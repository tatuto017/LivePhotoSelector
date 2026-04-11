"""src.analysis.main のユニットテスト。"""

import json
import math
import pickle
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.analysis.main import (
    AnalysisEntry,
    AnalysisRecord,
    AnalysisRepository,
    PhotoAnalyzer,
    PhotoMover,
    _calculate_face_angle,
    _get_shooting_date,
    _load_env,
    _run_analyze,
    _run_finalize,
    _run_scoring,
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
        with patch("src.analysis.main.load_dotenv") as mock_load:
            _load_env()

        mock_load.assert_called_once_with(override=False)


# ---------------------------------------------------------------------------
# _get_shooting_date
# ---------------------------------------------------------------------------


class TestGetShootingDate:
    """_get_shooting_date のテスト。"""

    def test_returns_date_from_exif(self, tmp_path: Path) -> None:
        """EXIF DateTimeOriginal が存在する場合、YYYY-MM-DD 形式で返すこと。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        mock_exif = {36867: "2026:04:01 12:00:00"}  # 36867 = DateTimeOriginal tag id

        mock_img = MagicMock()
        mock_img._getexif.return_value = mock_exif
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        with patch("src.analysis.main.Image.open", return_value=mock_img) as mock_open:
            with patch("src.analysis.main.TAGS", {36867: "DateTimeOriginal"}):
                result = _get_shooting_date(img_path)

        mock_open.assert_called_once_with(img_path)
        assert result == "2026-04-01"

    def test_returns_today_when_no_exif(self, tmp_path: Path) -> None:
        """EXIF データが None の場合、今日の日付を返すこと。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        mock_img = MagicMock()
        mock_img._getexif.return_value = None
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        with patch("src.analysis.main.Image.open", return_value=mock_img):
            with patch("src.analysis.main.datetime") as mock_dt:
                mock_dt.now.return_value.strftime.return_value = "2026-04-10"
                result = _get_shooting_date(img_path)

        assert result == "2026-04-10"
        mock_dt.now.assert_called_once()

    def test_returns_today_when_exception(self, tmp_path: Path) -> None:
        """Image.open が例外を送出した場合、今日の日付を返すこと。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        with patch("src.analysis.main.Image.open", side_effect=Exception("read error")):
            with patch("src.analysis.main.datetime") as mock_dt:
                mock_dt.now.return_value.strftime.return_value = "2026-04-10"
                result = _get_shooting_date(img_path)

        assert result == "2026-04-10"

    def test_returns_today_when_no_datetime_original_tag(self, tmp_path: Path) -> None:
        """EXIF に DateTimeOriginal タグが無い場合、今日の日付を返すこと。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        mock_exif = {271: "Canon"}  # 271 = Make tag

        mock_img = MagicMock()
        mock_img._getexif.return_value = mock_exif
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        with patch("src.analysis.main.Image.open", return_value=mock_img):
            with patch("src.analysis.main.TAGS", {271: "Make"}):
                with patch("src.analysis.main.datetime") as mock_dt:
                    mock_dt.now.return_value.strftime.return_value = "2026-04-10"
                    result = _get_shooting_date(img_path)

        assert result == "2026-04-10"


# ---------------------------------------------------------------------------
# _calculate_face_angle
# ---------------------------------------------------------------------------


class TestCalculateFaceAngle:
    """_calculate_face_angle のテスト。"""

    def test_horizontal_eyes_returns_zero(self) -> None:
        """水平に並ぶ目座標でロール角が 0 度になること。"""
        result = _calculate_face_angle([10, 50], [60, 50])
        assert result == pytest.approx(0.0)

    def test_tilted_eyes_returns_expected_angle(self) -> None:
        """傾いた目座標で正しいロール角を返すこと。"""
        # dx=10, dy=10 → 45 度
        result = _calculate_face_angle([0, 0], [10, 10])
        assert result == pytest.approx(45.0)

    def test_negative_tilt_returns_negative_angle(self) -> None:
        """負方向の傾きで負のロール角を返すこと。"""
        # dx=10, dy=-10 → -45 度
        result = _calculate_face_angle([0, 0], [10, -10])
        assert result == pytest.approx(-45.0)

    def test_vertical_eyes_returns_90_degrees(self) -> None:
        """垂直方向で 90 度を返すこと。"""
        result = _calculate_face_angle([0, 0], [0, 10])
        assert result == pytest.approx(90.0)


# ---------------------------------------------------------------------------
# AnalysisRepository
# ---------------------------------------------------------------------------


class TestAnalysisRepository:
    """AnalysisRepository のテスト。"""

    def _make_repo(self, tmp_path: Path) -> AnalysisRepository:
        """テスト用のリポジトリを生成する。"""
        return AnalysisRepository(
            project_root=tmp_path / "project",
            one_drive_root=tmp_path / "onedrive",
        )

    # --- loadRecords ---

    def test_load_records_returns_empty_when_file_not_exists(self, tmp_path: Path) -> None:
        """analysis.pki が存在しない場合、空リストを返すこと。"""
        repo = self._make_repo(tmp_path)
        result = repo.loadRecords()
        assert result == []

    def test_load_records_returns_records_from_file(self, tmp_path: Path) -> None:
        """analysis.pki が存在する場合、レコードを返すこと。"""
        repo = self._make_repo(tmp_path)
        records = [AnalysisRecord("a", "img.jpg", "2026-04-01", 0, 0, 80, 0, 0, 0, 20, 0.0, False, [0.1] * 128)]

        pki_path = tmp_path / "onedrive" / "data" / "analysis.pki"
        pki_path.parent.mkdir(parents=True)
        with open(pki_path, "wb") as f:
            pickle.dump(records, f)

        result = repo.loadRecords()
        assert len(result) == 1
        assert result[0].actor == "a"
        assert result[0].filename == "img.jpg"

    # --- saveRecords ---

    def test_save_records_creates_dir_and_saves(self, tmp_path: Path) -> None:
        """ディレクトリが無くても作成して保存できること。"""
        repo = self._make_repo(tmp_path)
        records = [AnalysisRecord("a", "img.jpg", "2026-04-01", 0, 0, 80, 0, 0, 0, 20, 0.0, False, [0.1] * 128)]

        repo.saveRecords(records)

        pki_path = tmp_path / "onedrive" / "data" / "analysis.pki"
        assert pki_path.exists()
        with open(pki_path, "rb") as f:
            loaded = pickle.load(f)
        assert len(loaded) == 1
        assert loaded[0].filename == "img.jpg"

    def test_save_records_writes_atomically(self, tmp_path: Path) -> None:
        """アトミック書き込み（一時ファイル→リネーム）で保存されること。"""
        repo = self._make_repo(tmp_path)
        records = [AnalysisRecord("a", "img.jpg", "2026-04-01", 0, 0, 80, 0, 0, 0, 20, 0.0, False, [0.1] * 128)]

        with patch("src.analysis.main.shutil.move") as mock_move:
            with patch("src.analysis.main.tempfile.NamedTemporaryFile") as mock_tmp:
                mock_tmp.return_value.__enter__ = MagicMock(return_value=MagicMock(name="/tmp/tmp_abc"))
                mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
                mock_tmp.return_value.__enter__.return_value.name = "/tmp/tmp_abc"
                repo.saveRecords(records)

        mock_move.assert_called_once()

    # --- loadActorEntries ---

    def test_load_actor_entries_returns_empty_when_file_not_exists(self, tmp_path: Path) -> None:
        """{actor}_analysis.json が存在しない場合、空リストを返すこと。"""
        repo = self._make_repo(tmp_path)
        result = repo.loadActorEntries("actor_a")
        assert result == []

    def test_load_actor_entries_returns_empty_when_file_is_corrupted(
        self, tmp_path: Path
    ) -> None:
        """JSON が破損している場合、空リストを返して警告を出すこと。"""
        data_dir = tmp_path / "onedrive" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "actor_a_analysis.json").write_text(
            '[{"filename": "img.jpg", "broken":', encoding="utf-8"
        )
        repo = self._make_repo(tmp_path)

        result = repo.loadActorEntries("actor_a")

        assert result == []

    def test_load_actor_entries_returns_entries_from_file(self, tmp_path: Path) -> None:
        """{actor}_analysis.json が存在する場合、エントリを返すこと。"""
        repo = self._make_repo(tmp_path)
        data_dir = tmp_path / "onedrive" / "data"
        data_dir.mkdir(parents=True)

        data = [
            {
                "filename": "img001.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "selectedAt": "2026-04-06T12:00:00.000Z",
            }
        ]
        with open(data_dir / "actor_a_analysis.json", "w") as f:
            json.dump(data, f)

        result = repo.loadActorEntries("actor_a")
        assert len(result) == 1
        assert result[0].filename == "img001.jpg"
        assert result[0].score == 0.8
        assert result[0].selectionState == "ok"

    # --- saveActorEntries ---

    def test_save_actor_entries_creates_dir_and_saves(self, tmp_path: Path) -> None:
        """ディレクトリが無くても作成して保存できること。"""
        repo = self._make_repo(tmp_path)
        entries = [
            AnalysisEntry(
                filename="img001.jpg",
                shootingDate="2026-04-01",
                score=0.9,
                selectionState="pending",
                selectedAt=None,
            )
        ]

        repo.saveActorEntries("actor_a", entries)

        path = tmp_path / "onedrive" / "data" / "actor_a_analysis.json"
        assert path.exists()
        with open(path, "r") as f:
            saved = json.load(f)
        assert len(saved) == 1
        assert saved[0]["filename"] == "img001.jpg"
        assert saved[0]["score"] == 0.9
        assert saved[0]["selectedAt"] is None

    def test_save_actor_entries_writes_atomically(self, tmp_path: Path) -> None:
        """アトミック書き込み（一時ファイル→リネーム）で保存されること。"""
        repo = self._make_repo(tmp_path)
        entries = [AnalysisEntry(filename="img.jpg", shootingDate="2026-04-01")]

        with patch("src.analysis.main.shutil.move") as mock_move:
            with patch("src.analysis.main.tempfile.NamedTemporaryFile") as mock_tmp:
                mock_tmp.return_value.__enter__ = MagicMock(return_value=MagicMock(name="/tmp/tmp_abc"))
                mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
                mock_tmp.return_value.__enter__.return_value.name = "/tmp/tmp_abc"
                repo.saveActorEntries("actor_a", entries)

        mock_move.assert_called_once()

    def test_save_actor_entries_serializes_none_fields(self, tmp_path: Path) -> None:
        """score・selectedAt が None でも正しく保存されること。"""
        repo = self._make_repo(tmp_path)
        entries = [AnalysisEntry(filename="img.jpg", shootingDate="2026-04-01")]

        repo.saveActorEntries("actor_a", entries)

        path = tmp_path / "onedrive" / "data" / "actor_a_analysis.json"
        with open(path, "r") as f:
            saved = json.load(f)
        assert saved[0]["score"] is None
        assert saved[0]["selectedAt"] is None


# ---------------------------------------------------------------------------
# PhotoAnalyzer
# ---------------------------------------------------------------------------


class TestPhotoAnalyzer:
    """PhotoAnalyzer のテスト。"""

    def _make_subprocess_stdout(
        self,
        actor: str = "actor_a",
        filename: str = "img.jpg",
        angry: float = 5.0,
        fear: float = 2.0,
        happy: float = 80.0,
        sad: float = 3.0,
        surprise: float = 4.0,
        disgust: float = 1.0,
        neutral: float = 5.0,
        faceAngle: float = 0.0,
        isOccluded: bool = False,
        face_embedding: list = None,
    ) -> str:
        """subprocess の標準出力として返す JSON 文字列を生成する。"""
        import json

        return json.dumps(
            {
                "actor": actor,
                "filename": filename,
                "angry": angry,
                "fear": fear,
                "happy": happy,
                "sad": sad,
                "surprise": surprise,
                "disgust": disgust,
                "neutral": neutral,
                "faceAngle": faceAngle,
                "isOccluded": isOccluded,
                "face_embedding": face_embedding if face_embedding is not None else [0.1] * 128,
            }
        )

    def _make_mock_subprocess_result(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        """subprocess.run の戻り値となる MagicMock を生成する。"""
        mock_result = MagicMock()
        mock_result.returncode = returncode
        mock_result.stdout = stdout
        mock_result.stderr = stderr
        return mock_result

    def test_analyze_returns_record_on_success(self, tmp_path: Path) -> None:
        """正常系: サブプロセスが成功した場合 AnalysisRecord を返すこと。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        stdout = self._make_subprocess_stdout()
        mock_result = self._make_mock_subprocess_result(returncode=0, stdout=stdout)

        with patch("src.analysis.main.subprocess.run", return_value=mock_result) as mock_run:
            with patch("src.analysis.main._get_shooting_date", return_value="2026-04-01") as mock_date:
                result = PhotoAnalyzer().analyze(img_path, "actor_a")

        assert result is not None
        assert result.actor == "actor_a"
        assert result.filename == "img.jpg"
        assert result.shootingDate == "2026-04-01"
        assert result.happy == 80.0
        assert result.faceAngle == pytest.approx(0.0)
        assert result.isOccluded is False
        assert result.face_embedding == [0.1] * 128

        # subprocess.run の引数検証
        mock_run.assert_called_once_with(
            [
                sys.executable,
                "-m",
                "src.analysis.analyzer_subprocess",
                str(img_path),
                "actor_a",
            ],
            capture_output=True,
            text=True,
            timeout=PhotoAnalyzer._SUBPROCESS_TIMEOUT,
        )
        mock_date.assert_called_once_with(img_path)

    def test_analyze_returns_record_with_is_occluded_true(self, tmp_path: Path) -> None:
        """最大感情スコアが低く isOccluded=True の結果を正しく返すこと。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        stdout = self._make_subprocess_stdout(happy=30.0, isOccluded=True)
        mock_result = self._make_mock_subprocess_result(returncode=0, stdout=stdout)

        with patch("src.analysis.main.subprocess.run", return_value=mock_result):
            with patch("src.analysis.main._get_shooting_date", return_value="2026-04-01"):
                result = PhotoAnalyzer().analyze(img_path, "actor_a")

        assert result is not None
        assert result.isOccluded is True

    def test_analyze_returns_record_with_face_angle(self, tmp_path: Path) -> None:
        """faceAngle が JSON から正しく復元されること。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        stdout = self._make_subprocess_stdout(faceAngle=15.5)
        mock_result = self._make_mock_subprocess_result(returncode=0, stdout=stdout)

        with patch("src.analysis.main.subprocess.run", return_value=mock_result):
            with patch("src.analysis.main._get_shooting_date", return_value="2026-04-01"):
                result = PhotoAnalyzer().analyze(img_path, "actor_a")

        assert result is not None
        assert result.faceAngle == pytest.approx(15.5)

    def test_analyze_returns_none_when_subprocess_fails(self, tmp_path: Path) -> None:
        """サブプロセスが非ゼロ終了した場合 None を返すこと。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        mock_result = self._make_mock_subprocess_result(returncode=1, stderr="ERROR: no face")

        with patch("src.analysis.main.subprocess.run", return_value=mock_result):
            result = PhotoAnalyzer().analyze(img_path, "actor_a")

        assert result is None

    def test_analyze_returns_none_when_oom_killed(self, tmp_path: Path) -> None:
        """OOM Kill（exit code 137）の場合 None を返すこと。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        mock_result = self._make_mock_subprocess_result(returncode=137, stderr="")

        with patch("src.analysis.main.subprocess.run", return_value=mock_result):
            result = PhotoAnalyzer().analyze(img_path, "actor_a")

        assert result is None

    def test_analyze_returns_none_on_timeout(self, tmp_path: Path) -> None:
        """サブプロセスがタイムアウトした場合 None を返すこと。"""
        import subprocess as sp

        img_path = tmp_path / "img.jpg"
        img_path.touch()

        with patch("src.analysis.main.subprocess.run", side_effect=sp.TimeoutExpired(cmd=[], timeout=300)):
            result = PhotoAnalyzer().analyze(img_path, "actor_a")

        assert result is None

    def test_analyze_returns_none_on_unexpected_exception(self, tmp_path: Path) -> None:
        """予期しない例外が発生した場合 None を返すこと。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        with patch("src.analysis.main.subprocess.run", side_effect=OSError("spawn failed")):
            result = PhotoAnalyzer().analyze(img_path, "actor_a")

        assert result is None


# ---------------------------------------------------------------------------
# PhotoMover
# ---------------------------------------------------------------------------


class TestPhotoMover:
    """PhotoMover のテスト。"""

    def _make_mover(self, tmp_path: Path) -> PhotoMover:
        """テスト用の PhotoMover を生成する。"""
        return PhotoMover(one_drive_root=tmp_path)

    def test_move_to_images_moves_file(self, tmp_path: Path) -> None:
        """inbox/{actor}/ から images/{actor}/ へファイルを移動すること。"""
        inbox_dir = tmp_path / "inbox" / "actor_a"
        inbox_dir.mkdir(parents=True)
        src_file = inbox_dir / "img.jpg"
        src_file.write_text("data")

        mover = self._make_mover(tmp_path)
        mover.moveToImages("actor_a", "img.jpg")

        assert not src_file.exists()
        assert (tmp_path / "images" / "actor_a" / "img.jpg").exists()

    def test_move_to_images_creates_dst_dir(self, tmp_path: Path) -> None:
        """images/{actor}/ が存在しなくても作成して移動すること。"""
        inbox_dir = tmp_path / "inbox" / "actor_a"
        inbox_dir.mkdir(parents=True)
        (inbox_dir / "img.jpg").write_text("data")

        mover = self._make_mover(tmp_path)
        mover.moveToImages("actor_a", "img.jpg")

        assert (tmp_path / "images" / "actor_a" / "img.jpg").exists()

    def test_move_to_confirmed_moves_file(self, tmp_path: Path) -> None:
        """images/{actor}/ から confirmed/{actor}/ へファイルを移動すること。"""
        images_dir = tmp_path / "images" / "actor_a"
        images_dir.mkdir(parents=True)
        src_file = images_dir / "img.jpg"
        src_file.write_text("data")

        mover = self._make_mover(tmp_path)
        mover.moveToConfirmed("actor_a", "img.jpg")

        assert not src_file.exists()
        assert (tmp_path / "confirmed" / "actor_a" / "img.jpg").exists()

    def test_move_to_confirmed_creates_dst_dir(self, tmp_path: Path) -> None:
        """confirmed/{actor}/ が存在しなくても作成して移動すること。"""
        images_dir = tmp_path / "images" / "actor_a"
        images_dir.mkdir(parents=True)
        (images_dir / "img.jpg").write_text("data")

        mover = self._make_mover(tmp_path)
        mover.moveToConfirmed("actor_a", "img.jpg")

        assert (tmp_path / "confirmed" / "actor_a" / "img.jpg").exists()

    def test_delete_from_images_deletes_file(self, tmp_path: Path) -> None:
        """images/{actor}/ のファイルを削除すること。"""
        images_dir = tmp_path / "images" / "actor_a"
        images_dir.mkdir(parents=True)
        target = images_dir / "img.jpg"
        target.write_text("data")

        mover = self._make_mover(tmp_path)
        mover.deleteFromImages("actor_a", "img.jpg")

        assert not target.exists()

    def test_delete_from_images_does_nothing_when_file_not_exists(self, tmp_path: Path) -> None:
        """ファイルが存在しない場合も例外を送出しないこと。"""
        mover = self._make_mover(tmp_path)
        # 例外が送出されないことを確認
        mover.deleteFromImages("actor_a", "nonexistent.jpg")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    """run() のテスト。"""

    def _make_deps(self, tmp_path: Path):
        """DI 用の依存オブジェクトをまとめて返す。"""
        project_root = tmp_path / "project"
        one_drive_root = tmp_path / "onedrive"
        project_root.mkdir()
        one_drive_root.mkdir()
        repo = AnalysisRepository(project_root, one_drive_root)
        mover = PhotoMover(one_drive_root)
        analyzer = PhotoAnalyzer()
        return project_root, one_drive_root, repo, mover, analyzer

    def test_run_calls_run_analyze_by_default(self, tmp_path: Path) -> None:
        """mode='analyze' のとき _run_analyze が呼ばれること。"""
        project_root, one_drive_root, repo, mover, analyzer = self._make_deps(tmp_path)

        with patch("src.analysis.main._load_env"):
            with patch("src.analysis.main._run_analyze") as mock_analyze:
                run(
                    mode="analyze",
                    analyzer=analyzer,
                    repository=repo,
                    mover=mover,
                    project_root=project_root,
                    one_drive_root=one_drive_root,
                )

        mock_analyze.assert_called_once_with(one_drive_root, analyzer, repo, mover)

    def test_run_calls_run_scoring(self, tmp_path: Path) -> None:
        """mode='scoring' のとき _run_scoring が呼ばれること。"""
        project_root, one_drive_root, repo, mover, analyzer = self._make_deps(tmp_path)

        with patch("src.analysis.main._load_env"):
            with patch("src.analysis.main._run_scoring") as mock_scoring:
                run(
                    mode="scoring",
                    repository=repo,
                    mover=mover,
                    project_root=project_root,
                    one_drive_root=one_drive_root,
                )

        mock_scoring.assert_called_once_with()

    def test_run_calls_run_finalize(self, tmp_path: Path) -> None:
        """mode='finalize' のとき _run_finalize が呼ばれること。"""
        project_root, one_drive_root, repo, mover, analyzer = self._make_deps(tmp_path)

        with patch("src.analysis.main._load_env"):
            with patch("src.analysis.main._run_finalize") as mock_finalize:
                run(
                    mode="finalize",
                    repository=repo,
                    mover=mover,
                    project_root=project_root,
                    one_drive_root=one_drive_root,
                )

        mock_finalize.assert_called_once_with()

    def test_run_creates_default_instances_from_env(self, tmp_path: Path) -> None:
        """依存オブジェクトを省略した場合、環境変数からインスタンスを生成すること。"""
        project_root = tmp_path / "project"
        one_drive_root = tmp_path / "onedrive"

        with patch("src.analysis.main._load_env"):
            with patch("src.analysis.main._run_analyze") as mock_analyze:
                with patch.dict(
                    "os.environ",
                    {"PROJECT_ROOT": str(project_root), "ONE_DRIVE_ROOT": str(one_drive_root)},
                ):
                    run(mode="analyze")

        mock_analyze.assert_called_once()
        _, called_analyzer, called_repo, called_mover = mock_analyze.call_args[0]
        assert isinstance(called_analyzer, PhotoAnalyzer)
        assert isinstance(called_repo, AnalysisRepository)
        assert isinstance(called_mover, PhotoMover)

    def test_run_calls_load_env(self, tmp_path: Path) -> None:
        """run() の冒頭で _load_env が呼ばれること。"""
        project_root, one_drive_root, repo, mover, _ = self._make_deps(tmp_path)

        with patch("src.analysis.main._load_env") as mock_load_env:
            with patch("src.analysis.main._run_analyze"):
                run(
                    mode="analyze",
                    repository=repo,
                    mover=mover,
                    project_root=project_root,
                    one_drive_root=one_drive_root,
                )

        mock_load_env.assert_called_once_with()


# ---------------------------------------------------------------------------
# _run_analyze
# ---------------------------------------------------------------------------


class TestRunAnalyze:
    """_run_analyze のテスト。"""

    def _make_deps(self, tmp_path: Path):
        """テスト用の依存オブジェクトを返す。"""
        one_drive_root = tmp_path
        repo = MagicMock(spec=AnalysisRepository)
        mover = MagicMock(spec=PhotoMover)
        analyzer = MagicMock(spec=PhotoAnalyzer)
        return one_drive_root, repo, mover, analyzer

    def test_exits_early_when_inbox_not_exists(self, tmp_path: Path) -> None:
        """inbox ディレクトリが存在しない場合、処理を中断すること。"""
        one_drive_root, repo, mover, analyzer = self._make_deps(tmp_path)

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(one_drive_root, analyzer, repo, mover)

        repo.loadRecords.assert_not_called()
        analyzer.analyze.assert_not_called()

    def test_skips_non_directory_in_inbox(self, tmp_path: Path) -> None:
        """inbox 直下のファイルはスキップすること。"""
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        (inbox / "file.txt").touch()

        one_drive_root, repo, mover, analyzer = self._make_deps(tmp_path)
        repo.loadRecords.return_value = []
        repo.loadActorEntries.return_value = []

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(one_drive_root, analyzer, repo, mover)

        analyzer.analyze.assert_not_called()

    def test_analyzes_image_and_saves(self, tmp_path: Path) -> None:
        """画像ファイルを解析して pki と json を保存すること。"""
        inbox_dir = tmp_path / "inbox" / "actor_a"
        inbox_dir.mkdir(parents=True)
        img_path = inbox_dir / "img001.jpg"
        img_path.touch()

        record = AnalysisRecord(
            actor="actor_a",
            filename="img001.jpg",
            shootingDate="2026-04-01",
            angry=5.0, fear=2.0, happy=80.0, sad=3.0,
            surprise=4.0, disgust=1.0, neutral=5.0,
            faceAngle=0.0, isOccluded=False, face_embedding=[0.1] * 128,
        )
        one_drive_root, repo, mover, analyzer = self._make_deps(tmp_path)
        repo.loadRecords.return_value = []
        repo.loadActorEntries.return_value = []
        analyzer.analyze.return_value = record

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(one_drive_root, analyzer, repo, mover)

        # analyze の引数を検証
        analyzer.analyze.assert_called_once_with(img_path, "actor_a")

        # moveToImages の呼び出しを検証
        mover.moveToImages.assert_called_once_with("actor_a", "img001.jpg")

        # saveRecords の呼び出しを検証 (1 件追加)
        saved_records = repo.saveRecords.call_args[0][0]
        assert len(saved_records) == 1
        assert saved_records[0].filename == "img001.jpg"

        # saveActorEntries の呼び出しを検証 (score = max(80)/100 = 0.8)
        repo.saveActorEntries.assert_called_once_with("actor_a", [
            AnalysisEntry(
                filename="img001.jpg",
                shootingDate="2026-04-01",
                score=0.8,
                selectionState="pending",
                selectedAt=None,
            )
        ])

    def test_tqdm_called_with_img_files_and_actor_desc(self, tmp_path: Path) -> None:
        """tqdm が img_files・desc=actor名・unit='枚' で呼ばれること。"""
        inbox_dir = tmp_path / "inbox" / "actor_a"
        inbox_dir.mkdir(parents=True)
        img_path = inbox_dir / "img001.jpg"
        img_path.touch()

        record = AnalysisRecord(
            actor="actor_a", filename="img001.jpg", shootingDate="2026-04-01",
            angry=0, fear=0, happy=80, sad=0, surprise=0, disgust=0, neutral=20,
            faceAngle=0.0, isOccluded=False, face_embedding=[0.1] * 128,
        )
        one_drive_root, repo, mover, analyzer = self._make_deps(tmp_path)
        repo.loadRecords.return_value = []
        repo.loadActorEntries.return_value = []
        analyzer.analyze.return_value = record

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x) as mock_tqdm:
            _run_analyze(one_drive_root, analyzer, repo, mover)

        mock_tqdm.assert_called_once_with([img_path], desc="[actor_a]", unit="枚")

    def test_does_not_add_duplicate_record(self, tmp_path: Path) -> None:
        """既存の (actor, filename) と同じレコードは追加しないこと。"""
        inbox_dir = tmp_path / "inbox" / "actor_a"
        inbox_dir.mkdir(parents=True)
        img_path = inbox_dir / "img001.jpg"
        img_path.touch()

        existing_record = AnalysisRecord(
            actor="actor_a", filename="img001.jpg", shootingDate="2026-04-01",
            angry=0, fear=0, happy=90, sad=0, surprise=0, disgust=0, neutral=10,
            faceAngle=0.0, isOccluded=False, face_embedding=[0.1] * 128,
        )
        new_record = AnalysisRecord(
            actor="actor_a", filename="img001.jpg", shootingDate="2026-04-01",
            angry=0, fear=0, happy=85, sad=0, surprise=0, disgust=0, neutral=15,
            faceAngle=0.0, isOccluded=False, face_embedding=[0.1] * 128,
        )

        one_drive_root, repo, mover, analyzer = self._make_deps(tmp_path)
        repo.loadRecords.return_value = [existing_record]
        repo.loadActorEntries.return_value = []
        analyzer.analyze.return_value = new_record

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(one_drive_root, analyzer, repo, mover)

        # レコード数は増えない（重複追加しない）
        saved_records = repo.saveRecords.call_args[0][0]
        assert len(saved_records) == 1

    def test_does_not_add_duplicate_entry(self, tmp_path: Path) -> None:
        """既存の filename と同じエントリは追加しないこと。"""
        inbox_dir = tmp_path / "inbox" / "actor_a"
        inbox_dir.mkdir(parents=True)
        img_path = inbox_dir / "img001.jpg"
        img_path.touch()

        existing_entry = AnalysisEntry(
            filename="img001.jpg",
            shootingDate="2026-04-01",
            score=0.9,
            selectionState="ok",
            selectedAt="2026-04-06T12:00:00.000Z",
        )
        record = AnalysisRecord(
            actor="actor_a", filename="img001.jpg", shootingDate="2026-04-01",
            angry=0, fear=0, happy=80, sad=0, surprise=0, disgust=0, neutral=20,
            faceAngle=0.0, isOccluded=False, face_embedding=[0.1] * 128,
        )

        one_drive_root, repo, mover, analyzer = self._make_deps(tmp_path)
        repo.loadRecords.return_value = []
        repo.loadActorEntries.return_value = [existing_entry]
        analyzer.analyze.return_value = record

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(one_drive_root, analyzer, repo, mover)

        # エントリ数は増えない（重複追加しない）
        saved_entries = repo.saveActorEntries.call_args[0][1]
        assert len(saved_entries) == 1
        assert saved_entries[0].selectionState == "ok"  # 既存が維持される

    def test_handles_null_record_gracefully(self, tmp_path: Path) -> None:
        """analyze が None を返した場合、score=None でエントリを追加すること。"""
        inbox_dir = tmp_path / "inbox" / "actor_a"
        inbox_dir.mkdir(parents=True)
        img_path = inbox_dir / "img001.jpg"
        img_path.touch()

        one_drive_root, repo, mover, analyzer = self._make_deps(tmp_path)
        repo.loadRecords.return_value = []
        repo.loadActorEntries.return_value = []
        analyzer.analyze.return_value = None

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            with patch("src.analysis.main._get_shooting_date", return_value="2026-04-01"):
                _run_analyze(one_drive_root, analyzer, repo, mover)

        # レコードは追加されない
        saved_records = repo.saveRecords.call_args[0][0]
        assert len(saved_records) == 0

        # エントリは score=None で追加される
        saved_entries = repo.saveActorEntries.call_args[0][1]
        assert len(saved_entries) == 1
        assert saved_entries[0].score is None
        assert saved_entries[0].filename == "img001.jpg"

        # ファイルは移動される
        mover.moveToImages.assert_called_once_with("actor_a", "img001.jpg")

    def test_ignores_non_image_files(self, tmp_path: Path) -> None:
        """拡張子が対象外のファイルは解析しないこと。"""
        inbox_dir = tmp_path / "inbox" / "actor_a"
        inbox_dir.mkdir(parents=True)
        (inbox_dir / "document.pdf").touch()
        (inbox_dir / "readme.txt").touch()

        one_drive_root, repo, mover, analyzer = self._make_deps(tmp_path)
        repo.loadRecords.return_value = []
        repo.loadActorEntries.return_value = []

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(one_drive_root, analyzer, repo, mover)

        analyzer.analyze.assert_not_called()
        mover.moveToImages.assert_not_called()

    def test_processes_multiple_actors(self, tmp_path: Path) -> None:
        """複数の actor ディレクトリを処理すること。"""
        for actor in ["actor_a", "actor_b"]:
            inbox_dir = tmp_path / "inbox" / actor
            inbox_dir.mkdir(parents=True)
            (inbox_dir / "img.jpg").touch()

        record_a = AnalysisRecord("actor_a", "img.jpg", "2026-04-01", 0, 0, 80, 0, 0, 0, 20, 0.0, False, [0.1] * 128)
        record_b = AnalysisRecord("actor_b", "img.jpg", "2026-04-01", 0, 0, 70, 0, 0, 0, 30, 0.0, False, [0.1] * 128)

        one_drive_root, repo, mover, analyzer = self._make_deps(tmp_path)
        repo.loadRecords.return_value = []
        repo.loadActorEntries.return_value = []
        analyzer.analyze.side_effect = [record_a, record_b]

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(one_drive_root, analyzer, repo, mover)

        assert analyzer.analyze.call_count == 2
        assert mover.moveToImages.call_count == 2
        assert repo.saveActorEntries.call_count == 2


# ---------------------------------------------------------------------------
# _run_scoring
# ---------------------------------------------------------------------------


class TestRunScoring:
    """_run_scoring のテスト。"""

    def test_delegates_to_scoring_run(self) -> None:
        """src.scoring.main.run が 1 回呼ばれること。"""
        mock_scoring_run = MagicMock()
        with patch.dict("sys.modules", {"src.scoring.main": MagicMock(run=mock_scoring_run)}):
            _run_scoring()

        mock_scoring_run.assert_called_once_with()


# ---------------------------------------------------------------------------
# _run_finalize
# ---------------------------------------------------------------------------


class TestRunFinalize:
    """_run_finalize のテスト。"""

    def test_delegates_to_finalize_run(self) -> None:
        """src.finalize.main.run が呼ばれること。"""
        with patch("src.finalize.main.run") as mock_run:
            _run_finalize()

        mock_run.assert_called_once_with()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    """main() の CLI 引数テスト。"""

    def test_main_calls_run_with_analyze_by_default(self) -> None:
        """引数なしのとき run(mode='analyze') が呼ばれること。"""
        with patch("sys.argv", ["main.py"]):
            with patch("src.analysis.main.run") as mock_run:
                main()

        mock_run.assert_called_once_with(mode="analyze")

    def test_main_calls_run_with_scoring(self) -> None:
        """--scoring フラグのとき run(mode='scoring') が呼ばれること。"""
        with patch("sys.argv", ["main.py", "--scoring"]):
            with patch("src.analysis.main.run") as mock_run:
                main()

        mock_run.assert_called_once_with(mode="scoring")

    def test_main_calls_run_with_finalize(self) -> None:
        """--finalize フラグのとき run(mode='finalize') が呼ばれること。"""
        with patch("sys.argv", ["main.py", "--finalize"]):
            with patch("src.analysis.main.run") as mock_run:
                main()

        mock_run.assert_called_once_with(mode="finalize")

