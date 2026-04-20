"""振り分け済み写真の移動スクリプト。

SORTING_ROOT/{actor}/ の写真を ANALYZE_ROOT/{actor}/ に移動する。
sorting_state テーブルに同名エントリが存在する場合、移動先ファイル名を
{stem}_{num:02d}{ext} にリネームする（num は 01 から開始）。

並列実行を行う（デフォルト worker 数は 4）。

Usage:
    python -m src.move.main
    python -m src.move.main --workers 8
"""

import argparse
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine

from src.db_schema import sorting_state

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")
SORTED_RESULTS_SUBDIR = "sorted_results"


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
# 移動リポジトリ
# ---------------------------------------------------------------------------


class MoveRepository:
    """sorting_state テーブルの読み取りを担う。"""

    def __init__(self, engine: Engine) -> None:
        """初期化。

        Args:
            engine: SQLAlchemy Engine。
        """
        self._engine = engine

    def getUnlearnedFilenames(self, actor: str) -> set:
        """指定 actor の learned=false のファイル名セットを返す。

        Args:
            actor: 被写体 ID。

        Returns:
            ファイル名のセット。
        """
        stmt = (
            select(sorting_state.c.filename)
            .where(
                sorting_state.c.actor_id == actor,
                sorting_state.c.learned == False,  # noqa: E712
            )
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return {row.filename for row in rows}


# ---------------------------------------------------------------------------
# 写真移動器
# ---------------------------------------------------------------------------


class PhotoMover:
    """振り分け済み写真の移動を担う。"""

    def listActorDirs(self, sorting_root: Path) -> list:
        """SORTING_ROOT 直下の actor ディレクトリ名リストを返す。

        Args:
            sorting_root: SORTING_ROOT パス。

        Returns:
            actor ディレクトリ名のリスト。ディレクトリが存在しない場合は空リスト。
        """
        if not sorting_root.exists():
            return []
        return [d for d in os.listdir(str(sorting_root)) if (sorting_root / d).is_dir()]

    def listPhotos(self, actor_dir: Path) -> list:
        """actor ディレクトリ配下の画像ファイル名リストを返す。

        Args:
            actor_dir: actor ディレクトリのパス。

        Returns:
            画像ファイル名のリスト。ディレクトリが存在しない場合は空リスト。
        """
        if not actor_dir.exists():
            return []
        return [f for f in os.listdir(str(actor_dir)) if f.lower().endswith(IMAGE_EXTENSIONS)]

    def resolveDestFilename(self, filename: str, dst_dir: Path, conflict_filenames: set) -> str:
        """移動先ファイル名を解決する。conflict がある場合はリネームする。

        sorting_state に同名エントリが存在する場合、{stem}_{num:02d}{ext} にリネームする。
        num は 01 から開始し、conflict_filenames と dst_dir に存在しない最小値を選ぶ。

        Args:
            filename: 元のファイル名。
            dst_dir: 移動先ディレクトリ。
            conflict_filenames: sorting_state のファイル名セット（learned=false）。

        Returns:
            移動先ファイル名。
        """
        if filename not in conflict_filenames:
            return filename

        stem = Path(filename).stem
        ext = Path(filename).suffix
        num = 1
        while True:
            new_name = f"{stem}_{num:02d}{ext}"
            if new_name not in conflict_filenames and not (dst_dir / new_name).exists():
                return new_name
            num += 1

    def movePhoto(self, src: Path, dst_dir: Path, dst_filename: str) -> None:
        """写真を移動する。

        Args:
            src: 移動元のファイルパス。
            dst_dir: 移動先ディレクトリ。
            dst_filename: 移動先ファイル名。
        """
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst_dir / dst_filename))


# ---------------------------------------------------------------------------
# actor 単位の移動処理
# ---------------------------------------------------------------------------


def _move_actor_photos(
    actor: str,
    sorting_root: Path,
    analyze_root: Path,
    repository: MoveRepository,
    mover: PhotoMover,
    max_workers: int,
) -> None:
    """指定 actor の写真を SORTING_ROOT から ANALYZE_ROOT に移動する。

    Args:
        actor: 被写体 ID。
        sorting_root: SORTING_ROOT パス。
        analyze_root: ANALYZE_ROOT パス。
        repository: MoveRepository インスタンス。
        mover: PhotoMover インスタンス。
        max_workers: 並列ワーカー数。
    """
    actor_src_dir = sorting_root / actor
    actor_dst_dir = analyze_root / actor

    photos = mover.listPhotos(actor_src_dir)
    if not photos:
        print(f"[INFO] No photos found for actor: {actor}")
        return

    conflict_filenames = repository.getUnlearnedFilenames(actor)

    def _move_one(filename: str) -> None:
        src = actor_src_dir / filename
        dst_filename = mover.resolveDestFilename(filename, actor_dst_dir, conflict_filenames)
        mover.movePhoto(src, actor_dst_dir, dst_filename)
        if dst_filename != filename:
            print(f"[INFO] Moved (renamed): {actor}/{filename} → {dst_filename}")
        else:
            print(f"[INFO] Moved: {actor}/{filename}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_move_one, f): f for f in photos}
        for future in as_completed(futures):
            filename = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"[ERROR] Failed to move {actor}/{filename}: {e}")


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------


def run(
    repository: Optional[MoveRepository] = None,
    mover: Optional[PhotoMover] = None,
    sorting_root: Optional[Path] = None,
    analyze_root: Optional[Path] = None,
    engine: Optional[Engine] = None,
    max_workers: int = 4,
) -> None:
    """振り分け済み写真の移動メイン処理。

    SORTING_ROOT/sorted_results/{actor}/ の写真を ANALYZE_ROOT/{actor}/ に移動する。
    sorting_state の learned=false エントリと同名のファイルはリネームして移動する。

    Args:
        repository: MoveRepository インスタンス（DI 用）。
        mover: PhotoMover インスタンス（DI 用）。
        sorting_root: SORTING_ROOT パス（DI 用）。省略時は環境変数を使用。
        analyze_root: ANALYZE_ROOT パス（DI 用）。省略時は環境変数を使用。
        engine: SQLAlchemy Engine（DI 用）。
        max_workers: 並列ワーカー数（デフォルト 4）。
    """
    _load_env()

    if engine is None:
        engine = _create_engine()
    if repository is None:
        repository = MoveRepository(engine)
    if mover is None:
        mover = PhotoMover()
    if sorting_root is None:
        sorting_root = Path(os.environ["SORTING_ROOT"])
    if analyze_root is None:
        analyze_root = Path(os.environ["ANALYZE_ROOT"])

    sorted_results_root = sorting_root / SORTED_RESULTS_SUBDIR
    actors = mover.listActorDirs(sorted_results_root)
    if not actors:
        print("[INFO] No actor directories found in SORTING_ROOT/sorted_results.")
        return

    for actor in actors:
        print(f"[INFO] Moving photos for actor: {actor}")
        _move_actor_photos(actor, sorted_results_root, analyze_root, repository, mover, max_workers)

    print("[INFO] Move complete.")


def main() -> None:
    """CLI エントリポイント。引数を解析して run() を呼び出す。"""
    parser = argparse.ArgumentParser(description="振り分け済み写真の移動スクリプト")
    parser.add_argument("--workers", type=int, default=4, help="並列ワーカー数（デフォルト: 4）")
    args = parser.parse_args()

    run(max_workers=args.workers)


if __name__ == "__main__":  # pragma: no cover
    main()
