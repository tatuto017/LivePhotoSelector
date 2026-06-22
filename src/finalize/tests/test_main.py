"""src.finalize.main のユニットテスト。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from src.finalize.main import (
    FinalizeRepository,
    LycheeApiClient,
    LycheeRepository,
    PhotoFinalizer,
    _create_lychee_client,
    _create_lychee_engine,
    _load_env,
    _run_finalize_for_actor,
    _run_lychee_remove,
    _run_publish,
    main,
    run,
)


# ---------------------------------------------------------------------------
# _load_env
# ---------------------------------------------------------------------------


class TestLoadEnv:
    """_load_env のテスト。"""

    def test_calls_load_dotenv_with_override_false(self) -> None:
        """load_dotenv が override=False で呼ばれること。"""
        with patch("src.finalize.main.load_dotenv") as mock_load:
            _load_env()

        mock_load.assert_called_once_with(override=False)


# ---------------------------------------------------------------------------
# _create_lychee_engine
# ---------------------------------------------------------------------------


class TestCreateLycheeEngine:
    """_create_lychee_engine のテスト。"""

    def test_creates_engine_with_env_vars(self) -> None:
        """環境変数から lychee DB 用エンジンを生成すること。"""
        env = {
            "MYSQL_HOST": "db.host",
            "MYSQL_PORT": "3307",
            "LYCHEE_DB_USER": "lychee_user",
            "LYCHEE_DB_PASSWORD": "lychee_pass",
            "LYCHEE_DATABASE": "lychee_db",
        }
        with patch("src.finalize.main.create_engine") as mock_create:
            with patch.dict("os.environ", env, clear=True):
                _create_lychee_engine()

        mock_create.assert_called_once_with(
            "mysql+pymysql://lychee_user:lychee_pass@db.host:3307/lychee_db"
        )

    def test_creates_engine_with_default_port(self) -> None:
        """MYSQL_PORT が未設定のとき 3306 をデフォルトポートとして使用すること。"""
        env = {
            "MYSQL_HOST": "db.host",
            "LYCHEE_DB_USER": "lychee_user",
            "LYCHEE_DB_PASSWORD": "lychee_pass",
            "LYCHEE_DATABASE": "lychee_db",
        }
        with patch("src.finalize.main.create_engine") as mock_create:
            with patch.dict("os.environ", env, clear=True):
                _create_lychee_engine()

        mock_create.assert_called_once_with(
            "mysql+pymysql://lychee_user:lychee_pass@db.host:3306/lychee_db"
        )


# ---------------------------------------------------------------------------
# _create_lychee_client
# ---------------------------------------------------------------------------


class TestCreateLycheeClient:
    """_create_lychee_client のテスト。"""

    def test_creates_client_with_correct_url(self) -> None:
        """LYCHEE_URL で LycheeClient を生成すること。"""
        env = {
            "LYCHEE_URL": "http://lychee.host",
            "LYCHEE_USER": "lychee_user",
            "LYCHEE_PASSWORD": "lychee_pass",
        }
        with patch("src.finalize.main.pychee_lib.LycheeClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            with patch.dict("os.environ", env, clear=True):
                _create_lychee_client()

        mock_cls.assert_called_once_with("http://lychee.host")

    def test_logs_in_with_env_credentials(self) -> None:
        """LYCHEE_USER / LYCHEE_PASSWORD でログインすること。"""
        env = {
            "LYCHEE_URL": "http://lychee.host",
            "LYCHEE_USER": "lychee_user",
            "LYCHEE_PASSWORD": "lychee_pass",
        }
        mock_inner = MagicMock()
        with patch("src.finalize.main.pychee_lib.LycheeClient", return_value=mock_inner):
            with patch.dict("os.environ", env, clear=True):
                result = _create_lychee_client()

        mock_inner.login.assert_called_once_with("lychee_user", "lychee_pass")
        assert isinstance(result, LycheeApiClient)


# ---------------------------------------------------------------------------
# FinalizeRepository
# ---------------------------------------------------------------------------


class TestFinalizeRepository:
    """FinalizeRepository のテスト。"""

    def _make_repo_with_engine(self):
        """テスト用リポジトリと mock Engine を両方返す。"""
        mock_engine = MagicMock()
        return FinalizeRepository(engine=mock_engine), mock_engine

    def _setup_conn(self, mock_engine, rows=None):
        """mock Engine に connect() コンテキストマネージャをセットアップする。"""
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        if rows is not None:
            mock_result = MagicMock()
            mock_result.fetchall.return_value = rows
            mock_conn.execute.return_value = mock_result
        return mock_conn

    # --- getActors ---

    def test_get_actors_returns_actor_ids_from_db(self) -> None:
        """sorting_state テーブルから被写体 ID 一覧を返すこと。"""
        repo, mock_engine = self._make_repo_with_engine()
        rows = [
            SimpleNamespace(actor_id="actor_a"),
            SimpleNamespace(actor_id="actor_b"),
        ]
        self._setup_conn(mock_engine, rows=rows)

        result = repo.getActors()

        assert result == ["actor_a", "actor_b"]

    def test_get_actors_executes_distinct_query(self) -> None:
        """DISTINCT actor_id を ORDER BY で取得するクエリが実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.getActors()

        mock_conn.execute.assert_called_once()

    def test_get_actors_returns_empty_when_no_rows(self) -> None:
        """テーブルが空の場合、空リストを返すこと。"""
        repo, mock_engine = self._make_repo_with_engine()
        self._setup_conn(mock_engine, rows=[])

        result = repo.getActors()

        assert result == []

    # --- loadFinalizedEntries ---

    def test_load_finalized_entries_returns_ok_ng_entries(self) -> None:
        """ok / ng のエントリを dict リストで返すこと。"""
        repo, mock_engine = self._make_repo_with_engine()
        rows = [
            SimpleNamespace(filename="ok.jpg", shooting_date="2026-04-01", score=0.9, selection_state="ok", selected_at=None),
            SimpleNamespace(filename="ng.jpg", shooting_date="2026-04-01", score=0.1, selection_state="ng", selected_at=None),
        ]
        self._setup_conn(mock_engine, rows=rows)

        result = repo.loadFinalizedEntries("actor_a")

        assert len(result) == 2
        assert result[0]["filename"] == "ok.jpg"
        assert result[1]["filename"] == "ng.jpg"

    def test_load_finalized_entries_queries_with_actor_id_and_state(self) -> None:
        """actor_id と selectionState IN ('ok', 'ng') でクエリが実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.loadFinalizedEntries("actor_a")

        mock_conn.execute.assert_called_once()

    def test_load_finalized_entries_returns_empty_when_no_rows(self) -> None:
        """対象 actor の ok/ng エントリが無い場合、空リストを返すこと。"""
        repo, mock_engine = self._make_repo_with_engine()
        self._setup_conn(mock_engine, rows=[])

        result = repo.loadFinalizedEntries("actor_a")

        assert result == []

    # --- updatePublic ---

    def test_update_public_executes_update_sql(self) -> None:
        """UPDATE sorting_state SET public = TRUE の SQL が実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        repo.updatePublic("actor_a")

        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_update_public_commits_after_execute(self) -> None:
        """execute 後に commit が呼ばれること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        repo.updatePublic("actor_a")

        mock_conn.commit.assert_called_once_with()

    def test_update_public_passes_correct_actor(self) -> None:
        """正しい actor_id でクエリが実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        repo.updatePublic("alice")

        mock_conn.execute.assert_called_once()

    # --- loadFinalizedEntries (finalize=false フィルタ) ---

    def test_load_finalized_entries_filters_by_finalize_false(self) -> None:
        """finalize=false のエントリのみ取得するクエリが実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.loadFinalizedEntries("actor_a")

        mock_conn.execute.assert_called_once()

    # --- updateFinalize ---

    def test_update_finalize_executes_update_sql(self) -> None:
        """UPDATE sorting_state SET finalize = TRUE の SQL が実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        repo.updateFinalize("actor_a", "img.jpg", "2026-04-01")

        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_update_finalize_commits_after_execute(self) -> None:
        """execute 後に commit が呼ばれること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        repo.updateFinalize("actor_a", "img.jpg", "2026-04-01")

        mock_conn.commit.assert_called_once_with()

    def test_update_finalize_passes_correct_params(self) -> None:
        """正しい actor_id / filename / shooting_date でクエリが実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        repo.updateFinalize("alice", "photo.jpg", "2026-05-01")

        mock_conn.execute.assert_called_once()

    # --- loadNgNotRemovedEntries ---

    def test_load_ng_not_removed_entries_returns_ng_entries(self) -> None:
        """selection_state='ng' かつ remove=false のエントリを dict リストで返すこと。"""
        repo, mock_engine = self._make_repo_with_engine()
        rows = [
            SimpleNamespace(filename="ng.jpg", shooting_date="2026-04-01", selection_state="ng"),
        ]
        self._setup_conn(mock_engine, rows=rows)

        result = repo.loadNgNotRemovedEntries("actor_a")

        assert len(result) == 1
        assert result[0]["filename"] == "ng.jpg"
        assert result[0]["shootingDate"] == "2026-04-01"
        assert result[0]["selectionState"] == "ng"

    def test_load_ng_not_removed_entries_executes_correct_query(self) -> None:
        """actor_id / selection_state='ng' / remove=false でクエリが実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.loadNgNotRemovedEntries("actor_a")

        mock_conn.execute.assert_called_once()

    def test_load_ng_not_removed_entries_returns_empty_when_no_rows(self) -> None:
        """対象 actor の NG エントリが無い場合、空リストを返すこと。"""
        repo, mock_engine = self._make_repo_with_engine()
        self._setup_conn(mock_engine, rows=[])

        result = repo.loadNgNotRemovedEntries("actor_a")

        assert result == []

    # --- updateRemove ---

    def test_update_remove_executes_update_sql(self) -> None:
        """UPDATE sorting_state SET remove = TRUE の SQL が実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        repo.updateRemove("actor_a", "img.jpg", "2026-04-01")

        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_update_remove_commits_after_execute(self) -> None:
        """execute 後に commit が呼ばれること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        repo.updateRemove("actor_a", "img.jpg", "2026-04-01")

        mock_conn.commit.assert_called_once_with()

    def test_update_remove_passes_correct_params(self) -> None:
        """正しい actor_id / filename / shooting_date でクエリが実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        repo.updateRemove("alice", "photo.jpg", "2026-05-01")

        mock_conn.execute.assert_called_once()


# ---------------------------------------------------------------------------
# LycheeRepository
# ---------------------------------------------------------------------------


class TestLycheeRepository:
    """LycheeRepository のテスト。"""

    def _make_repo(self):
        """テスト用リポジトリと mock Engine を返す。"""
        mock_engine = MagicMock()
        return LycheeRepository(engine=mock_engine), mock_engine

    def _setup_conn(self, mock_engine, rows=None):
        """mock Engine に connect() コンテキストマネージャをセットアップする。"""
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        if rows is not None:
            mock_result = MagicMock()
            mock_result.fetchall.return_value = rows
            mock_conn.execute.return_value = mock_result
        return mock_conn

    # --- getAlbumsByParentId ---

    def test_get_albums_by_parent_id_returns_albums(self) -> None:
        """親アルバム ID 配下のアルバム一覧を dict リストで返すこと。"""
        repo, mock_engine = self._make_repo()
        rows = [
            SimpleNamespace(id="album1", title="2026.04.01"),
            SimpleNamespace(id="album2", title="2026.04.02"),
        ]
        self._setup_conn(mock_engine, rows=rows)

        result = repo.getAlbumsByParentId("root_id")

        assert result == [
            {"id": "album1", "title": "2026.04.01"},
            {"id": "album2", "title": "2026.04.02"},
        ]

    def test_get_albums_by_parent_id_executes_sql(self) -> None:
        """SQL クエリが実行されること。"""
        repo, mock_engine = self._make_repo()
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.getAlbumsByParentId("root_id")

        mock_conn.execute.assert_called_once()

    def test_get_albums_by_parent_id_returns_empty_when_no_albums(self) -> None:
        """配下のアルバムが無い場合、空リストを返すこと。"""
        repo, mock_engine = self._make_repo()
        self._setup_conn(mock_engine, rows=[])

        result = repo.getAlbumsByParentId("root_id")

        assert result == []

    # --- getPhotoIdsByAlbumId ---

    def test_get_photo_ids_by_album_id_returns_photo_ids(self) -> None:
        """アルバム ID 配下の写真 ID リストを返すこと。"""
        repo, mock_engine = self._make_repo()
        rows = [
            SimpleNamespace(photo_id="photo1"),
            SimpleNamespace(photo_id="photo2"),
        ]
        self._setup_conn(mock_engine, rows=rows)

        result = repo.getPhotoIdsByAlbumId("album_id")

        assert result == ["photo1", "photo2"]

    def test_get_photo_ids_by_album_id_executes_sql(self) -> None:
        """SQL クエリが実行されること。"""
        repo, mock_engine = self._make_repo()
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.getPhotoIdsByAlbumId("album_id")

        mock_conn.execute.assert_called_once()

    def test_get_photo_ids_by_album_id_returns_empty_when_no_photos(self) -> None:
        """アルバムに写真が無い場合、空リストを返すこと。"""
        repo, mock_engine = self._make_repo()
        self._setup_conn(mock_engine, rows=[])

        result = repo.getPhotoIdsByAlbumId("album_id")

        assert result == []


# ---------------------------------------------------------------------------
# LycheeApiClient
# ---------------------------------------------------------------------------


class TestLycheeApiClient:
    """LycheeApiClient のテスト。"""

    def test_delete_photos_calls_pychee_delete_photo(self) -> None:
        """delete_photo が写真 ID リストで呼ばれること。"""
        mock_pychee = MagicMock()
        client = LycheeApiClient(mock_pychee)

        client.deletePhotos(["photo1", "photo2"])

        mock_pychee.delete_photo.assert_called_once_with(["photo1", "photo2"])

    def test_delete_photos_does_not_call_api_when_empty_list(self) -> None:
        """写真 ID が空リストの場合、API を呼ばないこと。"""
        mock_pychee = MagicMock()
        client = LycheeApiClient(mock_pychee)

        client.deletePhotos([])

        mock_pychee.delete_photo.assert_not_called()


# ---------------------------------------------------------------------------
# PhotoFinalizer
# ---------------------------------------------------------------------------


class TestPhotoFinalizer:
    """PhotoFinalizer のテスト。"""

    def test_move_to_confirmed_moves_file(self, tmp_path: Path) -> None:
        """data/images/{actor}/ の写真を data/confirmed/{actor}/ へ移動すること。"""
        images_dir = tmp_path / "images" / "actor_a"
        images_dir.mkdir(parents=True)
        src = images_dir / "img.jpg"
        src.write_text("data")
        finalizer = PhotoFinalizer(data_root=tmp_path)

        finalizer.moveToConfirmed("actor_a", "img.jpg")

        assert not src.exists()
        assert (tmp_path / "confirmed" / "actor_a" / "img.jpg").exists()

    def test_move_to_confirmed_creates_dst_dir(self, tmp_path: Path) -> None:
        """data/confirmed/{actor}/ ディレクトリが存在しない場合でも移動できること。"""
        images_dir = tmp_path / "images" / "actor_a"
        images_dir.mkdir(parents=True)
        (images_dir / "img.jpg").write_text("data")
        finalizer = PhotoFinalizer(data_root=tmp_path)

        finalizer.moveToConfirmed("actor_a", "img.jpg")

        assert (tmp_path / "confirmed" / "actor_a" / "img.jpg").exists()

    def test_delete_from_images_deletes_file(self, tmp_path: Path) -> None:
        """data/images/{actor}/ の写真を削除すること。"""
        images_dir = tmp_path / "images" / "actor_a"
        images_dir.mkdir(parents=True)
        target = images_dir / "img.jpg"
        target.write_text("data")
        finalizer = PhotoFinalizer(data_root=tmp_path)

        finalizer.deleteFromImages("actor_a", "img.jpg")

        assert not target.exists()

    def test_delete_from_images_does_nothing_when_file_not_exists(
        self, tmp_path: Path
    ) -> None:
        """ファイルが存在しない場合でも例外を発生させないこと。"""
        finalizer = PhotoFinalizer(data_root=tmp_path)

        # 例外が発生しないこと
        finalizer.deleteFromImages("actor_a", "nonexistent.jpg")


# ---------------------------------------------------------------------------
# _run_publish
# ---------------------------------------------------------------------------


class TestRunPublish:
    """_run_publish のテスト。"""

    def test_calls_get_actors_and_update_public_for_each_actor(self) -> None:
        """getActors() の結果に対して updatePublic() が各 actor に呼ばれること。"""
        repo = MagicMock(spec=FinalizeRepository)
        repo.getActors.return_value = ["actor_a", "actor_b"]

        _run_publish(repo)

        repo.getActors.assert_called_once_with()
        assert repo.updatePublic.call_count == 2
        repo.updatePublic.assert_any_call("actor_a")
        repo.updatePublic.assert_any_call("actor_b")

    def test_exits_early_when_no_actors(self) -> None:
        """被写体が存在しない場合、updatePublic が呼ばれないこと。"""
        repo = MagicMock(spec=FinalizeRepository)
        repo.getActors.return_value = []

        _run_publish(repo)

        repo.updatePublic.assert_not_called()

    def test_update_public_called_in_order(self) -> None:
        """updatePublic が各 actor に対して順番に呼ばれること。"""
        repo = MagicMock(spec=FinalizeRepository)
        repo.getActors.return_value = ["alice", "bob", "charlie"]

        call_order = []
        repo.updatePublic.side_effect = lambda a: call_order.append(a)

        _run_publish(repo)

        assert call_order == ["alice", "bob", "charlie"]

    def test_update_public_called_with_correct_actor(self) -> None:
        """正しい actor_id で updatePublic が呼ばれること。"""
        repo = MagicMock(spec=FinalizeRepository)
        repo.getActors.return_value = ["alice"]

        _run_publish(repo)

        repo.updatePublic.assert_called_once_with("alice")

    def test_no_file_operations_performed(self) -> None:
        """ファイル操作（shutil.move 等）は行われないこと。"""
        repo = MagicMock(spec=FinalizeRepository)
        repo.getActors.return_value = ["actor_a"]

        with patch("src.finalize.main.shutil") as mock_shutil:
            _run_publish(repo)

        mock_shutil.move.assert_not_called()


# ---------------------------------------------------------------------------
# _run_finalize_for_actor
# ---------------------------------------------------------------------------


class TestRunFinalizeForActor:
    """_run_finalize_for_actor のテスト。"""

    def _make_mock_repo(self, entries: list) -> MagicMock:
        """loadFinalizedEntries が entries を返す mock リポジトリを生成する。"""
        repo = MagicMock(spec=FinalizeRepository)
        repo.loadFinalizedEntries.return_value = entries
        return repo

    def test_moves_ok_entry_to_confirmed(self) -> None:
        """selectionState='ok' のエントリを confirmed へ移動すること。"""
        entries = [
            {
                "filename": "img.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.9,
                "selectionState": "ok",
                "selectedAt": "2026-04-06T12:00:00.000Z",
            }
        ]
        repo = self._make_mock_repo(entries)
        finalizer = MagicMock(spec=PhotoFinalizer)

        _run_finalize_for_actor("actor_a", repo, finalizer)

        finalizer.moveToConfirmed.assert_called_once_with("actor_a", "img.jpg")
        finalizer.deleteFromImages.assert_not_called()

    def test_deletes_ng_entry_from_images(self) -> None:
        """selectionState='ng' のエントリを削除すること。"""
        entries = [
            {
                "filename": "img.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.1,
                "selectionState": "ng",
                "selectedAt": "2026-04-06T12:00:00.000Z",
            }
        ]
        repo = self._make_mock_repo(entries)
        finalizer = MagicMock(spec=PhotoFinalizer)

        _run_finalize_for_actor("actor_a", repo, finalizer)

        finalizer.deleteFromImages.assert_called_once_with("actor_a", "img.jpg")
        finalizer.moveToConfirmed.assert_not_called()

    def test_processes_mixed_ok_and_ng_entries(self) -> None:
        """ok / ng エントリそれぞれが正しく処理されること。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.9,
                "selectionState": "ok",
                "selectedAt": "2026-04-06T12:00:00.000Z",
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.1,
                "selectionState": "ng",
                "selectedAt": "2026-04-06T12:00:00.000Z",
            },
        ]
        repo = self._make_mock_repo(entries)
        finalizer = MagicMock(spec=PhotoFinalizer)

        _run_finalize_for_actor("actor_a", repo, finalizer)

        finalizer.moveToConfirmed.assert_called_once_with("actor_a", "ok.jpg")
        finalizer.deleteFromImages.assert_called_once_with("actor_a", "ng.jpg")

    def test_load_finalized_entries_called_with_actor(self) -> None:
        """loadFinalizedEntries が正しい actor 名で呼ばれること。"""
        repo = self._make_mock_repo([])
        finalizer = MagicMock(spec=PhotoFinalizer)

        _run_finalize_for_actor("actor_b", repo, finalizer)

        repo.loadFinalizedEntries.assert_called_once_with("actor_b")

    def test_update_finalize_called_after_ok_entry(self) -> None:
        """ok エントリ処理後に updateFinalize が呼ばれること。"""
        entries = [{
            "filename": "img.jpg",
            "shootingDate": "2026-04-01",
            "score": 0.9,
            "selectionState": "ok",
            "selectedAt": "2026-04-06T12:00:00.000Z",
        }]
        repo = self._make_mock_repo(entries)
        finalizer = MagicMock(spec=PhotoFinalizer)

        _run_finalize_for_actor("actor_a", repo, finalizer)

        repo.updateFinalize.assert_called_once_with("actor_a", "img.jpg", "2026-04-01")

    def test_update_finalize_called_after_ng_entry(self) -> None:
        """ng エントリ処理後に updateFinalize が呼ばれること。"""
        entries = [{
            "filename": "img.jpg",
            "shootingDate": "2026-04-01",
            "score": 0.1,
            "selectionState": "ng",
            "selectedAt": "2026-04-06T12:00:00.000Z",
        }]
        repo = self._make_mock_repo(entries)
        finalizer = MagicMock(spec=PhotoFinalizer)

        _run_finalize_for_actor("actor_a", repo, finalizer)

        repo.updateFinalize.assert_called_once_with("actor_a", "img.jpg", "2026-04-01")

    def test_update_finalize_called_for_each_entry(self) -> None:
        """複数エントリそれぞれに updateFinalize が呼ばれること。"""
        entries = [
            {"filename": "ok.jpg", "shootingDate": "2026-04-01", "score": 0.9, "selectionState": "ok", "selectedAt": None},
            {"filename": "ng.jpg", "shootingDate": "2026-04-01", "score": 0.1, "selectionState": "ng", "selectedAt": None},
        ]
        repo = self._make_mock_repo(entries)
        finalizer = MagicMock(spec=PhotoFinalizer)

        _run_finalize_for_actor("actor_a", repo, finalizer)

        assert repo.updateFinalize.call_count == 2
        repo.updateFinalize.assert_any_call("actor_a", "ok.jpg", "2026-04-01")
        repo.updateFinalize.assert_any_call("actor_a", "ng.jpg", "2026-04-01")


# ---------------------------------------------------------------------------
# _run_lychee_remove
# ---------------------------------------------------------------------------


class TestRunLycheeRemove:
    """_run_lychee_remove のテスト。"""

    def _make_mocks(
        self,
        actors: list,
        ng_entries_map: dict,
        date_albums: list,
        actor_albums_map: dict,
        photo_ids_map: dict,
    ):
        """テスト用 mock を生成する。"""
        repo = MagicMock(spec=FinalizeRepository)
        repo.getActors.return_value = actors
        repo.loadNgNotRemovedEntries.side_effect = lambda actor: ng_entries_map.get(actor, [])

        lychee_repo = MagicMock(spec=LycheeRepository)

        def _get_albums(parent_id):
            if parent_id == "root_id":
                return date_albums
            return actor_albums_map.get(parent_id, [])

        lychee_repo.getAlbumsByParentId.side_effect = _get_albums
        lychee_repo.getPhotoIdsByAlbumId.side_effect = lambda album_id: photo_ids_map.get(album_id, [])

        lychee_client = MagicMock(spec=LycheeApiClient)
        return repo, lychee_repo, lychee_client

    def test_deletes_photos_from_lychee_for_ng_entries(self) -> None:
        """NG エントリに対応する lychee アルバムの写真が削除されること。"""
        ng_entries = [{"filename": "ng.jpg", "shootingDate": "2026-04-01", "selectionState": "ng"}]
        date_albums = [{"id": "date_album_1", "title": "2026.04.01"}]
        actor_albums = {"date_album_1": [{"id": "actor_album_1", "title": "actor_a"}]}
        photo_ids = {"actor_album_1": ["photo1", "photo2"]}

        repo, lychee_repo, lychee_client = self._make_mocks(
            actors=["actor_a"],
            ng_entries_map={"actor_a": ng_entries},
            date_albums=date_albums,
            actor_albums_map=actor_albums,
            photo_ids_map=photo_ids,
        )

        _run_lychee_remove(repo, lychee_repo, lychee_client, "root_id")

        lychee_client.deletePhotos.assert_called_once_with(["photo1", "photo2"])

    def test_updates_remove_after_deletion(self) -> None:
        """削除後に updateRemove が呼ばれること。"""
        ng_entries = [{"filename": "ng.jpg", "shootingDate": "2026-04-01", "selectionState": "ng"}]
        date_albums = [{"id": "date_album_1", "title": "2026.04.01"}]
        actor_albums = {"date_album_1": [{"id": "actor_album_1", "title": "actor_a"}]}
        photo_ids = {"actor_album_1": ["photo1"]}

        repo, lychee_repo, lychee_client = self._make_mocks(
            actors=["actor_a"],
            ng_entries_map={"actor_a": ng_entries},
            date_albums=date_albums,
            actor_albums_map=actor_albums,
            photo_ids_map=photo_ids,
        )

        _run_lychee_remove(repo, lychee_repo, lychee_client, "root_id")

        repo.updateRemove.assert_called_once_with("actor_a", "ng.jpg", "2026-04-01")

    def test_skips_when_no_ng_entries(self) -> None:
        """NG エントリが無い場合、削除も updateRemove も呼ばれないこと。"""
        repo, lychee_repo, lychee_client = self._make_mocks(
            actors=["actor_a"],
            ng_entries_map={"actor_a": []},
            date_albums=[],
            actor_albums_map={},
            photo_ids_map={},
        )

        _run_lychee_remove(repo, lychee_repo, lychee_client, "root_id")

        lychee_client.deletePhotos.assert_not_called()
        repo.updateRemove.assert_not_called()

    def test_skips_when_date_album_not_found(self) -> None:
        """撮影日アルバムが見つからない場合、削除も updateRemove も呼ばれないこと。"""
        ng_entries = [{"filename": "ng.jpg", "shootingDate": "2026-04-01", "selectionState": "ng"}]

        repo, lychee_repo, lychee_client = self._make_mocks(
            actors=["actor_a"],
            ng_entries_map={"actor_a": ng_entries},
            date_albums=[],
            actor_albums_map={},
            photo_ids_map={},
        )

        _run_lychee_remove(repo, lychee_repo, lychee_client, "root_id")

        lychee_client.deletePhotos.assert_not_called()
        repo.updateRemove.assert_not_called()

    def test_skips_when_actor_album_not_found(self) -> None:
        """被写体アルバムが見つからない場合、削除も updateRemove も呼ばれないこと。"""
        ng_entries = [{"filename": "ng.jpg", "shootingDate": "2026-04-01", "selectionState": "ng"}]
        date_albums = [{"id": "date_album_1", "title": "2026.04.01"}]
        actor_albums = {"date_album_1": []}

        repo, lychee_repo, lychee_client = self._make_mocks(
            actors=["actor_a"],
            ng_entries_map={"actor_a": ng_entries},
            date_albums=date_albums,
            actor_albums_map=actor_albums,
            photo_ids_map={},
        )

        _run_lychee_remove(repo, lychee_repo, lychee_client, "root_id")

        lychee_client.deletePhotos.assert_not_called()
        repo.updateRemove.assert_not_called()

    def test_updates_remove_even_when_no_photos_in_album(self) -> None:
        """アルバムに写真が無くても updateRemove が呼ばれること。"""
        ng_entries = [{"filename": "ng.jpg", "shootingDate": "2026-04-01", "selectionState": "ng"}]
        date_albums = [{"id": "date_album_1", "title": "2026.04.01"}]
        actor_albums = {"date_album_1": [{"id": "actor_album_1", "title": "actor_a"}]}
        photo_ids = {"actor_album_1": []}

        repo, lychee_repo, lychee_client = self._make_mocks(
            actors=["actor_a"],
            ng_entries_map={"actor_a": ng_entries},
            date_albums=date_albums,
            actor_albums_map=actor_albums,
            photo_ids_map=photo_ids,
        )

        _run_lychee_remove(repo, lychee_repo, lychee_client, "root_id")

        lychee_client.deletePhotos.assert_not_called()
        repo.updateRemove.assert_called_once_with("actor_a", "ng.jpg", "2026-04-01")

    def test_groups_entries_by_shooting_date(self) -> None:
        """同じ撮影日の複数エントリは1回の削除にまとめられること。"""
        ng_entries = [
            {"filename": "ng1.jpg", "shootingDate": "2026-04-01", "selectionState": "ng"},
            {"filename": "ng2.jpg", "shootingDate": "2026-04-01", "selectionState": "ng"},
            {"filename": "ng3.jpg", "shootingDate": "2026-04-02", "selectionState": "ng"},
        ]
        date_albums = [
            {"id": "date_album_1", "title": "2026.04.01"},
            {"id": "date_album_2", "title": "2026.04.02"},
        ]
        actor_albums = {
            "date_album_1": [{"id": "actor_album_1", "title": "actor_a"}],
            "date_album_2": [{"id": "actor_album_2", "title": "actor_a"}],
        }
        photo_ids = {
            "actor_album_1": ["photo1"],
            "actor_album_2": ["photo2"],
        }

        repo, lychee_repo, lychee_client = self._make_mocks(
            actors=["actor_a"],
            ng_entries_map={"actor_a": ng_entries},
            date_albums=date_albums,
            actor_albums_map=actor_albums,
            photo_ids_map=photo_ids,
        )

        _run_lychee_remove(repo, lychee_repo, lychee_client, "root_id")

        assert lychee_client.deletePhotos.call_count == 2
        assert repo.updateRemove.call_count == 3

    def test_processes_multiple_actors(self) -> None:
        """複数被写体それぞれに対して削除処理が行われること。"""
        date_albums = [{"id": "date_album_1", "title": "2026.04.01"}]
        actor_albums = {
            "date_album_1": [
                {"id": "actor_album_a", "title": "actor_a"},
                {"id": "actor_album_b", "title": "actor_b"},
            ],
        }
        photo_ids = {
            "actor_album_a": ["photo1"],
            "actor_album_b": ["photo2"],
        }
        ng_entries_map = {
            "actor_a": [{"filename": "ng_a.jpg", "shootingDate": "2026-04-01", "selectionState": "ng"}],
            "actor_b": [{"filename": "ng_b.jpg", "shootingDate": "2026-04-01", "selectionState": "ng"}],
        }

        repo, lychee_repo, lychee_client = self._make_mocks(
            actors=["actor_a", "actor_b"],
            ng_entries_map=ng_entries_map,
            date_albums=date_albums,
            actor_albums_map=actor_albums,
            photo_ids_map=photo_ids,
        )

        _run_lychee_remove(repo, lychee_repo, lychee_client, "root_id")

        assert lychee_client.deletePhotos.call_count == 2
        assert repo.updateRemove.call_count == 2

    def test_converts_date_format_for_album_title(self) -> None:
        """shooting_date (YYYY-MM-DD) を lychee アルバムタイトル (YYYY.MM.DD) に変換すること。"""
        ng_entries = [{"filename": "ng.jpg", "shootingDate": "2026-04-15", "selectionState": "ng"}]
        date_albums = [{"id": "date_album_1", "title": "2026.04.15"}]
        actor_albums = {"date_album_1": [{"id": "actor_album_1", "title": "actor_a"}]}
        photo_ids = {"actor_album_1": ["photo1"]}

        repo, lychee_repo, lychee_client = self._make_mocks(
            actors=["actor_a"],
            ng_entries_map={"actor_a": ng_entries},
            date_albums=date_albums,
            actor_albums_map=actor_albums,
            photo_ids_map=photo_ids,
        )

        _run_lychee_remove(repo, lychee_repo, lychee_client, "root_id")

        lychee_client.deletePhotos.assert_called_once_with(["photo1"])


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    """run() のテスト。"""

    def _make_deps(self, tmp_path: Path):
        """テスト用の依存オブジェクトを生成する。"""
        data_root = tmp_path / "data"
        data_root.mkdir()
        mock_engine = MagicMock()
        repo = MagicMock(spec=FinalizeRepository)
        finalizer = MagicMock(spec=PhotoFinalizer)
        return data_root, mock_engine, repo, finalizer

    def test_run_calls_load_env(self, tmp_path: Path) -> None:
        """_load_env が呼ばれること。"""
        data_root, mock_engine, repo, finalizer = self._make_deps(tmp_path)
        repo.getActors.return_value = []
        lychee_repo = MagicMock(spec=LycheeRepository)
        lychee_client = MagicMock(spec=LycheeApiClient)

        with patch("src.finalize.main._load_env") as mock_env:
            with patch("src.finalize.main._run_lychee_remove"):
                with patch.dict("os.environ", {"LYCHEE_ROOT_ALBUM_ID": "root"}):
                    run(
                        mode="finalize",
                        repository=repo,
                        finalizer=finalizer,
                        data_root=data_root,
                        engine=mock_engine,
                        lychee_repository=lychee_repo,
                        lychee_client=lychee_client,
                    )

        mock_env.assert_called_once_with()

    def test_run_processes_all_actors_in_finalize_mode(self, tmp_path: Path) -> None:
        """mode='finalize' のとき全被写体に対して _run_finalize_for_actor が呼ばれること。"""
        data_root, mock_engine, repo, finalizer = self._make_deps(tmp_path)
        repo.getActors.return_value = ["actor_a", "actor_b"]
        lychee_repo = MagicMock(spec=LycheeRepository)
        lychee_client = MagicMock(spec=LycheeApiClient)

        with patch("src.finalize.main._load_env"):
            with patch("src.finalize.main._run_finalize_for_actor") as mock_finalize:
                with patch("src.finalize.main._run_lychee_remove"):
                    with patch.dict("os.environ", {"LYCHEE_ROOT_ALBUM_ID": "root"}):
                        run(
                            mode="finalize",
                            repository=repo,
                            finalizer=finalizer,
                            data_root=data_root,
                            engine=mock_engine,
                            lychee_repository=lychee_repo,
                            lychee_client=lychee_client,
                        )

        assert mock_finalize.call_count == 2
        calls = mock_finalize.call_args_list
        assert calls[0][0][0] == "actor_a"
        assert calls[1][0][0] == "actor_b"

    def test_run_calls_run_publish_in_publish_mode(self, tmp_path: Path) -> None:
        """mode='publish' のとき _run_publish が repository のみで呼ばれること。"""
        data_root, mock_engine, repo, finalizer = self._make_deps(tmp_path)

        with patch("src.finalize.main._load_env"):
            with patch("src.finalize.main._run_publish") as mock_publish:
                run(
                    mode="publish",
                    repository=repo,
                    engine=mock_engine,
                )

        mock_publish.assert_called_once_with(repo)

    def test_run_calls_lychee_remove_in_finalize_mode(self, tmp_path: Path) -> None:
        """mode='finalize' のとき _run_lychee_remove が呼ばれること。"""
        data_root, mock_engine, repo, finalizer = self._make_deps(tmp_path)
        repo.getActors.return_value = []
        lychee_repo = MagicMock(spec=LycheeRepository)
        lychee_client = MagicMock(spec=LycheeApiClient)

        with patch("src.finalize.main._load_env"):
            with patch("src.finalize.main._run_lychee_remove") as mock_lychee_remove:
                with patch.dict("os.environ", {"LYCHEE_ROOT_ALBUM_ID": "root123"}):
                    run(
                        mode="finalize",
                        repository=repo,
                        finalizer=finalizer,
                        data_root=data_root,
                        engine=mock_engine,
                        lychee_repository=lychee_repo,
                        lychee_client=lychee_client,
                    )

        mock_lychee_remove.assert_called_once_with(repo, lychee_repo, lychee_client, "root123")

    def test_run_uses_album_id_param_over_env(self, tmp_path: Path) -> None:
        """album_id 引数が LYCHEE_ROOT_ALBUM_ID 環境変数より優先されること。"""
        data_root, mock_engine, repo, finalizer = self._make_deps(tmp_path)
        repo.getActors.return_value = []
        lychee_repo = MagicMock(spec=LycheeRepository)
        lychee_client = MagicMock(spec=LycheeApiClient)

        with patch("src.finalize.main._load_env"):
            with patch("src.finalize.main._run_lychee_remove") as mock_lychee_remove:
                with patch.dict("os.environ", {"LYCHEE_ROOT_ALBUM_ID": "env_root"}):
                    run(
                        mode="finalize",
                        repository=repo,
                        finalizer=finalizer,
                        data_root=data_root,
                        engine=mock_engine,
                        album_id="param_root",
                        lychee_repository=lychee_repo,
                        lychee_client=lychee_client,
                    )

        mock_lychee_remove.assert_called_once_with(repo, lychee_repo, lychee_client, "param_root")

    def test_run_does_not_call_lychee_remove_in_publish_mode(self, tmp_path: Path) -> None:
        """mode='publish' のとき _run_lychee_remove は呼ばれないこと。"""
        data_root, mock_engine, repo, finalizer = self._make_deps(tmp_path)

        with patch("src.finalize.main._load_env"):
            with patch("src.finalize.main._run_publish"):
                with patch("src.finalize.main._run_lychee_remove") as mock_lychee_remove:
                    run(mode="publish", repository=repo, engine=mock_engine)

        mock_lychee_remove.assert_not_called()

    def test_run_creates_default_instances_from_env_finalize(self, tmp_path: Path) -> None:
        """mode='finalize' で依存オブジェクトを省略した場合、環境変数からインスタンスを生成すること。"""
        data_root = tmp_path / "data"
        mock_engine = MagicMock()
        mock_lychee_engine = MagicMock()

        with patch("src.finalize.main._load_env"):
            with patch("src.finalize.main._create_engine", return_value=mock_engine):
                with patch("src.finalize.main._create_lychee_engine", return_value=mock_lychee_engine):
                    with patch("src.finalize.main._create_lychee_client") as mock_create_lychee_client:
                        mock_create_lychee_client.return_value = MagicMock(spec=LycheeApiClient)
                        with patch.dict("os.environ", {"DATA_ROOT": str(data_root), "LYCHEE_ROOT_ALBUM_ID": "root"}):
                            with patch("src.finalize.main.FinalizeRepository") as mock_repo_cls:
                                with patch("src.finalize.main.PhotoFinalizer") as mock_finalizer_cls:
                                    with patch("src.finalize.main.LycheeRepository") as mock_lychee_repo_cls:
                                        with patch("src.finalize.main._run_lychee_remove"):
                                            mock_repo = MagicMock(spec=FinalizeRepository)
                                            mock_repo.getActors.return_value = []
                                            mock_repo_cls.return_value = mock_repo
                                            mock_finalizer_cls.return_value = MagicMock(spec=PhotoFinalizer)
                                            mock_lychee_repo_cls.return_value = MagicMock(spec=LycheeRepository)

                                            run(mode="finalize")

        mock_repo_cls.assert_called_once_with(mock_engine)
        mock_finalizer_cls.assert_called_once_with(data_root)
        mock_lychee_repo_cls.assert_called_once_with(mock_lychee_engine)
        mock_create_lychee_client.assert_called_once()

    def test_run_creates_default_instances_from_env_publish(self, tmp_path: Path) -> None:
        """mode='publish' で依存オブジェクトを省略した場合、repository のみを生成して _run_publish に渡すこと。"""
        mock_engine = MagicMock()

        with patch("src.finalize.main._load_env"):
            with patch("src.finalize.main._create_engine", return_value=mock_engine):
                with patch("src.finalize.main.FinalizeRepository") as mock_repo_cls:
                    with patch("src.finalize.main._run_publish") as mock_run_publish:
                        mock_repo = MagicMock(spec=FinalizeRepository)
                        mock_repo_cls.return_value = mock_repo

                        run(mode="publish")

        mock_repo_cls.assert_called_once_with(mock_engine)
        mock_run_publish.assert_called_once_with(mock_repo)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    """main() の CLI 引数テスト。"""

    def test_main_calls_run_with_finalize_by_default(self) -> None:
        """引数なしのとき run(mode='finalize', album_id=None) が呼ばれること。"""
        with patch("sys.argv", ["main.py"]):
            with patch("src.finalize.main.run") as mock_run:
                main()

        mock_run.assert_called_once_with(mode="finalize", album_id=None)

    def test_main_calls_run_with_publish_flag(self) -> None:
        """--publish フラグのとき run(mode='publish') が呼ばれること。"""
        with patch("sys.argv", ["main.py", "--publish"]):
            with patch("src.finalize.main.run") as mock_run:
                main()

        mock_run.assert_called_once_with(mode="publish")

    def test_main_passes_album_id_to_run(self) -> None:
        """--album_id 引数が run() に渡されること。"""
        with patch("sys.argv", ["main.py", "--album_id=root123"]):
            with patch("src.finalize.main.run") as mock_run:
                main()

        mock_run.assert_called_once_with(mode="finalize", album_id="root123")

    def test_main_passes_none_album_id_when_not_specified(self) -> None:
        """--album_id を省略したとき album_id=None で run() が呼ばれること。"""
        with patch("sys.argv", ["main.py"]):
            with patch("src.finalize.main.run") as mock_run:
                main()

        mock_run.assert_called_once_with(mode="finalize", album_id=None)
