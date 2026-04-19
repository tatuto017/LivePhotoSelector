"""src.analysis.main のユニットテスト。"""

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from src.analysis.main import (
    AnalysisEntry,
    AnalysisRecord,
    AnalysisRepository,
    PhotoAnalyzer,
    _calculate_face_angle,
    _get_shooting_date,
    _load_env,
    _run_analyze,
    _run_finalize,
    _run_scoring,
    main,
    run,
)
from concurrent.futures import Future


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

    def _make_repo_with_engine(self):
        """テスト用のリポジトリと mock Engine を両方返す。"""
        mock_engine = MagicMock()
        return AnalysisRepository(engine=mock_engine), mock_engine

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

    # --- loadRecords ---

    def test_load_records_returns_empty_when_no_rows(self) -> None:
        """analysis_records テーブルが空の場合、空リストを返すこと。"""
        repo, mock_engine = self._make_repo_with_engine()
        self._setup_conn(mock_engine, rows=[])

        result = repo.loadRecords()

        assert result == []

    def test_load_records_returns_records_from_db(self) -> None:
        """analysis_records テーブルのレコードを AnalysisRecord に変換して返すこと。"""
        repo, mock_engine = self._make_repo_with_engine()
        embedding = [0.1] * 128
        row = SimpleNamespace(
            actor="actor_a",
            filename="img.jpg",
            shooting_date="2026-04-01",
            angry=5.0, fear=2.0, happy=80.0, sad=3.0,
            surprise=4.0, disgust=1.0, neutral=5.0,
            face_angle=1.5,
            is_occluded=0,
            face_embedding=json.dumps(embedding),
        )
        self._setup_conn(mock_engine, rows=[row])

        result = repo.loadRecords()

        assert len(result) == 1
        assert result[0].actor == "actor_a"
        assert result[0].filename == "img.jpg"
        assert result[0].shootingDate == "2026-04-01"
        assert result[0].happy == 80.0
        assert result[0].faceAngle == 1.5
        assert result[0].isOccluded is False
        assert result[0].face_embedding == embedding

    def test_load_records_executes_select_query(self) -> None:
        """SELECT クエリが analysis_records テーブルに対して実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.loadRecords()

        mock_conn.execute.assert_called_once()

    def test_load_records_deserializes_is_occluded_as_bool(self) -> None:
        """is_occluded が TINYINT(1)=1 の場合、True に変換されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        row = SimpleNamespace(
            actor="a", filename="img.jpg", shooting_date="2026-04-01",
            angry=0, fear=0, happy=0, sad=0, surprise=0,
            disgust=0, neutral=100, face_angle=0.0,
            is_occluded=1,
            face_embedding=json.dumps([0.0] * 128),
        )
        self._setup_conn(mock_engine, rows=[row])

        result = repo.loadRecords()

        assert result[0].isOccluded is True

    # --- loadProcessedKeys ---

    def test_load_processed_keys_returns_set_of_tuples(self) -> None:
        """sorting_state から (actor_id, filename) のセットを返すこと。"""
        repo, mock_engine = self._make_repo_with_engine()
        rows = [
            SimpleNamespace(actor_id="actor_a", filename="img001.jpg"),
            SimpleNamespace(actor_id="actor_b", filename="img002.jpg"),
        ]
        self._setup_conn(mock_engine, rows=rows)

        result = repo.loadProcessedKeys()

        assert result == {("actor_a", "img001.jpg"), ("actor_b", "img002.jpg")}

    def test_load_processed_keys_returns_empty_set_when_no_rows(self) -> None:
        """sorting_state が空の場合、空セットを返すこと。"""
        repo, mock_engine = self._make_repo_with_engine()
        self._setup_conn(mock_engine, rows=[])

        result = repo.loadProcessedKeys()

        assert result == set()

    def test_load_processed_keys_executes_select_on_sorting_state(self) -> None:
        """sorting_state テーブルに対して SELECT が実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.loadProcessedKeys()

        mock_conn.execute.assert_called_once()

    # --- insertRecord ---

    def test_insert_record_executes_insert_ignore_sql(self) -> None:
        """INSERT IGNORE INTO analysis_records が実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        record = AnalysisRecord(
            actor="actor_a", filename="img001.jpg", shootingDate="2026-04-01",
            angry=5.0, fear=2.0, happy=80.0, sad=3.0, surprise=4.0,
            disgust=1.0, neutral=5.0, faceAngle=1.5,
            isOccluded=False, face_embedding=[0.1] * 128,
        )
        repo.insertRecord(record)

        mock_conn.execute.assert_called_once()

    def test_insert_record_passes_correct_params(self) -> None:
        """全フィールドが正しい型で INSERT されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)
        embedding = [0.1] * 128

        record = AnalysisRecord(
            actor="actor_a", filename="img001.jpg", shootingDate="2026-04-01",
            angry=5.0, fear=2.0, happy=80.0, sad=3.0, surprise=4.0,
            disgust=1.0, neutral=5.0, faceAngle=1.5,
            isOccluded=True, face_embedding=embedding,
        )
        repo.insertRecord(record)

        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_insert_record_encodes_is_occluded_false_as_zero(self) -> None:
        """isOccluded=False が 0 としてエンコードされること（execute が呼ばれること）。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        record = AnalysisRecord(
            actor="a", filename="img.jpg", shootingDate="2026-04-01",
            angry=0, fear=0, happy=0, sad=0, surprise=0, disgust=0, neutral=100,
            faceAngle=0.0, isOccluded=False, face_embedding=[],
        )
        repo.insertRecord(record)

        mock_conn.execute.assert_called_once()

    def test_insert_record_commits_after_execute(self) -> None:
        """execute 後に conn.commit が呼ばれること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        record = AnalysisRecord(
            actor="a", filename="img.jpg", shootingDate="2026-04-01",
            angry=0, fear=0, happy=0, sad=0, surprise=0, disgust=0, neutral=100,
            faceAngle=0.0, isOccluded=False, face_embedding=[],
        )
        repo.insertRecord(record)

        mock_conn.commit.assert_called_once_with()

    # --- insertEntry ---

    def test_insert_entry_executes_insert_ignore_sql(self) -> None:
        """INSERT IGNORE が実行されること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        entry = AnalysisEntry(
            filename="img001.jpg",
            shootingDate="2026-04-01",
            score=0.8,
            selectionState="pending",
            selectedAt=None,
        )
        repo.insertEntry("actor_a", entry)

        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_insert_entry_commits_after_execute(self) -> None:
        """execute 後に conn.commit が呼ばれること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        entry = AnalysisEntry(filename="img001.jpg", shootingDate="2026-04-01")
        repo.insertEntry("actor_a", entry)

        mock_conn.commit.assert_called_once_with()

    def test_insert_entry_with_none_score(self) -> None:
        """score が None の場合も execute が呼ばれること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        entry = AnalysisEntry(filename="img001.jpg", shootingDate="2026-04-01", score=None)
        repo.insertEntry("actor_a", entry)

        mock_conn.execute.assert_called_once()

    def test_insert_entry_inserts_all_fields(self) -> None:
        """全フィールドで execute・commit が呼ばれること。"""
        repo, mock_engine = self._make_repo_with_engine()
        mock_conn = self._setup_conn(mock_engine)

        entry = AnalysisEntry(
            filename="photo.jpg",
            shootingDate="2026-05-01",
            score=0.95,
            selectionState="ok",
            selectedAt="2026-05-02 12:00:00",
        )
        repo.insertEntry("actor_b", entry)

        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()


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
        """isOccluded=True の結果を正しく返すこと。"""
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
# run
# ---------------------------------------------------------------------------


class TestRun:
    """run() のテスト。"""

    def _make_deps(self, tmp_path: Path):
        """DI 用の依存オブジェクトをまとめて返す。"""
        analyze_root = tmp_path / "analyze"
        analyze_root.mkdir()
        mock_engine = MagicMock()
        repo = AnalysisRepository(engine=mock_engine)
        analyzer = PhotoAnalyzer()
        return analyze_root, mock_engine, repo, analyzer

    def test_run_calls_run_analyze_by_default(self, tmp_path: Path) -> None:
        """mode='analyze' のとき _run_analyze が呼ばれること。"""
        analyze_root, mock_engine, repo, analyzer = self._make_deps(tmp_path)

        with patch("src.analysis.main._load_env"):
            with patch("src.analysis.main._run_analyze") as mock_analyze:
                run(
                    mode="analyze",
                    analyzer=analyzer,
                    repository=repo,
                    analyze_root=analyze_root,
                    engine=mock_engine,
                )

        mock_analyze.assert_called_once_with(analyze_root, analyzer, repo, max_workers=2)

    def test_run_calls_run_scoring(self, tmp_path: Path) -> None:
        """mode='scoring' のとき _run_scoring が呼ばれること。"""
        analyze_root, mock_engine, repo, analyzer = self._make_deps(tmp_path)

        with patch("src.analysis.main._load_env"):
            with patch("src.analysis.main._run_scoring") as mock_scoring:
                run(
                    mode="scoring",
                    repository=repo,
                    analyze_root=analyze_root,
                    engine=mock_engine,
                )

        mock_scoring.assert_called_once_with()

    def test_run_calls_run_finalize(self, tmp_path: Path) -> None:
        """mode='finalize' のとき _run_finalize が呼ばれること。"""
        analyze_root, mock_engine, repo, analyzer = self._make_deps(tmp_path)

        with patch("src.analysis.main._load_env"):
            with patch("src.analysis.main._run_finalize") as mock_finalize:
                run(
                    mode="finalize",
                    repository=repo,
                    analyze_root=analyze_root,
                    engine=mock_engine,
                )

        mock_finalize.assert_called_once_with()

    def test_run_creates_default_instances_from_env(self, tmp_path: Path) -> None:
        """依存オブジェクトを省略した場合、環境変数からインスタンスを生成すること。"""
        analyze_root = tmp_path / "analyze"
        mock_engine = MagicMock()

        with patch("src.analysis.main._load_env"):
            with patch("src.analysis.main._run_analyze") as mock_analyze:
                with patch("src.analysis.main._create_engine", return_value=mock_engine):
                    with patch.dict(
                        "os.environ",
                        {"ANALYZE_ROOT": str(analyze_root)},
                    ):
                        run(mode="analyze")

        mock_analyze.assert_called_once()
        called_analyze_root, called_analyzer, called_repo = mock_analyze.call_args[0]
        assert called_analyze_root == analyze_root
        assert isinstance(called_analyzer, PhotoAnalyzer)
        assert isinstance(called_repo, AnalysisRepository)

    def test_run_calls_load_env(self, tmp_path: Path) -> None:
        """run() の冒頭で _load_env が呼ばれること。"""
        analyze_root, mock_engine, repo, _ = self._make_deps(tmp_path)

        with patch("src.analysis.main._load_env") as mock_load_env:
            with patch("src.analysis.main._run_analyze"):
                run(
                    mode="analyze",
                    repository=repo,
                    analyze_root=analyze_root,
                    engine=mock_engine,
                )

        mock_load_env.assert_called_once_with()


# ---------------------------------------------------------------------------
# _run_analyze
# ---------------------------------------------------------------------------


class TestRunAnalyze:
    """_run_analyze のテスト。"""

    def _make_deps(self, tmp_path: Path):
        """テスト用の依存オブジェクトを返す。"""
        analyze_root = tmp_path
        repo = MagicMock(spec=AnalysisRepository)
        analyzer = MagicMock(spec=PhotoAnalyzer)
        # デフォルト: 処理済みなし
        repo.loadRecords.return_value = []
        repo.loadProcessedKeys.return_value = set()
        return analyze_root, repo, analyzer

    def test_exits_early_when_analyze_root_not_exists(self, tmp_path: Path) -> None:
        """ANALYZE_ROOT が存在しない場合、処理を中断すること。"""
        analyze_root = tmp_path / "nonexistent"
        repo = MagicMock(spec=AnalysisRepository)
        analyzer = MagicMock(spec=PhotoAnalyzer)

        _run_analyze(analyze_root, analyzer, repo)

        repo.loadRecords.assert_not_called()
        analyzer.analyze.assert_not_called()

    def test_exits_early_when_no_actor_dirs(self, tmp_path: Path) -> None:
        """ANALYZE_ROOT に被写体ディレクトリが無い場合、処理を中断すること。"""
        analyze_root = tmp_path
        _, repo, analyzer = self._make_deps(tmp_path)

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(analyze_root, analyzer, repo)

        repo.loadRecords.assert_not_called()
        analyzer.analyze.assert_not_called()

    def test_exits_early_when_no_image_files(self, tmp_path: Path) -> None:
        """被写体ディレクトリにファイルが無い場合、解析を呼ばないこと。"""
        analyze_root = tmp_path
        (analyze_root / "actor_a").mkdir()
        _, repo, analyzer = self._make_deps(tmp_path)

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(analyze_root, analyzer, repo)

        analyzer.analyze.assert_not_called()

    def test_analyzes_image_and_saves(self, tmp_path: Path) -> None:
        """画像ファイルを解析して DB INSERT を行うこと（ファイルは移動しない）。"""
        analyze_root = tmp_path
        actor_dir = analyze_root / "actor_a"
        actor_dir.mkdir()
        img_path = actor_dir / "img001.jpg"
        img_path.touch()

        record = AnalysisRecord(
            actor="actor_a", filename="img001.jpg", shootingDate="2026-04-01",
            angry=5.0, fear=2.0, happy=80.0, sad=3.0,
            surprise=4.0, disgust=1.0, neutral=5.0,
            faceAngle=0.0, isOccluded=False, face_embedding=[0.1] * 128,
        )
        _, repo, analyzer = self._make_deps(tmp_path)
        analyzer.analyze.return_value = record

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(analyze_root, analyzer, repo)

        # analyze の引数を検証
        analyzer.analyze.assert_called_once_with(img_path, "actor_a")

        # insertRecord の呼び出しを検証
        repo.insertRecord.assert_called_once_with(record)

        # insertEntry の呼び出しを検証 (score = max(80)/100 = 0.8)
        repo.insertEntry.assert_called_once_with(
            "actor_a",
            AnalysisEntry(
                filename="img001.jpg",
                shootingDate="2026-04-01",
                score=0.8,
                selectionState="pending",
                selectedAt=None,
            ),
        )

        # ファイルは ANALYZE_ROOT に残ること
        assert img_path.exists()

    def test_tqdm_called_with_entries_and_desc(self, tmp_path: Path) -> None:
        """tqdm が entries リスト・desc='解析'・unit='枚' で呼ばれること。"""
        analyze_root = tmp_path
        actor_dir = analyze_root / "actor_a"
        actor_dir.mkdir()
        (actor_dir / "img001.jpg").touch()

        record = AnalysisRecord(
            actor="actor_a", filename="img001.jpg", shootingDate="2026-04-01",
            angry=0, fear=0, happy=80, sad=0, surprise=0, disgust=0, neutral=20,
            faceAngle=0.0, isOccluded=False, face_embedding=[0.1] * 128,
        )
        _, repo, analyzer = self._make_deps(tmp_path)
        analyzer.analyze.return_value = record

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x) as mock_tqdm:
            _run_analyze(analyze_root, analyzer, repo)

        mock_tqdm.assert_called_once()
        call_kwargs = mock_tqdm.call_args[1]
        assert call_kwargs.get("desc") == "解析"
        assert call_kwargs.get("unit") == "枚"
        assert call_kwargs.get("total") == 1

    def test_skips_already_processed_files(self, tmp_path: Path) -> None:
        """sorting_state に既に存在するファイルはスキップすること。"""
        analyze_root = tmp_path
        actor_dir = analyze_root / "actor_a"
        actor_dir.mkdir()
        (actor_dir / "img001.jpg").touch()

        _, repo, analyzer = self._make_deps(tmp_path)
        # img001.jpg は処理済み
        repo.loadProcessedKeys.return_value = {("actor_a", "img001.jpg")}

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(analyze_root, analyzer, repo)

        analyzer.analyze.assert_not_called()
        repo.insertRecord.assert_not_called()
        repo.insertEntry.assert_not_called()

    def test_processes_only_unprocessed_files(self, tmp_path: Path) -> None:
        """処理済みをスキップして未処理のみ解析すること。"""
        analyze_root = tmp_path
        actor_dir = analyze_root / "actor_a"
        actor_dir.mkdir()
        (actor_dir / "img001.jpg").touch()
        (actor_dir / "img002.jpg").touch()

        record = AnalysisRecord(
            actor="actor_a", filename="img002.jpg", shootingDate="2026-04-01",
            angry=0, fear=0, happy=80, sad=0, surprise=0, disgust=0, neutral=20,
            faceAngle=0.0, isOccluded=False, face_embedding=[0.1] * 128,
        )
        _, repo, analyzer = self._make_deps(tmp_path)
        # img001.jpg のみ処理済み
        repo.loadProcessedKeys.return_value = {("actor_a", "img001.jpg")}
        analyzer.analyze.return_value = record

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(analyze_root, analyzer, repo)

        # img002.jpg のみ解析されること
        analyzer.analyze.assert_called_once_with(analyze_root / "actor_a" / "img002.jpg", "actor_a")

    def test_does_not_add_duplicate_record(self, tmp_path: Path) -> None:
        """既存の (actor, filename) と同じレコードは analysis_records に追加しないこと。"""
        analyze_root = tmp_path
        actor_dir = analyze_root / "actor_a"
        actor_dir.mkdir()
        (actor_dir / "img001.jpg").touch()

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

        _, repo, analyzer = self._make_deps(tmp_path)
        repo.loadRecords.return_value = [existing_record]
        analyzer.analyze.return_value = new_record

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(analyze_root, analyzer, repo)

        repo.insertRecord.assert_not_called()

    def test_handles_null_record_gracefully(self, tmp_path: Path) -> None:
        """analyze が None を返した場合、score=None で insertEntry を呼ぶこと。"""
        analyze_root = tmp_path
        actor_dir = analyze_root / "actor_a"
        actor_dir.mkdir()
        img_path = actor_dir / "img001.jpg"
        img_path.touch()

        _, repo, analyzer = self._make_deps(tmp_path)
        analyzer.analyze.return_value = None

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            with patch("src.analysis.main._get_shooting_date", return_value="2026-04-01"):
                _run_analyze(analyze_root, analyzer, repo)

        repo.insertRecord.assert_not_called()
        repo.insertEntry.assert_called_once()
        call_args = repo.insertEntry.call_args[0]
        assert call_args[0] == "actor_a"
        assert call_args[1].score is None
        assert call_args[1].filename == "img001.jpg"

    def test_processes_multiple_actors(self, tmp_path: Path) -> None:
        """複数の actor のファイルを処理すること。"""
        analyze_root = tmp_path
        for actor in ["actor_a", "actor_b"]:
            actor_dir = analyze_root / actor
            actor_dir.mkdir()
            (actor_dir / "img.jpg").touch()

        record_a = AnalysisRecord("actor_a", "img.jpg", "2026-04-01", 0, 0, 80, 0, 0, 0, 20, 0.0, False, [0.1] * 128)
        record_b = AnalysisRecord("actor_b", "img.jpg", "2026-04-01", 0, 0, 70, 0, 0, 0, 30, 0.0, False, [0.1] * 128)

        _, repo, analyzer = self._make_deps(tmp_path)
        analyzer.analyze.side_effect = [record_a, record_b]

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(analyze_root, analyzer, repo)

        assert analyzer.analyze.call_count == 2
        assert repo.insertEntry.call_count == 2

    def test_all_actors_processed(self, tmp_path: Path) -> None:
        """全被写体のファイルが処理されること（並列実行のため順序は保証しない）。"""
        analyze_root = tmp_path
        for actor in ["charlie", "alice", "bob"]:
            (analyze_root / actor).mkdir()
            (analyze_root / actor / "img.jpg").touch()

        _, repo, analyzer = self._make_deps(tmp_path)
        record = AnalysisRecord("actor", "img.jpg", "2026-04-01", 0, 0, 80, 0, 0, 0, 20, 0.0, False, [0.1] * 128)
        analyzer.analyze.return_value = record

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(analyze_root, analyzer, repo)

        processed_actors = {c[0][1] for c in analyzer.analyze.call_args_list}  # actor 引数
        assert processed_actors == {"alice", "bob", "charlie"}
        assert analyzer.analyze.call_count == 3

    def test_insert_called_after_analyze(self, tmp_path: Path) -> None:
        """insertRecord・insertEntry は analyze より後に呼ばれること。"""
        analyze_root = tmp_path
        actor_dir = analyze_root / "actor_a"
        actor_dir.mkdir()
        (actor_dir / "img001.jpg").touch()

        record = AnalysisRecord(
            actor="actor_a", filename="img001.jpg", shootingDate="2026-04-01",
            angry=0, fear=0, happy=80, sad=0, surprise=0, disgust=0, neutral=20,
            faceAngle=0.0, isOccluded=False, face_embedding=[0.1] * 128,
        )
        _, repo, analyzer = self._make_deps(tmp_path)
        analyzer.analyze.return_value = record

        call_order = []
        repo.insertRecord.side_effect = lambda *a, **kw: call_order.append("insertRecord")
        repo.insertEntry.side_effect = lambda *a, **kw: call_order.append("insertEntry")
        analyzer.analyze.side_effect = lambda *a, **kw: call_order.append("analyze") or record

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(analyze_root, analyzer, repo)

        assert call_order == ["analyze", "insertRecord", "insertEntry"]

    def test_max_workers_is_passed_to_thread_pool(self, tmp_path: Path) -> None:
        """max_workers が ThreadPoolExecutor に渡されること。"""
        analyze_root = tmp_path
        actor_dir = analyze_root / "actor_a"
        actor_dir.mkdir()
        (actor_dir / "img001.jpg").touch()

        _, repo, analyzer = self._make_deps(tmp_path)
        record = AnalysisRecord(
            actor="actor_a", filename="img001.jpg", shootingDate="2026-04-01",
            angry=0, fear=0, happy=80, sad=0, surprise=0, disgust=0, neutral=20,
            faceAngle=0.0, isOccluded=False, face_embedding=[0.1] * 128,
        )
        analyzer.analyze.return_value = record

        with patch("src.analysis.main.ThreadPoolExecutor") as mock_executor_cls:
            mock_executor = MagicMock()
            mock_executor_cls.return_value.__enter__ = MagicMock(return_value=mock_executor)
            mock_executor_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_executor.submit.return_value = MagicMock(spec=Future)
            mock_executor.submit.return_value.result.return_value = None
            with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: iter([])):
                _run_analyze(analyze_root, analyzer, repo, max_workers=3)

        mock_executor_cls.assert_called_once_with(max_workers=3)

    def test_worker_exception_is_caught_and_logged(self, tmp_path: Path, capsys) -> None:
        """ワーカースレッドで例外が発生した場合、WARN ログを出力して処理を継続すること。"""
        analyze_root = tmp_path
        actor_dir = analyze_root / "actor_a"
        actor_dir.mkdir()
        (actor_dir / "img001.jpg").touch()

        _, repo, analyzer = self._make_deps(tmp_path)
        analyzer.analyze.side_effect = RuntimeError("unexpected failure")

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            # 例外が呼び出し元に伝播しないこと
            _run_analyze(analyze_root, analyzer, repo)

        captured = capsys.readouterr()
        assert "[WARN]" in captured.out
        assert "actor_a/img001.jpg" in captured.out

    def test_subdirectories_in_actor_dir_are_ignored(self, tmp_path: Path) -> None:
        """被写体ディレクトリ内のサブディレクトリはスキップすること。"""
        analyze_root = tmp_path
        actor_dir = analyze_root / "actor_a"
        actor_dir.mkdir()
        (actor_dir / "img001.jpg").touch()
        (actor_dir / "subdir").mkdir()  # サブディレクトリは無視

        record = AnalysisRecord(
            actor="actor_a", filename="img001.jpg", shootingDate="2026-04-01",
            angry=0, fear=0, happy=80, sad=0, surprise=0, disgust=0, neutral=20,
            faceAngle=0.0, isOccluded=False, face_embedding=[0.1] * 128,
        )
        _, repo, analyzer = self._make_deps(tmp_path)
        analyzer.analyze.return_value = record

        with patch("src.analysis.main.tqdm", side_effect=lambda x, **kw: x):
            _run_analyze(analyze_root, analyzer, repo)

        # ファイル 1 件のみ処理されること
        assert analyzer.analyze.call_count == 1
        analyzer.analyze.assert_called_once_with(actor_dir / "img001.jpg", "actor_a")


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
        """引数なしのとき run(mode='analyze', max_workers=2) が呼ばれること。"""
        with patch("sys.argv", ["main.py"]):
            with patch("src.analysis.main.run") as mock_run:
                main()

        mock_run.assert_called_once_with(mode="analyze", max_workers=2)

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

    def test_main_passes_workers_flag_to_run(self) -> None:
        """--workers N フラグが run(max_workers=N) に渡されること。"""
        with patch("sys.argv", ["main.py", "--workers", "4"]):
            with patch("src.analysis.main.run") as mock_run:
                main()

        mock_run.assert_called_once_with(mode="analyze", max_workers=4)
