"""src.move.main のユニットテスト。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from src.move.main import (
    MoveRepository,
    PhotoMover,
    _move_actor_photos,
    _load_env,
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
        with patch("src.move.main.load_dotenv") as mock_load:
            _load_env()

        mock_load.assert_called_once_with(override=False)


# ---------------------------------------------------------------------------
# MoveRepository
# ---------------------------------------------------------------------------


class TestMoveRepository:
    """MoveRepository のテスト。"""

    def _make_repo_with_engine(self):
        """テスト用リポジトリと mock Engine を両方返す。"""
        mock_engine = MagicMock()
        return MoveRepository(engine=mock_engine), mock_engine

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

    # --- getUnlearnedFilenames ---

    def test_get_unlearned_filenames_returns_set_of_filenames(self) -> None:
        """learned=false のファイル名セットを返すこと。"""
        repo, mock_engine = self._make_repo_with_engine()
        rows = [
            SimpleNamespace(filename="img001.jpg"),
            SimpleNamespace(filename="img002.jpg"),
        ]
        self._setup_conn(mock_engine, rows=rows)

        result = repo.getUnlearnedFilenames("actor_a")

        assert result == {"img001.jpg", "img002.jpg"}

    def test_get_unlearned_filenames_executes_query(self) -> None:
        """クエリが実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.getUnlearnedFilenames("actor_a")

        mock_conn.execute.assert_called_once()

    def test_get_unlearned_filenames_returns_empty_set_when_no_rows(self) -> None:
        """テーブルが空の場合、空セットを返すこと。"""
        repo, mock_engine = self._make_repo_with_engine()
        self._setup_conn(mock_engine, rows=[])

        result = repo.getUnlearnedFilenames("actor_a")

        assert result == set()

    def test_get_unlearned_filenames_deduplicates(self) -> None:
        """同名ファイルが複数あっても重複なしのセットを返すこと。"""
        repo, mock_engine = self._make_repo_with_engine()
        rows = [
            SimpleNamespace(filename="img.jpg"),
            SimpleNamespace(filename="img.jpg"),
        ]
        self._setup_conn(mock_engine, rows=rows)

        result = repo.getUnlearnedFilenames("actor_a")

        assert result == {"img.jpg"}


# ---------------------------------------------------------------------------
# PhotoMover
# ---------------------------------------------------------------------------


class TestPhotoMover:
    """PhotoMover のテスト。"""

    # --- listActorDirs ---

    def test_list_actor_dirs_returns_subdirs(self, tmp_path: Path) -> None:
        """SORTING_ROOT 直下のディレクトリ名リストを返すこと。"""
        (tmp_path / "actor_a").mkdir()
        (tmp_path / "actor_b").mkdir()
        mover = PhotoMover()

        result = mover.listActorDirs(tmp_path)

        assert sorted(result) == ["actor_a", "actor_b"]

    def test_list_actor_dirs_excludes_files(self, tmp_path: Path) -> None:
        """ファイルはディレクトリ一覧に含まれないこと。"""
        (tmp_path / "actor_a").mkdir()
        (tmp_path / "file.txt").write_text("x")
        mover = PhotoMover()

        result = mover.listActorDirs(tmp_path)

        assert result == ["actor_a"]

    def test_list_actor_dirs_returns_empty_when_dir_not_exists(self, tmp_path: Path) -> None:
        """ディレクトリが存在しない場合、空リストを返すこと。"""
        mover = PhotoMover()

        result = mover.listActorDirs(tmp_path / "nonexistent")

        assert result == []

    def test_list_actor_dirs_returns_empty_when_no_subdirs(self, tmp_path: Path) -> None:
        """サブディレクトリが存在しない場合、空リストを返すこと。"""
        mover = PhotoMover()

        result = mover.listActorDirs(tmp_path)

        assert result == []

    # --- listPhotos ---

    def test_list_photos_returns_image_files(self, tmp_path: Path) -> None:
        """画像ファイル名リストを返すこと。"""
        actor_dir = tmp_path / "actor_a"
        actor_dir.mkdir()
        (actor_dir / "img001.jpg").write_text("x")
        (actor_dir / "img002.png").write_text("x")
        (actor_dir / "img003.jpeg").write_text("x")
        mover = PhotoMover()

        result = sorted(mover.listPhotos(actor_dir))

        assert result == ["img001.jpg", "img002.png", "img003.jpeg"]

    def test_list_photos_excludes_non_image_files(self, tmp_path: Path) -> None:
        """画像以外のファイルは一覧に含まれないこと。"""
        actor_dir = tmp_path / "actor_a"
        actor_dir.mkdir()
        (actor_dir / "img.jpg").write_text("x")
        (actor_dir / "doc.txt").write_text("x")
        mover = PhotoMover()

        result = mover.listPhotos(actor_dir)

        assert result == ["img.jpg"]

    def test_list_photos_returns_empty_when_dir_not_exists(self, tmp_path: Path) -> None:
        """ディレクトリが存在しない場合、空リストを返すこと。"""
        mover = PhotoMover()

        result = mover.listPhotos(tmp_path / "nonexistent")

        assert result == []

    def test_list_photos_returns_empty_when_no_images(self, tmp_path: Path) -> None:
        """画像ファイルが無い場合、空リストを返すこと。"""
        actor_dir = tmp_path / "actor_a"
        actor_dir.mkdir()
        mover = PhotoMover()

        result = mover.listPhotos(actor_dir)

        assert result == []

    def test_list_photos_case_insensitive_extension(self, tmp_path: Path) -> None:
        """拡張子の大文字小文字を問わず画像ファイルを返すこと。"""
        actor_dir = tmp_path / "actor_a"
        actor_dir.mkdir()
        (actor_dir / "IMG.JPG").write_text("x")
        mover = PhotoMover()

        result = mover.listPhotos(actor_dir)

        assert result == ["IMG.JPG"]

    # --- resolveDestFilename ---

    def test_resolve_dest_filename_returns_original_when_no_conflict(
        self, tmp_path: Path
    ) -> None:
        """conflict がない場合、元のファイル名を返すこと。"""
        mover = PhotoMover()

        result = mover.resolveDestFilename("img001.jpg", tmp_path, set())

        assert result == "img001.jpg"

    def test_resolve_dest_filename_renames_when_conflict_in_sorting_state(
        self, tmp_path: Path
    ) -> None:
        """sorting_state に同名エントリがある場合、01 サフィックスを付けてリネームすること。"""
        mover = PhotoMover()

        result = mover.resolveDestFilename("0001.jpg", tmp_path, {"0001.jpg"})

        assert result == "0001_01.jpg"

    def test_resolve_dest_filename_skips_num_if_already_in_conflict(
        self, tmp_path: Path
    ) -> None:
        """リネーム候補も conflict_filenames にある場合、次の番号を使うこと。"""
        mover = PhotoMover()
        conflicts = {"0001.jpg", "0001_01.jpg"}

        result = mover.resolveDestFilename("0001.jpg", tmp_path, conflicts)

        assert result == "0001_02.jpg"

    def test_resolve_dest_filename_skips_num_if_exists_in_dst_dir(
        self, tmp_path: Path
    ) -> None:
        """リネーム候補が移動先ディレクトリに存在する場合、次の番号を使うこと。"""
        (tmp_path / "0001_01.jpg").write_text("x")
        mover = PhotoMover()

        result = mover.resolveDestFilename("0001.jpg", tmp_path, {"0001.jpg"})

        assert result == "0001_02.jpg"

    def test_resolve_dest_filename_uses_two_digit_num(self, tmp_path: Path) -> None:
        """num が 2 桁フォーマットであること。"""
        mover = PhotoMover()

        result = mover.resolveDestFilename("img.jpg", tmp_path, {"img.jpg"})

        assert result == "img_01.jpg"

    def test_resolve_dest_filename_preserves_extension(self, tmp_path: Path) -> None:
        """リネーム後も拡張子が保持されること。"""
        mover = PhotoMover()

        result = mover.resolveDestFilename("photo.png", tmp_path, {"photo.png"})

        assert result == "photo_01.png"

    # --- movePhoto ---

    def test_move_photo_moves_file(self, tmp_path: Path) -> None:
        """指定先にファイルが移動されること。"""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        src = src_dir / "img.jpg"
        src.write_text("data")
        dst_dir = tmp_path / "dst"
        mover = PhotoMover()

        mover.movePhoto(src, dst_dir, "img.jpg")

        assert not src.exists()
        assert (dst_dir / "img.jpg").exists()

    def test_move_photo_creates_dst_dir(self, tmp_path: Path) -> None:
        """移動先ディレクトリが存在しない場合でも移動できること。"""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "img.jpg").write_text("data")
        dst_dir = tmp_path / "dst" / "nested"
        mover = PhotoMover()

        mover.movePhoto(src_dir / "img.jpg", dst_dir, "img.jpg")

        assert (dst_dir / "img.jpg").exists()

    def test_move_photo_uses_dst_filename(self, tmp_path: Path) -> None:
        """dst_filename で指定されたファイル名で移動されること。"""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "orig.jpg").write_text("data")
        dst_dir = tmp_path / "dst"
        mover = PhotoMover()

        mover.movePhoto(src_dir / "orig.jpg", dst_dir, "renamed_01.jpg")

        assert (dst_dir / "renamed_01.jpg").exists()
        assert not (dst_dir / "orig.jpg").exists()


# ---------------------------------------------------------------------------
# _move_actor_photos
# ---------------------------------------------------------------------------


class TestMoveActorPhotos:
    """_move_actor_photos のテスト。"""

    def _make_mocks(self, photos: list, conflict_filenames: set):
        """mock Repository と PhotoMover を生成する。"""
        repo = MagicMock(spec=MoveRepository)
        repo.getUnlearnedFilenames.return_value = conflict_filenames
        mover = MagicMock(spec=PhotoMover)
        mover.listPhotos.return_value = photos
        mover.resolveDestFilename.side_effect = lambda f, dst, cf: f
        return repo, mover

    def test_moves_each_photo(self, tmp_path: Path) -> None:
        """各写真が movePhoto で移動されること。"""
        repo, mover = self._make_mocks(["a.jpg", "b.jpg"], set())
        sorting_root = tmp_path / "sorting"
        analyze_root = tmp_path / "analyze"

        _move_actor_photos("actor_a", sorting_root, analyze_root, repo, mover, max_workers=1)

        assert mover.movePhoto.call_count == 2

    def test_calls_get_unlearned_filenames_with_actor(self, tmp_path: Path) -> None:
        """getUnlearnedFilenames が actor 名で呼ばれること。"""
        repo, mover = self._make_mocks(["img.jpg"], set())
        sorting_root = tmp_path / "sorting"
        analyze_root = tmp_path / "analyze"

        _move_actor_photos("actor_b", sorting_root, analyze_root, repo, mover, max_workers=1)

        repo.getUnlearnedFilenames.assert_called_once_with("actor_b")

    def test_does_nothing_when_no_photos(self, tmp_path: Path) -> None:
        """写真が無い場合、movePhoto が呼ばれないこと。"""
        repo, mover = self._make_mocks([], set())
        sorting_root = tmp_path / "sorting"
        analyze_root = tmp_path / "analyze"

        _move_actor_photos("actor_a", sorting_root, analyze_root, repo, mover, max_workers=1)

        mover.movePhoto.assert_not_called()
        repo.getUnlearnedFilenames.assert_not_called()

    def test_resolve_dest_filename_called_with_conflict_filenames(self, tmp_path: Path) -> None:
        """resolveDestFilename が conflict_filenames を受け取って呼ばれること。"""
        conflicts = {"img.jpg"}
        repo, mover = self._make_mocks(["img.jpg"], conflicts)
        sorting_root = tmp_path / "sorting"
        analyze_root = tmp_path / "analyze"

        _move_actor_photos("actor_a", sorting_root, analyze_root, repo, mover, max_workers=1)

        resolve_calls = mover.resolveDestFilename.call_args_list
        assert len(resolve_calls) == 1
        _, kwargs_or_args = resolve_calls[0][0], resolve_calls[0][1]
        assert resolve_calls[0][0][0] == "img.jpg"
        assert resolve_calls[0][0][2] == conflicts

    def test_move_photo_called_with_renamed_filename(self, tmp_path: Path) -> None:
        """resolveDestFilename の結果が movePhoto に渡されること。"""
        repo = MagicMock(spec=MoveRepository)
        repo.getUnlearnedFilenames.return_value = {"img.jpg"}
        mover = MagicMock(spec=PhotoMover)
        mover.listPhotos.return_value = ["img.jpg"]
        mover.resolveDestFilename.return_value = "img_01.jpg"
        sorting_root = tmp_path / "sorting"
        analyze_root = tmp_path / "analyze"

        _move_actor_photos("actor_a", sorting_root, analyze_root, repo, mover, max_workers=1)

        assert mover.movePhoto.call_count == 1
        call_args = mover.movePhoto.call_args[0]
        assert call_args[0] == sorting_root / "actor_a" / "img.jpg"
        assert call_args[1] == analyze_root / "actor_a"
        assert call_args[2] == "img_01.jpg"


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    """run() のテスト。"""

    def _make_deps(self, tmp_path: Path):
        """テスト用の依存オブジェクトを生成する。"""
        sorting_root = tmp_path / "sorting"
        analyze_root = tmp_path / "analyze"
        sorting_root.mkdir()
        analyze_root.mkdir()
        mock_engine = MagicMock()
        repo = MagicMock(spec=MoveRepository)
        mover = MagicMock(spec=PhotoMover)
        return sorting_root, analyze_root, mock_engine, repo, mover

    def test_run_calls_load_env(self, tmp_path: Path) -> None:
        """_load_env が呼ばれること。"""
        sorting_root, analyze_root, mock_engine, repo, mover = self._make_deps(tmp_path)
        mover.listActorDirs.return_value = []

        with patch("src.move.main._load_env") as mock_env:
            run(
                repository=repo,
                mover=mover,
                sorting_root=sorting_root,
                analyze_root=analyze_root,
                engine=mock_engine,
            )

        mock_env.assert_called_once_with()

    def test_run_calls_move_actor_photos_for_each_actor(self, tmp_path: Path) -> None:
        """全 actor に対して _move_actor_photos が呼ばれること。"""
        sorting_root, analyze_root, mock_engine, repo, mover = self._make_deps(tmp_path)
        mover.listActorDirs.return_value = ["actor_a", "actor_b"]
        sorted_results_root = sorting_root / "sorted_results"

        with patch("src.move.main._load_env"):
            with patch("src.move.main._move_actor_photos") as mock_move:
                run(
                    repository=repo,
                    mover=mover,
                    sorting_root=sorting_root,
                    analyze_root=analyze_root,
                    engine=mock_engine,
                )

        mover.listActorDirs.assert_called_once_with(sorted_results_root)
        assert mock_move.call_count == 2
        calls = mock_move.call_args_list
        assert calls[0][0][0] == "actor_a"
        assert calls[0][0][1] == sorted_results_root
        assert calls[1][0][0] == "actor_b"
        assert calls[1][0][1] == sorted_results_root

    def test_run_does_nothing_when_no_actor_dirs(self, tmp_path: Path) -> None:
        """actor ディレクトリが無い場合、_move_actor_photos が呼ばれないこと。"""
        sorting_root, analyze_root, mock_engine, repo, mover = self._make_deps(tmp_path)
        mover.listActorDirs.return_value = []

        with patch("src.move.main._load_env"):
            with patch("src.move.main._move_actor_photos") as mock_move:
                run(
                    repository=repo,
                    mover=mover,
                    sorting_root=sorting_root,
                    analyze_root=analyze_root,
                    engine=mock_engine,
                )

        mover.listActorDirs.assert_called_once_with(sorting_root / "sorted_results")
        mock_move.assert_not_called()

    def test_run_creates_default_instances_from_env(self, tmp_path: Path) -> None:
        """依存オブジェクトを省略した場合、環境変数からインスタンスを生成すること。"""
        sorting_root = tmp_path / "sorting"
        analyze_root = tmp_path / "analyze"
        mock_engine = MagicMock()

        with patch("src.move.main._load_env"):
            with patch("src.move.main._create_engine", return_value=mock_engine):
                with patch.dict(
                    "os.environ",
                    {
                        "SORTING_ROOT": str(sorting_root),
                        "ANALYZE_ROOT": str(analyze_root),
                    },
                ):
                    with patch("src.move.main.MoveRepository") as mock_repo_cls:
                        with patch("src.move.main.PhotoMover") as mock_mover_cls:
                            mock_repo = MagicMock(spec=MoveRepository)
                            mock_mover = MagicMock(spec=PhotoMover)
                            mock_repo_cls.return_value = mock_repo
                            mock_mover_cls.return_value = mock_mover
                            mock_mover.listActorDirs.return_value = []

                            run()

        mock_repo_cls.assert_called_once_with(mock_engine)
        mock_mover_cls.assert_called_once_with()

    def test_run_passes_max_workers_to_move_actor_photos(self, tmp_path: Path) -> None:
        """max_workers が _move_actor_photos に渡されること。"""
        sorting_root, analyze_root, mock_engine, repo, mover = self._make_deps(tmp_path)
        mover.listActorDirs.return_value = ["actor_a"]

        with patch("src.move.main._load_env"):
            with patch("src.move.main._move_actor_photos") as mock_move:
                run(
                    repository=repo,
                    mover=mover,
                    sorting_root=sorting_root,
                    analyze_root=analyze_root,
                    engine=mock_engine,
                    max_workers=8,
                )

        call_kwargs = mock_move.call_args[1]
        assert call_kwargs.get("max_workers") == 8 or mock_move.call_args[0][5] == 8


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    """main() の CLI 引数テスト。"""

    def test_main_calls_run_with_default_workers(self) -> None:
        """引数なしのとき run(max_workers=4) が呼ばれること。"""
        with patch("sys.argv", ["main.py"]):
            with patch("src.move.main.run") as mock_run:
                main()

        mock_run.assert_called_once_with(max_workers=4)

    def test_main_calls_run_with_custom_workers(self) -> None:
        """--workers 8 のとき run(max_workers=8) が呼ばれること。"""
        with patch("sys.argv", ["main.py", "--workers", "8"]):
            with patch("src.move.main.run") as mock_run:
                main()

        mock_run.assert_called_once_with(max_workers=8)
