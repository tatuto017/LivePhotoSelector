"""データ整理スクリプト。

フェーズ1（--publish）: 解析完了・手動でのファイル移動後に sorting_state.public を true に更新する。
  ファイルの移動（ANALYZE_ROOT → DATA_ROOT/images/）は事前に手動で実施済みであること。

フェーズ2（デフォルト）: 選別後に sorting_state の selection_state に基づいて
  ok 写真を confirmed/ へ移動し、ng 写真を削除する。
  その後、lychee アルバムから NG 写真を削除する。

Usage:
    python -m src.finalize.main --publish              # フェーズ1: 公開処理
    python -m src.finalize.main                        # フェーズ2: 選別後整理
    python -m src.finalize.main --album_id=<ALBUM_ID>  # フェーズ2: ルートアルバム ID を上書き
"""

import argparse
import os
import shutil
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pychee import pychee as pychee_lib
from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import Engine

from src.db_schema import sorting_state
from src.lychee_schema import lychee_albums, lychee_base_albums, lychee_photo_album


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


def _create_lychee_engine() -> Engine:
    """環境変数から lychee DB 用 SQLAlchemy エンジンを生成する。

    Returns:
        SQLAlchemy Engine（PyMySQL ドライバー使用）。
    """
    host = os.environ["MYSQL_HOST"]
    port = os.environ.get("MYSQL_PORT", "3306")
    user = os.environ["LYCHEE_DB_USER"]
    password = os.environ["LYCHEE_DB_PASSWORD"]
    database = os.environ["LYCHEE_DATABASE"]
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    return create_engine(url)


def _create_lychee_client() -> "LycheeApiClient":
    """環境変数から lychee API クライアントを生成してログインする。

    Returns:
        ログイン済みの LycheeApiClient インスタンス。
    """
    url = os.environ["LYCHEE_URL"]
    user = os.environ["LYCHEE_USER"]
    password = os.environ["LYCHEE_PASSWORD"]
    client = pychee_lib.LycheeClient(url)
    client.login(user, password)
    return LycheeApiClient(client)


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

    def loadNgNotRemovedEntries(self, actor: str) -> list:
        """selection_state='ng' かつ remove=false のエントリを返す。

        Args:
            actor: 被写体 ID。

        Returns:
            NG かつ未削除エントリの dict リスト。
        """
        stmt = (
            select(
                sorting_state.c.filename,
                sorting_state.c.shooting_date,
                sorting_state.c.selection_state,
            )
            .where(
                sorting_state.c.actor_id == actor,
                sorting_state.c.selection_state == "ng",
                sorting_state.c["remove"] == False,  # noqa: E712
            )
            .order_by(sorting_state.c.filename)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [
            {
                "filename": row.filename,
                "shootingDate": str(row.shooting_date),
                "selectionState": row.selection_state,
            }
            for row in rows
        ]

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

    def updateRemove(self, actor: str, filename: str, shootingDate: str) -> None:
        """sorting_state テーブルの指定エントリで remove を true に更新する。

        lychee アルバムからの削除完了後に呼び出す。

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
            .values(remove=True)
        )
        with self._engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()


# ---------------------------------------------------------------------------
# lychee リポジトリ
# ---------------------------------------------------------------------------


class LycheeRepository:
    """lychee DB のアルバム・写真情報を扱うリポジトリ。"""

    def __init__(self, engine: Engine) -> None:
        """初期化。

        Args:
            engine: SQLAlchemy Engine（lychee DB 接続用）。
        """
        self._engine = engine

    def getAlbumsByParentId(self, parentId: str) -> list:
        """指定した親アルバム ID 配下のアルバム一覧を返す。

        Args:
            parentId: 親アルバム ID。

        Returns:
            {"id": str, "title": str} の dict リスト。
        """
        stmt = (
            select(lychee_albums.c.id, lychee_base_albums.c.title)
            .select_from(
                lychee_albums.join(
                    lychee_base_albums,
                    lychee_albums.c.id == lychee_base_albums.c.id,
                    isouter=True,
                )
            )
            .where(lychee_albums.c.parent_id == parentId)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [{"id": row.id, "title": row.title} for row in rows]

    def getPhotoIdsByAlbumId(self, albumId: str) -> list:
        """指定したアルバム ID 配下の写真 ID 一覧を返す。

        Args:
            albumId: アルバム ID。

        Returns:
            photo_id の文字列リスト。
        """
        stmt = select(lychee_photo_album.c.photo_id).where(
            lychee_photo_album.c.album_id == albumId
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [row.photo_id for row in rows]


# ---------------------------------------------------------------------------
# lychee API クライアント
# ---------------------------------------------------------------------------


class LycheeApiClient:
    """lychee Web API クライアント。写真削除を担う。"""

    def __init__(self, client: Any) -> None:
        """初期化。

        Args:
            client: pychee.LycheeClient インスタンス。
        """
        self._client = client

    def deletePhotos(self, photoIds: list) -> None:
        """写真 ID リストを lychee API で削除する。空リストの場合は何もしない。

        Args:
            photoIds: 削除対象の写真 ID リスト。
        """
        if photoIds:
            self._client.delete_photo(photoIds)


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
    album_id: Optional[str] = None,
    lychee_repository: Optional[LycheeRepository] = None,
    lychee_client: Optional[LycheeApiClient] = None,
    lychee_engine: Optional[Engine] = None,
) -> None:
    """データ整理のメイン処理。

    mode='publish'  : フェーズ1 — sorting_state.public を true に更新する。
                      ファイルの移動は事前に手動で実施済みであること。
    mode='finalize' : フェーズ2 — 選別済み（ok/ng）エントリを整理し、
                      lychee アルバムから NG 写真を削除する。

    Args:
        mode: 実行モード。"publish" または "finalize"。
        repository: FinalizeRepository インスタンス（DI 用）。
        finalizer: PhotoFinalizer インスタンス（DI 用）。
        data_root: データルートパス（DI 用）。finalize モード時に使用。省略時は DATA_ROOT 環境変数を使用。
        engine: SQLAlchemy Engine（DI 用）。
        album_id: lychee ルートアルバム ID（DI 用）。省略時は LYCHEE_ROOT_ALBUM_ID 環境変数を使用。
        lychee_repository: LycheeRepository インスタンス（DI 用）。
        lychee_client: LycheeApiClient インスタンス（DI 用）。
        lychee_engine: lychee DB 用 SQLAlchemy Engine（DI 用）。
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

        if lychee_repository is None:
            if lychee_engine is None:
                lychee_engine = _create_lychee_engine()
            lychee_repository = LycheeRepository(lychee_engine)
        if lychee_client is None:
            lychee_client = _create_lychee_client()
        root_album_id = album_id or os.environ["LYCHEE_ROOT_ALBUM_ID"]
        _run_lychee_remove(repository, lychee_repository, lychee_client, root_album_id)
        print("[INFO] Lychee remove complete.")


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


def _run_lychee_remove(
    repository: FinalizeRepository,
    lychee_repository: LycheeRepository,
    lychee_client: LycheeApiClient,
    root_album_id: str,
) -> None:
    """lychee アルバムから NG 写真を削除する。

    処理フロー:
    1. ルートアルバム配下の撮影日別アルバムを取得する。
    2. 被写体ごとに NG かつ未削除のエントリを取得する。
    3. 撮影日に対応するアルバムを検索する。
    4. 被写体に対応するアルバムを検索する。
    5. アルバム内の写真 ID を取得して lychee API で削除する。
    6. sorting_state の remove を true に更新する。

    Args:
        repository: FinalizeRepository インスタンス。
        lychee_repository: LycheeRepository インスタンス。
        lychee_client: LycheeApiClient インスタンス。
        root_album_id: lychee ルートアルバム ID。
    """
    actors = repository.getActors()
    date_albums = lychee_repository.getAlbumsByParentId(root_album_id)

    for actor in actors:
        ng_entries = repository.loadNgNotRemovedEntries(actor)
        if not ng_entries:
            continue

        # 撮影日ごとにエントリをグループ化
        date_to_entries: dict = {}
        for entry in ng_entries:
            date_to_entries.setdefault(entry["shootingDate"], []).append(entry)

        for shooting_date, entries in date_to_entries.items():
            # sorting_state の "YYYY-MM-DD" を lychee アルバムタイトルの "YYYY.MM.DD" に変換
            date_album_title = shooting_date.replace("-", ".")
            date_album = next(
                (a for a in date_albums if a["title"] == date_album_title), None
            )
            if date_album is None:
                print(f"[WARN] Date album not found: {date_album_title}")
                continue

            actor_albums = lychee_repository.getAlbumsByParentId(date_album["id"])
            actor_album = next(
                (a for a in actor_albums if a["title"] == actor), None
            )
            if actor_album is None:
                print(f"[WARN] Actor album not found: {actor} in {date_album_title}")
                continue

            photo_ids = lychee_repository.getPhotoIdsByAlbumId(actor_album["id"])
            if photo_ids:
                lychee_client.deletePhotos(photo_ids)
                print(
                    f"[INFO] Deleted {len(photo_ids)} photos from lychee: "
                    f"{date_album_title}/{actor}"
                )

            for entry in entries:
                repository.updateRemove(actor, entry["filename"], shooting_date)
                print(f"[INFO] Updated remove=true: {actor}/{entry['filename']}")


def main() -> None:
    """CLI エントリポイント。引数を解析して run() を呼び出す。"""
    parser = argparse.ArgumentParser(description="データ整理スクリプト")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="フェーズ1: sorting_state.public を true に更新する（ファイル移動は手動で事前実施）",
    )
    parser.add_argument(
        "--album_id",
        type=str,
        default=None,
        help="lychee ルートアルバム ID（省略時は LYCHEE_ROOT_ALBUM_ID 環境変数を使用）",
    )
    args = parser.parse_args()

    if args.publish:
        run(mode="publish")
    else:
        run(mode="finalize", album_id=args.album_id)


if __name__ == "__main__":  # pragma: no cover
    main()
