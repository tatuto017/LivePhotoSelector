"""DeepFace による写真解析スクリプト。

ANALYZE_ROOT/{actor}/ の写真を DeepFace で解析し、
analysis_records・sorting_state テーブルに結果を保存する。

解析対象ファイルはファイルシステムから直接取得する。
sorting_state に既に存在するファイルはスキップするため、
OOM Kill 後に再起動しても安全に途中から再開できる。

写真ファイルは解析後も ANALYZE_ROOT に留め、
全解析完了後に手動でのファイル移動（ANALYZE_ROOT → DATA_ROOT/images/）を促す。

Usage:
    python -m src.analysis.main
    python -m src.analysis.main --scoring
    python -m src.analysis.main --finalize
"""

import argparse
import json
import math
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image
from PIL.ExifTags import TAGS
from dotenv import load_dotenv
from sqlalchemy import create_engine, select, insert, distinct
from sqlalchemy.engine import Engine
from tqdm import tqdm

from src.db_schema import analysis_records, sorting_state


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass
class AnalysisRecord:
    """analysis_records テーブルに格納する 1 件の DeepFace 解析データ。"""

    actor: str
    filename: str
    shootingDate: str
    angry: float
    fear: float
    happy: float
    sad: float
    surprise: float
    disgust: float
    neutral: float
    faceAngle: float
    isOccluded: bool
    face_embedding: list


@dataclass
class AnalysisEntry:
    """sorting_state テーブルに格納する 1 件の選別データ。"""

    filename: str
    shootingDate: str
    score: Optional[float] = None
    selectionState: str = "pending"
    selectedAt: Optional[str] = None


# ---------------------------------------------------------------------------
# 環境変数
# ---------------------------------------------------------------------------


def _load_env() -> None:
    """プロジェクトルートの .env を読み込む。既存の環境変数は上書きしない。"""
    load_dotenv(override=False)


def _create_engine() -> Engine:
    """環境変数から SQLAlchemy エンジンを生成する。

    Returns:
        SQLAlchemy Engine（PyMySQL ドライバー使用）。
    """
    host = os.environ["MYSQL_HOST"]
    port = os.environ.get("MYSQL_PORT", "3306")
    user = os.environ["MYSQL_USER"]
    password = os.environ["MYSQL_PASSWORD"]
    database = os.environ["MYSQL_DATABASE"]
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    return create_engine(url)


# ---------------------------------------------------------------------------
# EXIF ユーティリティ
# ---------------------------------------------------------------------------


def _get_shooting_date(img_path: Path) -> str:
    """EXIF DateTimeOriginal から撮影日を取得する。

    Args:
        img_path: 画像ファイルのパス。

    Returns:
        撮影日 (YYYY-MM-DD)。EXIF が無い場合または例外時は今日の日付。
    """
    try:
        with Image.open(img_path) as img:
            exif_data = img._getexif()  # type: ignore[attr-defined]
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    if tag == "DateTimeOriginal":
                        # EXIF フォーマット: "2026:04:01 12:00:00"
                        dt = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 顔角度計算
# ---------------------------------------------------------------------------


def _calculate_face_angle(left_eye: list, right_eye: list) -> float:
    """両目の座標からロール角（度数）を計算する。

    水平方向を基準に、右目と左目を結ぶ線の傾きをアークタンジェントで求める。

    Args:
        left_eye: 左目の座標 [x, y]。
        right_eye: 右目の座標 [x, y]。

    Returns:
        ロール角（度数）。
    """
    dx = right_eye[0] - left_eye[0]
    dy = right_eye[1] - left_eye[1]
    return math.degrees(math.atan2(dy, dx))


# ---------------------------------------------------------------------------
# 解析リポジトリ
# ---------------------------------------------------------------------------


class AnalysisRepository:
    """analysis_records テーブルへの読み書きと sorting_state テーブルへの INSERT を担う。"""

    def __init__(self, engine: Engine) -> None:
        """初期化。

        Args:
            engine: SQLAlchemy Engine。
        """
        self._engine = engine

    def loadRecords(self) -> list:
        """analysis_records テーブルから全解析レコードを読み込む。

        Returns:
            AnalysisRecord のリスト。レコードが存在しない場合は空リスト。
        """
        stmt = select(
            analysis_records.c.actor,
            analysis_records.c.filename,
            analysis_records.c.shooting_date,
            analysis_records.c.angry,
            analysis_records.c.fear,
            analysis_records.c.happy,
            analysis_records.c.sad,
            analysis_records.c.surprise,
            analysis_records.c.disgust,
            analysis_records.c.neutral,
            analysis_records.c.face_angle,
            analysis_records.c.is_occluded,
            analysis_records.c.face_embedding,
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [
            AnalysisRecord(
                actor=row.actor,
                filename=row.filename,
                shootingDate=str(row.shooting_date),
                angry=row.angry,
                fear=row.fear,
                happy=row.happy,
                sad=row.sad,
                surprise=row.surprise,
                disgust=row.disgust,
                neutral=row.neutral,
                faceAngle=row.face_angle,
                isOccluded=bool(row.is_occluded),
                face_embedding=json.loads(row.face_embedding)
                if isinstance(row.face_embedding, str)
                else row.face_embedding,
            )
            for row in rows
        ]

    def loadProcessedKeys(self) -> set:
        """sorting_state テーブルから処理済み (actor_id, filename) ペアを返す。

        OOM Kill 後の再起動時に既処理ファイルをスキップするために使用する。
        DeepFace 解析に失敗したファイルも sorting_state に登録されるため、
        analysis_records ではなく sorting_state を参照する。

        Returns:
            処理済み (actor_id, filename) のセット。
        """
        stmt = select(
            sorting_state.c.actor_id,
            sorting_state.c.filename,
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return {(row.actor_id, row.filename) for row in rows}

    def insertRecord(self, record: AnalysisRecord) -> None:
        """解析レコードを analysis_records テーブルに INSERT する。

        同一 (actor, filename) が既に存在する場合はスキップする
        （INSERT IGNORE によりプロセス再起動後の継続に対応）。

        Args:
            record: 挿入する AnalysisRecord。
        """
        stmt = insert(analysis_records).prefix_with("IGNORE").values(
            actor=record.actor,
            filename=record.filename,
            shooting_date=record.shootingDate,
            angry=record.angry,
            fear=record.fear,
            happy=record.happy,
            sad=record.sad,
            surprise=record.surprise,
            disgust=record.disgust,
            neutral=record.neutral,
            face_angle=record.faceAngle,
            is_occluded=1 if record.isOccluded else 0,
            face_embedding=json.dumps(record.face_embedding),
        )
        with self._engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()

    def insertEntry(self, actor: str, entry: AnalysisEntry) -> None:
        """sorting_state テーブルに解析エントリを INSERT する。

        同一 (actor_id, filename, shooting_date) が既に存在する場合はスキップする
        （INSERT IGNORE によりプロセス再起動後の継続に対応）。
        public は初期値 FALSE のままとし、全解析完了後の --publish フェーズで更新する。

        Args:
            actor: 被写体 ID。
            entry: 挿入する AnalysisEntry。
        """
        stmt = insert(sorting_state).prefix_with("IGNORE").values(
            actor_id=actor,
            filename=entry.filename,
            shooting_date=entry.shootingDate,
            score=entry.score,
            selection_state=entry.selectionState,
            selected_at=entry.selectedAt,
        )
        with self._engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()


# ---------------------------------------------------------------------------
# 写真解析器
# ---------------------------------------------------------------------------


class PhotoAnalyzer:
    """DeepFace を使用して写真を解析する。"""

    # サブプロセスのタイムアウト秒数（QEMU 環境での処理時間を考慮して余裕を持たせる）
    _SUBPROCESS_TIMEOUT = 300

    def analyze(self, img_path: Path, actor: str) -> Optional[AnalysisRecord]:
        """写真を DeepFace で解析して AnalysisRecord を返す。

        DeepFace/TF の重いモデルをサブプロセスで実行することで、
        OOM Kill によるメインプロセスの強制終了を防ぐ。
        サブプロセスが OOM Kill された場合は None を返し、次の画像の処理に進む。

        Args:
            img_path: 解析する画像ファイルのパス。
            actor: 被写体 ID。

        Returns:
            解析結果の AnalysisRecord。解析失敗・OOM Kill 時は None。
        """
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.analysis.analyzer_subprocess",
                    str(img_path),
                    actor,
                ],
                capture_output=True,
                text=True,
                timeout=self._SUBPROCESS_TIMEOUT,
            )
            if result.returncode != 0:
                # OOM Kill (exit 137) や解析エラーを含む全失敗ケース
                stderr = result.stderr.strip()
                print(
                    f"[WARN] Failed to analyze {img_path}: "
                    f"{stderr or f'exit code {result.returncode}'}"
                )
                return None

            data = json.loads(result.stdout)
            shooting_date = _get_shooting_date(img_path)
            return AnalysisRecord(
                actor=data["actor"],
                filename=data["filename"],
                shootingDate=shooting_date,
                angry=data["angry"],
                fear=data["fear"],
                happy=data["happy"],
                sad=data["sad"],
                surprise=data["surprise"],
                disgust=data["disgust"],
                neutral=data["neutral"],
                faceAngle=data["faceAngle"],
                isOccluded=data["isOccluded"],
                face_embedding=data["face_embedding"],
            )
        except subprocess.TimeoutExpired:
            print(f"[WARN] Timeout analyzing {img_path}")
            return None
        except Exception as e:
            print(f"[WARN] Failed to analyze {img_path}: {e}")
            return None


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------


def run(
    mode: str = "analyze",
    analyzer: Optional[PhotoAnalyzer] = None,
    repository: Optional[AnalysisRepository] = None,
    analyze_root: Optional[Path] = None,
    engine: Optional[Engine] = None,
    max_workers: int = 2,
) -> None:
    """メイン処理を実行する。

    Args:
        mode: 実行モード。"analyze" / "scoring" / "finalize" のいずれか。
        analyzer: PhotoAnalyzer インスタンス（DI 用）。
        repository: AnalysisRepository インスタンス（DI 用）。
        analyze_root: 解析作業ディレクトリのパス（DI 用）。省略時は ANALYZE_ROOT 環境変数を使用。
        engine: SQLAlchemy Engine（DI 用）。
        max_workers: 並列処理の最大ワーカー数（DI 用）。デフォルトは 2。
    """
    _load_env()

    if analyze_root is None:
        analyze_root = Path(os.environ["ANALYZE_ROOT"])
    if engine is None:
        engine = _create_engine()
    if repository is None:
        repository = AnalysisRepository(engine)
    if analyzer is None:
        analyzer = PhotoAnalyzer()

    if mode == "analyze":
        _run_analyze(analyze_root, analyzer, repository, max_workers=max_workers)
    elif mode == "scoring":
        _run_scoring()
    elif mode == "finalize":
        _run_finalize()


def _run_analyze(
    analyze_root: Path,
    analyzer: PhotoAnalyzer,
    repository: AnalysisRepository,
    max_workers: int = 2,
) -> None:
    """ANALYZE_ROOT/{actor}/ の写真をファイルシステムから取得して並列解析し、DB を更新する。

    写真ファイルは ANALYZE_ROOT に留め、ファイル移動は行わない。
    全解析完了後に手動でのファイル移動（ANALYZE_ROOT → DATA_ROOT/images/）を促す。

    処理フロー:
    1. ANALYZE_ROOT 直下の被写体ディレクトリを列挙する。
    2. 各被写体ディレクトリ内のファイルを列挙する。
    3. sorting_state に既に存在するファイルはスキップする（OOM 後の再起動対応）。
    4. 未処理画像を ThreadPoolExecutor で並列に DeepFace 解析する。
    5. DB への書き込みはロックで保護してスレッドセーフを確保する。

    Args:
        analyze_root: 解析作業ディレクトリ（{actor}/ サブディレクトリを含む）。
        analyzer: PhotoAnalyzer インスタンス。
        repository: AnalysisRepository インスタンス。
        max_workers: 並列処理の最大ワーカー数（Raspberry Pi 4 では 2 を推奨）。
    """
    if not analyze_root.exists():
        print(f"[INFO] ANALYZE_ROOT が存在しません: {analyze_root}")
        return

    # 被写体ディレクトリ一覧をソート順で取得
    actor_dirs = sorted([d for d in analyze_root.iterdir() if d.is_dir()])
    if not actor_dirs:
        print("[INFO] ANALYZE_ROOT に被写体ディレクトリが見つかりません。")
        return

    # analysis_records の重複 INSERT 防止用セット (actor, filename)
    existing_keys = {(r.actor, r.filename) for r in repository.loadRecords()}
    # sorting_state 処理済みキー（再解析スキップ用）
    processed_keys = repository.loadProcessedKeys()

    # 全ファイルを収集（被写体 → ファイル名 順にソート）
    all_entries = []
    for actor_dir in actor_dirs:
        actor = actor_dir.name
        for file_path in sorted(actor_dir.iterdir()):
            if file_path.is_file():
                all_entries.append((actor, file_path.name, file_path))

    if not all_entries:
        print("[INFO] 解析対象ファイルが見つかりません。")
        return

    # sorting_state に既に存在するファイルを除外して未処理のみに絞る（OOM 後の再起動対応）
    pending_entries = [
        (actor, filename, img_path)
        for actor, filename, img_path in all_entries
        if (actor, filename) not in processed_keys
    ]

    # スレッド間で共有する状態（existing_keys・processed_keys・DB）を保護するロック
    lock = threading.Lock()

    def _process_one(actor: str, filename: str, img_path: Path) -> None:
        """1 枚の画像を解析し、ロックを取得してから DB に書き込む。

        analyzer.analyze() はサブプロセスを起動するため並列実行による CPU バウンドは発生しない。
        DB 書き込みと共有キャッシュの更新のみロックで保護する。

        Args:
            actor: 被写体 ID。
            filename: ファイル名。
            img_path: 画像ファイルのパス。
        """
        record = analyzer.analyze(img_path, actor)

        # 初期 score: DeepFace の最大感情スコア (0〜1)
        score: Optional[float] = None
        if record is not None:
            max_val = max(
                record.angry,
                record.fear,
                record.happy,
                record.sad,
                record.surprise,
                record.disgust,
                record.neutral,
            )
            score = round(float(max_val) / 100.0, 4)

        shooting_date = (
            record.shootingDate if record is not None else _get_shooting_date(img_path)
        )
        entry = AnalysisEntry(filename=filename, shootingDate=shooting_date, score=score)

        # DB 書き込みと共有キャッシュ更新はロックで保護する
        with lock:
            if record is not None and (actor, filename) not in existing_keys:
                repository.insertRecord(record)
                existing_keys.add((actor, filename))
            repository.insertEntry(actor, entry)
            processed_keys.add((actor, filename))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_one, actor, filename, img_path): (actor, filename)
            for actor, filename, img_path in pending_entries
        }
        for future in tqdm(as_completed(futures), total=len(pending_entries), desc="解析", unit="枚"):
            try:
                future.result()
            except Exception as e:
                actor_name, fname = futures[future]
                print(f"[WARN] Error processing {actor_name}/{fname}: {e}")

    print("[INFO] Analysis complete.")


def _run_scoring() -> None:
    """スコアリングを実行する。src.scoring.main.run() に委譲する。"""
    from src.scoring.main import run as scoring_run

    scoring_run()


def _run_finalize() -> None:
    """データ整理を実行する。src.finalize.main.run() に委譲する。"""
    from src.finalize.main import run as finalize_run

    finalize_run()


def main() -> None:
    """CLI エントリポイント。引数を解析して run() を呼び出す。"""
    parser = argparse.ArgumentParser(description="DeepFace 写真解析スクリプト")
    parser.add_argument(
        "--scoring",
        action="store_true",
        help="Scikit-learn によるスコアリングを実行する",
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="写真整理（OK → confirmed 移動、NG → 削除）を実行する",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="並列処理の最大ワーカー数（Raspberry Pi 4 では 2 を推奨、デフォルト: 2）",
    )
    args = parser.parse_args()

    if args.scoring:
        run(mode="scoring")
    elif args.finalize:
        run(mode="finalize")
    else:
        run(mode="analyze", max_workers=args.workers)


if __name__ == "__main__":  # pragma: no cover
    main()
