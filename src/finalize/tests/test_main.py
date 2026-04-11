"""src.finalize.main のユニットテスト。"""

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.finalize.main import (
    FinalizeRepository,
    PhotoFinalizer,
    _load_env,
    _run_finalize_for_actor,
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

    def test_get_actors_returns_empty_when_data_dir_not_exists(
        self, tmp_path: Path
    ) -> None:
        """data ディレクトリが存在しない場合、空リストを返すこと。"""
        repo = FinalizeRepository(tmp_path, tmp_path)

        result = repo.getActors()

        assert result == []

    def test_get_actors_returns_sorted_actor_ids(self, tmp_path: Path) -> None:
        """*_analysis.json ファイルから被写体 ID をソート済みで返すこと。"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "actor_b_analysis.json").touch()
        (data_dir / "actor_a_analysis.json").touch()
        repo = FinalizeRepository(tmp_path, tmp_path)

        result = repo.getActors()

        assert result == ["actor_a", "actor_b"]

    def test_load_actor_entries_returns_empty_when_file_not_exists(
        self, tmp_path: Path
    ) -> None:
        """{actor}_analysis.json が存在しない場合、空リストを返すこと。"""
        repo = FinalizeRepository(tmp_path, tmp_path)

        result = repo.loadActorEntries("actor_a")

        assert result == []

    def test_load_actor_entries_returns_parsed_json(self, tmp_path: Path) -> None:
        """{actor}_analysis.json を dict リストとして返すこと。"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        entries = [
            {
                "filename": "img.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.9,
                "selectionState": "ok",
                "selectedAt": "2026-04-06T12:00:00.000Z",
            }
        ]
        (data_dir / "actor_a_analysis.json").write_text(
            json.dumps(entries), encoding="utf-8"
        )
        repo = FinalizeRepository(tmp_path, tmp_path)

        result = repo.loadActorEntries("actor_a")

        assert result == entries

    def test_save_actor_entries_creates_file(self, tmp_path: Path) -> None:
        """{actor}_analysis.json を作成して保存すること。"""
        repo = FinalizeRepository(tmp_path, tmp_path)
        entries = [{"filename": "img.jpg", "selectionState": "pending"}]

        repo.saveActorEntries("actor_a", entries)

        path = tmp_path / "data" / "actor_a_analysis.json"
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8")) == entries

    def test_save_actor_entries_creates_parent_dirs(self, tmp_path: Path) -> None:
        """data ディレクトリが存在しない場合でも保存できること。"""
        repo = FinalizeRepository(tmp_path, tmp_path)

        repo.saveActorEntries("actor_a", [])

        assert (tmp_path / "data" / "actor_a_analysis.json").exists()

    def test_load_analysis_json_returns_empty_when_file_not_exists(
        self, tmp_path: Path
    ) -> None:
        """analysis.json が存在しない場合、空辞書を返すこと。"""
        repo = FinalizeRepository(tmp_path, tmp_path)

        result = repo.loadAnalysisJson()

        assert result == {}

    def test_load_analysis_json_returns_parsed_dict(self, tmp_path: Path) -> None:
        """analysis.json を辞書として返すこと。"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        data = {"actor_a": [{"filename": "img.jpg", "selectionState": "ok"}]}
        (data_dir / "analysis.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        repo = FinalizeRepository(tmp_path, tmp_path)

        result = repo.loadAnalysisJson()

        assert result == data

    def test_save_analysis_json_creates_file(self, tmp_path: Path) -> None:
        """analysis.json を作成して保存すること。"""
        repo = FinalizeRepository(tmp_path, tmp_path)
        data = {"actor_a": [{"filename": "img.jpg", "selectionState": "ok"}]}

        repo.saveAnalysisJson(data)

        path = tmp_path / "data" / "analysis.json"
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8")) == data

    def test_save_analysis_json_creates_parent_dirs(self, tmp_path: Path) -> None:
        """data ディレクトリが存在しない場合でも保存できること。"""
        repo = FinalizeRepository(tmp_path, tmp_path)

        repo.saveAnalysisJson({})

        assert (tmp_path / "data" / "analysis.json").exists()


# ---------------------------------------------------------------------------
# PhotoFinalizer
# ---------------------------------------------------------------------------


class TestPhotoFinalizer:
    """PhotoFinalizer のテスト。"""

    def test_move_to_confirmed_moves_file(self, tmp_path: Path) -> None:
        """images/{actor}/ の写真を confirmed/{actor}/ へ移動すること。"""
        images_dir = tmp_path / "images" / "actor_a"
        images_dir.mkdir(parents=True)
        src = images_dir / "img.jpg"
        src.write_text("data")
        finalizer = PhotoFinalizer(tmp_path)

        finalizer.moveToConfirmed("actor_a", "img.jpg")

        assert not src.exists()
        assert (tmp_path / "confirmed" / "actor_a" / "img.jpg").exists()

    def test_move_to_confirmed_creates_dst_dir(self, tmp_path: Path) -> None:
        """confirmed/{actor}/ ディレクトリが存在しない場合でも移動できること。"""
        images_dir = tmp_path / "images" / "actor_a"
        images_dir.mkdir(parents=True)
        (images_dir / "img.jpg").write_text("data")
        finalizer = PhotoFinalizer(tmp_path)

        finalizer.moveToConfirmed("actor_a", "img.jpg")

        assert (tmp_path / "confirmed" / "actor_a" / "img.jpg").exists()

    def test_delete_from_images_deletes_file(self, tmp_path: Path) -> None:
        """images/{actor}/ の写真を削除すること。"""
        images_dir = tmp_path / "images" / "actor_a"
        images_dir.mkdir(parents=True)
        target = images_dir / "img.jpg"
        target.write_text("data")
        finalizer = PhotoFinalizer(tmp_path)

        finalizer.deleteFromImages("actor_a", "img.jpg")

        assert not target.exists()

    def test_delete_from_images_does_nothing_when_file_not_exists(
        self, tmp_path: Path
    ) -> None:
        """ファイルが存在しない場合でも例外を発生させないこと。"""
        finalizer = PhotoFinalizer(tmp_path)

        # 例外が発生しないこと
        finalizer.deleteFromImages("actor_a", "nonexistent.jpg")


# ---------------------------------------------------------------------------
# _run_finalize_for_actor
# ---------------------------------------------------------------------------


class TestRunFinalizeForActor:
    """_run_finalize_for_actor のテスト。"""

    def test_moves_ok_entry_to_confirmed(self) -> None:
        """selectionState='ok' のエントリを confirmed へ移動すること。"""
        repo = MagicMock(spec=FinalizeRepository)
        finalizer = MagicMock(spec=PhotoFinalizer)
        repo.loadActorEntries.return_value = [
            {
                "filename": "img.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.9,
                "selectionState": "ok",
                "selectedAt": "2026-04-06T12:00:00.000Z",
            }
        ]
        analysis_data: dict = {}

        _run_finalize_for_actor("actor_a", repo, finalizer, analysis_data)

        finalizer.moveToConfirmed.assert_called_once_with("actor_a", "img.jpg")
        finalizer.deleteFromImages.assert_not_called()

    def test_deletes_ng_entry_from_images(self) -> None:
        """selectionState='ng' のエントリを削除すること。"""
        repo = MagicMock(spec=FinalizeRepository)
        finalizer = MagicMock(spec=PhotoFinalizer)
        repo.loadActorEntries.return_value = [
            {
                "filename": "img.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.1,
                "selectionState": "ng",
                "selectedAt": "2026-04-06T12:00:00.000Z",
            }
        ]
        analysis_data: dict = {}

        _run_finalize_for_actor("actor_a", repo, finalizer, analysis_data)

        finalizer.deleteFromImages.assert_called_once_with("actor_a", "img.jpg")
        finalizer.moveToConfirmed.assert_not_called()

    def test_keeps_pending_entry_in_actor_json(self) -> None:
        """selectionState='pending' のエントリは {actor}_analysis.json に残すこと。"""
        repo = MagicMock(spec=FinalizeRepository)
        finalizer = MagicMock(spec=PhotoFinalizer)
        pending_entry = {
            "filename": "img.jpg",
            "shootingDate": "2026-04-01",
            "score": 0.5,
            "selectionState": "pending",
            "selectedAt": None,
        }
        repo.loadActorEntries.return_value = [pending_entry]
        analysis_data: dict = {}

        _run_finalize_for_actor("actor_a", repo, finalizer, analysis_data)

        finalizer.moveToConfirmed.assert_not_called()
        finalizer.deleteFromImages.assert_not_called()
        saved = repo.saveActorEntries.call_args[0][1]
        assert len(saved) == 1
        assert saved[0]["filename"] == "img.jpg"

    def test_ok_ng_entries_removed_from_actor_json(self) -> None:
        """ok / ng エントリは {actor}_analysis.json から除去されること。"""
        repo = MagicMock(spec=FinalizeRepository)
        finalizer = MagicMock(spec=PhotoFinalizer)
        repo.loadActorEntries.return_value = [
            {
                "filename": "ok.jpg",
                "selectionState": "ok",
                "shootingDate": "2026-04-01",
                "score": 0.9,
                "selectedAt": "2026-04-06T12:00:00.000Z",
            },
            {
                "filename": "ng.jpg",
                "selectionState": "ng",
                "shootingDate": "2026-04-01",
                "score": 0.1,
                "selectedAt": "2026-04-06T12:00:00.000Z",
            },
        ]
        analysis_data: dict = {}

        _run_finalize_for_actor("actor_a", repo, finalizer, analysis_data)

        saved = repo.saveActorEntries.call_args[0][1]
        assert saved == []

    def test_ok_ng_entries_moved_to_analysis_json(self) -> None:
        """ok / ng エントリが analysis.json に追加されること。"""
        repo = MagicMock(spec=FinalizeRepository)
        finalizer = MagicMock(spec=PhotoFinalizer)
        ok_entry = {
            "filename": "ok.jpg",
            "selectionState": "ok",
            "shootingDate": "2026-04-01",
            "score": 0.9,
            "selectedAt": "2026-04-06T12:00:00.000Z",
        }
        ng_entry = {
            "filename": "ng.jpg",
            "selectionState": "ng",
            "shootingDate": "2026-04-01",
            "score": 0.1,
            "selectedAt": "2026-04-06T12:00:00.000Z",
        }
        repo.loadActorEntries.return_value = [ok_entry, ng_entry]
        analysis_data: dict = {}

        _run_finalize_for_actor("actor_a", repo, finalizer, analysis_data)

        assert "actor_a" in analysis_data
        filenames = [e["filename"] for e in analysis_data["actor_a"]]
        assert "ok.jpg" in filenames
        assert "ng.jpg" in filenames

    def test_does_not_duplicate_entries_in_analysis_json(self) -> None:
        """analysis.json に既存のエントリは重複追加されないこと。"""
        repo = MagicMock(spec=FinalizeRepository)
        finalizer = MagicMock(spec=PhotoFinalizer)
        repo.loadActorEntries.return_value = [
            {
                "filename": "img.jpg",
                "selectionState": "ok",
                "shootingDate": "2026-04-01",
                "score": 0.9,
                "selectedAt": "2026-04-06T12:00:00.000Z",
            }
        ]
        # 既に analysis.json に存在するエントリ
        analysis_data: dict = {
            "actor_a": [{"filename": "img.jpg", "selectionState": "ok"}]
        }

        _run_finalize_for_actor("actor_a", repo, finalizer, analysis_data)

        assert len(analysis_data["actor_a"]) == 1

    def test_processes_mixed_entries(self) -> None:
        """ok / ng / pending が混在している場合、それぞれ正しく処理すること。"""
        repo = MagicMock(spec=FinalizeRepository)
        finalizer = MagicMock(spec=PhotoFinalizer)
        repo.loadActorEntries.return_value = [
            {
                "filename": "ok.jpg",
                "selectionState": "ok",
                "shootingDate": "2026-04-01",
                "score": 0.9,
                "selectedAt": "2026-04-06T12:00:00.000Z",
            },
            {
                "filename": "ng.jpg",
                "selectionState": "ng",
                "shootingDate": "2026-04-01",
                "score": 0.1,
                "selectedAt": "2026-04-06T12:00:00.000Z",
            },
            {
                "filename": "pending.jpg",
                "selectionState": "pending",
                "shootingDate": "2026-04-01",
                "score": 0.5,
                "selectedAt": None,
            },
        ]
        analysis_data: dict = {}

        _run_finalize_for_actor("actor_a", repo, finalizer, analysis_data)

        finalizer.moveToConfirmed.assert_called_once_with("actor_a", "ok.jpg")
        finalizer.deleteFromImages.assert_called_once_with("actor_a", "ng.jpg")
        saved = repo.saveActorEntries.call_args[0][1]
        assert len(saved) == 1
        assert saved[0]["filename"] == "pending.jpg"
        assert len(analysis_data["actor_a"]) == 2

    def test_save_actor_entries_called_with_actor(self) -> None:
        """saveActorEntries が正しい actor 名で呼ばれること。"""
        repo = MagicMock(spec=FinalizeRepository)
        finalizer = MagicMock(spec=PhotoFinalizer)
        repo.loadActorEntries.return_value = []
        analysis_data: dict = {}

        _run_finalize_for_actor("actor_b", repo, finalizer, analysis_data)

        repo.saveActorEntries.assert_called_once_with("actor_b", [])


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    """run() のテスト。"""

    def _make_deps(self, tmp_path: Path):
        """テスト用の依存オブジェクトを生成する。"""
        project_root = tmp_path / "project"
        one_drive_root = tmp_path / "onedrive"
        project_root.mkdir()
        one_drive_root.mkdir()
        repo = MagicMock(spec=FinalizeRepository)
        finalizer = MagicMock(spec=PhotoFinalizer)
        return project_root, one_drive_root, repo, finalizer

    def test_run_calls_load_env(self, tmp_path: Path) -> None:
        """_load_env が呼ばれること。"""
        project_root, one_drive_root, repo, finalizer = self._make_deps(tmp_path)
        repo.getActors.return_value = []
        repo.loadAnalysisJson.return_value = {}

        with patch("src.finalize.main._load_env") as mock_env:
            run(
                repository=repo,
                finalizer=finalizer,
                project_root=project_root,
                one_drive_root=one_drive_root,
            )

        mock_env.assert_called_once_with()

    def test_run_processes_all_actors(self, tmp_path: Path) -> None:
        """全被写体に対して _run_finalize_for_actor が呼ばれること。"""
        project_root, one_drive_root, repo, finalizer = self._make_deps(tmp_path)
        repo.getActors.return_value = ["actor_a", "actor_b"]
        repo.loadActorEntries.return_value = []
        repo.loadAnalysisJson.return_value = {}

        with patch("src.finalize.main._load_env"):
            with patch(
                "src.finalize.main._run_finalize_for_actor"
            ) as mock_finalize:
                run(
                    repository=repo,
                    finalizer=finalizer,
                    project_root=project_root,
                    one_drive_root=one_drive_root,
                )

        assert mock_finalize.call_count == 2
        calls = mock_finalize.call_args_list
        assert calls[0][0][0] == "actor_a"
        assert calls[1][0][0] == "actor_b"

    def test_run_saves_analysis_json(self, tmp_path: Path) -> None:
        """処理後に saveAnalysisJson が呼ばれること。"""
        project_root, one_drive_root, repo, finalizer = self._make_deps(tmp_path)
        repo.getActors.return_value = []
        repo.loadAnalysisJson.return_value = {"actor_a": []}

        with patch("src.finalize.main._load_env"):
            run(
                repository=repo,
                finalizer=finalizer,
                project_root=project_root,
                one_drive_root=one_drive_root,
            )

        repo.saveAnalysisJson.assert_called_once_with({"actor_a": []})

    def test_run_creates_default_instances_from_env(self, tmp_path: Path) -> None:
        """依存オブジェクトを省略した場合、環境変数からインスタンスを生成すること。"""
        project_root, one_drive_root, _, _ = self._make_deps(tmp_path)

        with patch("src.finalize.main._load_env"):
            with patch.dict(
                "os.environ",
                {
                    "PROJECT_ROOT": str(project_root),
                    "ONE_DRIVE_ROOT": str(one_drive_root),
                },
            ):
                with patch(
                    "src.finalize.main.FinalizeRepository"
                ) as mock_repo_cls:
                    with patch(
                        "src.finalize.main.PhotoFinalizer"
                    ) as mock_finalizer_cls:
                        mock_repo = MagicMock(spec=FinalizeRepository)
                        mock_repo.getActors.return_value = []
                        mock_repo.loadAnalysisJson.return_value = {}
                        mock_repo_cls.return_value = mock_repo
                        mock_finalizer_cls.return_value = MagicMock(
                            spec=PhotoFinalizer
                        )

                        run()

        mock_repo_cls.assert_called_once_with(project_root, one_drive_root)
        mock_finalizer_cls.assert_called_once_with(one_drive_root)
