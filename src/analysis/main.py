"""DeepFace による写真解析スクリプト。

INBOX_ROOT/{actor}/ の写真を DeepFace で解析し、
analysis.pki に解析結果を保存して inbox → images へ移動する。
{actor}_analysis.json を更新する。

Usage:
    python -m src.analysis.main
    python -m src.analysis.main --scoring
    python -m src.analysis.main --finalize
"""

import argparse
import json
import math
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image
from PIL.ExifTags import TAGS
from dotenv import load_dotenv
from tqdm import tqdm


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass
class AnalysisRecord:
    """analysis.pki に格納する 1 件の DeepFace 解析データ。"""

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
    """{actor}_analysis.json に格納する 1 件の選別データ。"""

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
    """analysis.pki と {actor}_analysis.json の読み書きを担う。"""

    def __init__(self, project_root: Path, one_drive_root: Path) -> None:
        """初期化。

        Args:
            project_root: プロジェクトルートディレクトリ。
            one_drive_root: OneDrive ルートディレクトリ。
        """
        self._pki_path = one_drive_root / "data" / "analysis.pki"
        self._data_dir = one_drive_root / "data"

    def loadRecords(self) -> list:
        """analysis.pki から解析レコードを読み込む。

        Returns:
            AnalysisRecord のリスト。ファイルが存在しない場合は空リスト。
        """
        if not self._pki_path.exists():
            return []
        with open(self._pki_path, "rb") as f:
            return pickle.load(f)

    def saveRecords(self, records: list) -> None:
        """解析レコードを analysis.pki にアトミックに保存する。

        一時ファイルに書き込んでからリネームすることで、
        プロセス強制終了時のファイル破損を防ぐ。

        Args:
            records: AnalysisRecord のリスト。
        """
        self._pki_path.parent.mkdir(parents=True, exist_ok=True)
        dir_ = self._pki_path.parent
        with tempfile.NamedTemporaryFile("wb", dir=dir_, delete=False) as tmp:
            pickle.dump(records, tmp)
            tmp_path = tmp.name
        shutil.move(tmp_path, self._pki_path)

    def loadActorEntries(self, actor: str) -> list:
        """{actor}_analysis.json から選別エントリを読み込む。

        JSON が破損している場合は空リストを返して警告を出す。

        Args:
            actor: 被写体 ID。

        Returns:
            AnalysisEntry のリスト。ファイルが存在しない場合は空リスト。
        """
        path = self._data_dir / f"{actor}_analysis.json"
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [AnalysisEntry(**entry) for entry in data]
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[WARN] {path} の読み込みに失敗しました（破損の可能性）: {e}")
            return []

    def saveActorEntries(self, actor: str, entries: list) -> None:
        """{actor}_analysis.json に選別エントリをアトミックに保存する。

        一時ファイルに書き込んでからリネームすることで、
        プロセス強制終了時のファイル破損を防ぐ。

        Args:
            actor: 被写体 ID。
            entries: AnalysisEntry のリスト。
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        path = self._data_dir / f"{actor}_analysis.json"
        data = [
            {
                "filename": e.filename,
                "shootingDate": e.shootingDate,
                "score": e.score,
                "selectionState": e.selectionState,
                "selectedAt": e.selectedAt,
            }
            for e in entries
        ]
        with tempfile.NamedTemporaryFile(
            "w", dir=self._data_dir, delete=False, encoding="utf-8", suffix=".json"
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name
        shutil.move(tmp_path, path)


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
# 写真移動器
# ---------------------------------------------------------------------------


class PhotoMover:
    """写真の inbox→images 移動・confirmed 移動・削除を担う。"""

    def __init__(self, one_drive_root: Path) -> None:
        """初期化。

        Args:
            one_drive_root: OneDrive ルートディレクトリ。
        """
        self._inbox_root = one_drive_root / "inbox"
        self._images_root = one_drive_root / "images"
        self._confirmed_root = one_drive_root / "confirmed"

    def moveToImages(self, actor: str, filename: str) -> None:
        """写真を inbox/{actor}/ から images/{actor}/ へ移動する。

        Args:
            actor: 被写体 ID。
            filename: ファイル名。
        """
        src = self._inbox_root / actor / filename
        dst_dir = self._images_root / actor
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst_dir / filename))

    def moveToConfirmed(self, actor: str, filename: str) -> None:
        """写真を images/{actor}/ から confirmed/{actor}/ へ移動する。

        Args:
            actor: 被写体 ID。
            filename: ファイル名。
        """
        src = self._images_root / actor / filename
        dst_dir = self._confirmed_root / actor
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst_dir / filename))

    def deleteFromImages(self, actor: str, filename: str) -> None:
        """images/{actor}/ から写真を削除する。ファイルが無い場合は何もしない。

        Args:
            actor: 被写体 ID。
            filename: ファイル名。
        """
        path = self._images_root / actor / filename
        if path.exists():
            path.unlink()


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------


def run(
    mode: str = "analyze",
    analyzer: Optional[PhotoAnalyzer] = None,
    repository: Optional[AnalysisRepository] = None,
    mover: Optional[PhotoMover] = None,
    project_root: Optional[Path] = None,
    one_drive_root: Optional[Path] = None,
) -> None:
    """メイン処理を実行する。

    Args:
        mode: 実行モード。"analyze" / "scoring" / "finalize" のいずれか。
        analyzer: PhotoAnalyzer インスタンス（DI 用）。
        repository: AnalysisRepository インスタンス（DI 用）。
        mover: PhotoMover インスタンス（DI 用）。
        project_root: プロジェクトルートパス（DI 用）。
        one_drive_root: OneDrive ルートパス（DI 用）。
    """
    _load_env()

    if project_root is None:
        project_root = Path(os.environ["PROJECT_ROOT"])
    if one_drive_root is None:
        one_drive_root = Path(os.environ["ONE_DRIVE_ROOT"])
    if repository is None:
        repository = AnalysisRepository(project_root, one_drive_root)
    if mover is None:
        mover = PhotoMover(one_drive_root)
    if analyzer is None:
        analyzer = PhotoAnalyzer()

    if mode == "analyze":
        _run_analyze(one_drive_root, analyzer, repository, mover)
    elif mode == "scoring":
        _run_scoring()
    elif mode == "finalize":
        _run_finalize()


def _run_analyze(
    one_drive_root: Path,
    analyzer: PhotoAnalyzer,
    repository: AnalysisRepository,
    mover: PhotoMover,
) -> None:
    """INBOX_ROOT/{actor}/ の写真を解析し、analysis.pki と {actor}_analysis.json を更新する。

    処理フロー:
    1. INBOX_ROOT 配下の actor ディレクトリを走査する。
    2. 各画像を DeepFace で解析して AnalysisRecord を作成・追記する。
    3. {actor}_analysis.json に AnalysisEntry を追記する（初期 score は最大感情スコア）。
    4. 写真を inbox → images へ移動する。
    5. analysis.pki を保存する。

    Args:
        one_drive_root: OneDrive ルートディレクトリ。
        analyzer: PhotoAnalyzer インスタンス。
        repository: AnalysisRepository インスタンス。
        mover: PhotoMover インスタンス。
    """
    inbox_root = one_drive_root / "inbox"
    if not inbox_root.exists():
        print(f"[INFO] Inbox not found: {inbox_root}")
        return

    records = repository.loadRecords()
    # 重複チェック用セット (actor, filename)
    existing_keys = {(r.actor, r.filename) for r in records}

    for actor_dir in sorted(inbox_root.iterdir()):
        if not actor_dir.is_dir():
            continue
        actor = actor_dir.name

        entries = repository.loadActorEntries(actor)
        existing_filenames = {e.filename for e in entries}

        # 対象拡張子の画像ファイルを取得
        img_files = sorted(
            f
            for f in actor_dir.iterdir()
            if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )

        for img_path in tqdm(img_files, desc=f"[{actor}]", unit="枚"):
            filename = img_path.name
            print(f"[INFO] Analyzing {actor}/{filename} ...")

            record = analyzer.analyze(img_path, actor)

            # 新規レコードのみ追加
            if record is not None and (actor, filename) not in existing_keys:
                records.append(record)
                existing_keys.add((actor, filename))

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

            # 新規エントリのみ追加
            if filename not in existing_filenames:
                shooting_date = (
                    record.shootingDate
                    if record is not None
                    else _get_shooting_date(img_path)
                )
                entries.append(
                    AnalysisEntry(
                        filename=filename,
                        shootingDate=shooting_date,
                        score=score,
                    )
                )
                existing_filenames.add(filename)

            # 移動前に pki・json を保存してデータ整合性を保つ。
            # OOM 等でプロセスが強制終了されても再起動時に続きから再開できる。
            repository.saveRecords(records)
            repository.saveActorEntries(actor, entries)

            # inbox → images へ移動
            mover.moveToImages(actor, filename)

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
    args = parser.parse_args()

    if args.scoring:
        run(mode="scoring")
    elif args.finalize:
        run(mode="finalize")
    else:
        run(mode="analyze")


if __name__ == "__main__":  # pragma: no cover
    main()
