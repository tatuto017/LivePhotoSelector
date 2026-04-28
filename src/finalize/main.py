"""データ整理スクリプト。

フェーズ1（--publish）: 解析完了・手動でのファイル移動後に sorting_state.public を true に更新する。
  ファイルの移動（ANALYZE_ROOT → DATA_ROOT/images/）は事前に手動で実施済みであること。

フェーズ2（デフォルト）: 選別後に sorting_state の selection_state に基づいて
  ok 写真を confirmed/ へ移動し、ng 写真を削除する。

Usage:
    python -m src.finalize.main --publish   # フェーズ1: 公開処理
    python -m src.finalize.main             # フェーズ2: 選別後整理
"""

import argparse
import os
import shutil
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import Engine

from src.db_schema import sorting_state


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
# データ整理リポジトリ
# ---------------------------------------------------------------------------


class FinalizeRepository:
    """sorting_state テーブルの読み書きを担う。"""

    def __init__(self, engine: Engine) -> None:
        """初期化。

        Args:
            engine: SQLAlchemy Engine。
        """
        self._engine = engine

    def getActors(self) -> list:
        """sorting_state テーブルから被写体 ID 一覧を返す。

        Returns:
            被写体 ID のリスト（ソート済み）。
        """
        stmt = (
            select(sorting_state.c.actor_id)
            .distinct()
            .order_by(sorting_state.c.actor_id)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [row.actor_id for row in rows]

    def loadFinalizedEntries(self, actor: str) -> list:
        """sorting_state テーブルから ok / ng かつ未整理（finalize=false）の処理対象エントリを返す。

        Args:
            actor: 被写体 ID。

        Returns:
            ok または ng のエントリの dict リスト。
        """
        stmt = (
            select(
                sorting_state.c.filename,
                sorting_state.c.shooting_date,
                sorting_state.c.score,
                sorting_state.c.selection_state,
                sorting_state.c.selected_at,
            )
            .where(
                sorting_state.c.actor_id == actor,
                sorting_state.c.selection_state.in_(["ok", "ng"]),
                sorting_state.c.finalize == False,  # noqa: E712
            )
            .order_by(sorting_state.c.filename)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        result = []
        for row in rows:
            result.append({
                "filename": row.filename,
                "shootingDate": str(row.shooting_date),
                "score": float(row.score) if row.score is not None else None,
                "selectionState": row.selection_state,
                "selectedAt": str(row.selected_at) if row.selected_at is not None else None,
            })
        return result

    def updateFinalize(self, actor: str, filename: str, shootingDate: str) -> None:
        """sorting_state テーブルの指定エントリで finalize を true に更新する。

        ファイル整理（移動または削除）完了後に呼び出す。

        Args:
            actor: 被写体 ID。
            filename: ファイル名。
            shootingDate: 撮影日文字列（YYYY-MM-DD）。
        """
        stmt = (
            update(sorting_state)
            .where(
                sorting_state.c.actor_id == actor,
                sorting_state.c.filename == filename,
                sorting_state.c.shooting_date == shootingDate,
            )
            .values(finalize=True)
        )
        with self._engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()

    def updatePublic(self, actor: str) -> None:
        """sorting_state テーブルの指定 actor の全エントリで public を true に更新する。

        手動でのファイル移動（ANALYZE_ROOT → DATA_ROOT/images/）完了後に呼び出す。

        Args:
            actor: 被写体 ID。
        """
        stmt = (
            update(sorting_state)
            .where(sorting_state.c.actor_id == actor)
            .values(public=True)
        )
        with self._engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()


# ---------------------------------------------------------------------------
# 写真整理器（フェーズ2）
# ---------------------------------------------------------------------------


class PhotoFinalizer:
    """写真の confirmed 移動・削除を担う。"""

    def __init__(self, data_root: Path) -> None:
        """初期化。

        Args:
            data_root: データルートディレクトリ（images/confirmed を含む）。
        """
        self._images_root = data_root / "images"
        self._confirmed_root = data_root / "confirmed"

    def moveToConfirmed(self, actor: str, filename: str) -> None:
        """写真を data/images/{actor}/ から data/confirmed/{actor}/ へ移動する。

        Args:
            actor: 被写体 ID。
            filename: ファイル名。
        """
        src = self._images_root / actor / filename
        dst_dir = self._confirmed_root / actor
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst_dir / filename))

    def deleteFromImages(self, actor: str, filename: str) -> None:
        """data/images/{actor}/ から写真を削除する。ファイルが無い場合は何もしない。

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
    mode: str = "finalize",
    repository: Optional[FinalizeRepository] = None,
    finalizer: Optional[PhotoFinalizer] = None,
    data_root: Optional[Path] = None,
    engine: Optional[Engine] = None,
) -> None:
    """データ整理のメイン処理。

    mode='publish'  : フェーズ1 — sorting_state.public を true に更新する。
                      ファイルの移動は事前に手動で実施済みであること。
    mode='finalize' : フェーズ2 — 選別済み（ok/ng）エントリを整理する。

    Args:
        mode: 実行モード。"publish" または "finalize"。
        repository: FinalizeRepository インスタンス（DI 用）。
        finalizer: PhotoFinalizer インスタンス（DI 用）。
        data_root: データルートパス（DI 用）。finalize モード時に使用。省略時は DATA_ROOT 環境変数を使用。
        engine: SQLAlchemy Engine（DI 用）。
    """
    _load_env()

    if engine is None:
        engine = _create_engine()
    if repository is None:
        repository = FinalizeRepository(engine)

    if mode == "publish":
        _run_publish(repository)
    else:
        if data_root is None:
            data_root = Path(os.environ["DATA_ROOT"])
        if finalizer is None:
            finalizer = PhotoFinalizer(data_root)
        actors = repository.getActors()
        for actor in actors:
            print(f"[INFO] Finalizing actor: {actor}")
            _run_finalize_for_actor(actor, repository, finalizer)
        print("[INFO] Finalize complete.")


def _run_publish(repository: FinalizeRepository) -> None:
    """フェーズ1: sorting_state の全エントリで public を true に更新する。

    ファイルの移動（ANALYZE_ROOT → DATA_ROOT/images/）は事前に手動で実施済みであることを前提とする。
    DB の public フラグを更新することで Web アプリ上で写真が表示対象になる。

    処理フロー:
    1. sorting_state から被写体 ID 一覧を取得する。
    2. 被写体ごとに sorting_state.public を true に更新する。

    Args:
        repository: FinalizeRepository インスタンス。
    """
    actors = repository.getActors()
    if not actors:
        print("[INFO] 公開対象の被写体が見つかりません。")
        return

    for actor in actors:
        print(f"[INFO] Publishing actor: {actor}")
        repository.updatePublic(actor)
        print(f"[INFO] Updated public=true for {actor}")

    print("[INFO] Publish complete.")


def _run_finalize_for_actor(
    actor: str,
    repository: FinalizeRepository,
    finalizer: PhotoFinalizer,
) -> None:
    """被写体ごとのデータ整理処理。

    1. ok エントリ → images/ から confirmed/ へ移動
    2. ng エントリ → images/ から削除
    sorting_state のレコードは削除しない。

    Args:
        actor: 被写体 ID。
        repository: FinalizeRepository インスタンス。
        finalizer: PhotoFinalizer インスタンス。
    """
    entries = repository.loadFinalizedEntries(actor)

    for entry in entries:
        state = entry.get("selectionState")
        if state == "ok":
            # ok: confirmed/ へ移動
            finalizer.moveToConfirmed(actor, entry["filename"])
            print(f"[INFO] Moved to confirmed: {actor}/{entry['filename']}")
        elif state == "ng":
            # ng: images/ から削除
            finalizer.deleteFromImages(actor, entry["filename"])
            print(f"[INFO] Deleted: {actor}/{entry['filename']}")
        repository.updateFinalize(actor, entry["filename"], entry["shootingDate"])


def main() -> None:
    """CLI エントリポイント。引数を解析して run() を呼び出す。"""
    parser = argparse.ArgumentParser(description="データ整理スクリプト")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="フェーズ1: sorting_state.public を true に更新する（ファイル移動は手動で事前実施）",
    )
    args = parser.parse_args()

    if args.publish:
        run(mode="publish")
    else:
        run(mode="finalize")


if __name__ == "__main__":  # pragma: no cover
    main()
