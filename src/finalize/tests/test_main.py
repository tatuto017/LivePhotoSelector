"""src.finalize.main のユニットテスト。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from src.finalize.main import (
    FinalizeRepository,
    PhotoFinalizer,
    _load_env,
    _run_finalize_for_actor,
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

        with patch("src.finalize.main._load_env") as mock_env:
            run(
                mode="finalize",
                repository=repo,
                finalizer=finalizer,
                data_root=data_root,
                engine=mock_engine,
            )

        mock_env.assert_called_once_with()

    def test_run_processes_all_actors_in_finalize_mode(self, tmp_path: Path) -> None:
        """mode='finalize' のとき全被写体に対して _run_finalize_for_actor が呼ばれること。"""
        data_root, mock_engine, repo, finalizer = self._make_deps(tmp_path)
        repo.getActors.return_value = ["actor_a", "actor_b"]

        with patch("src.finalize.main._load_env"):
            with patch(
                "src.finalize.main._run_finalize_for_actor"
            ) as mock_finalize:
                run(
                    mode="finalize",
                    repository=repo,
                    finalizer=finalizer,
                    data_root=data_root,
                    engine=mock_engine,
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

    def test_run_creates_default_instances_from_env_finalize(self, tmp_path: Path) -> None:
        """mode='finalize' で依存オブジェクトを省略した場合、環境変数からインスタンスを生成すること。"""
        data_root = tmp_path / "data"
        mock_engine = MagicMock()

        with patch("src.finalize.main._load_env"):
            with patch("src.finalize.main._create_engine", return_value=mock_engine):
                with patch.dict("os.environ", {"DATA_ROOT": str(data_root)}):
                    with patch("src.finalize.main.FinalizeRepository") as mock_repo_cls:
                        with patch("src.finalize.main.PhotoFinalizer") as mock_finalizer_cls:
                            mock_repo = MagicMock(spec=FinalizeRepository)
                            mock_repo.getActors.return_value = []
                            mock_repo_cls.return_value = mock_repo
                            mock_finalizer_cls.return_value = MagicMock(spec=PhotoFinalizer)

                            run(mode="finalize")

        mock_repo_cls.assert_called_once_with(mock_engine)
        mock_finalizer_cls.assert_called_once_with(data_root)

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
        """引数なしのとき run(mode='finalize') が呼ばれること。"""
        with patch("sys.argv", ["main.py"]):
            with patch("src.finalize.main.run") as mock_run:
                main()

        mock_run.assert_called_once_with(mode="finalize")

    def test_main_calls_run_with_publish_flag(self) -> None:
        """--publish フラグのとき run(mode='publish') が呼ばれること。"""
        with patch("sys.argv", ["main.py", "--publish"]):
            with patch("src.finalize.main.run") as mock_run:
                main()

        mock_run.assert_called_once_with(mode="publish")
