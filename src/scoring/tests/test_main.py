"""src.scoring.main のユニットテスト。"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from src.analysis.main import AnalysisRecord
from src.scoring.main import (
    ModelTrainer,
    PhotoScorer,
    ScoringRepository,
    _display_training_result,
    _extract_features,
    _load_env,
    _run_scoring_for_actor,
    run,
)

# ---------------------------------------------------------------------------
# テストデータ定数
# ---------------------------------------------------------------------------

_BASE_ENTRY = {
    "filename": "img.jpg",
    "shootingDate": "2026-04-01",
    "score": None,
    "selectionState": "pending",
    "learned": False,
    "selectedAt": None,
}


# ---------------------------------------------------------------------------
# _load_env
# ---------------------------------------------------------------------------


class TestLoadEnv:
    """_load_env のテスト。"""

    def test_calls_load_dotenv_with_override_false(self) -> None:
        """load_dotenv が override=False で呼ばれること。"""
        with patch("src.scoring.main.load_dotenv") as mock_load:
            _load_env()

        mock_load.assert_called_once_with(override=False)


# ---------------------------------------------------------------------------
# _extract_features
# ---------------------------------------------------------------------------


class TestExtractFeatures:
    """_extract_features のテスト。"""

    # Facenet 埋め込みの次元数
    _FACENET_DIM = 128

    def _make_record(self, is_occluded: bool = False, embedding: list = None) -> AnalysisRecord:
        """テスト用 AnalysisRecord を生成する。"""
        return AnalysisRecord(
            actor="actor_a",
            filename="img.jpg",
            shootingDate="2026-04-01",
            angry=10.0,
            fear=5.0,
            happy=70.0,
            sad=3.0,
            surprise=4.0,
            disgust=2.0,
            neutral=6.0,
            faceAngle=1.5,
            isOccluded=is_occluded,
            face_embedding=embedding if embedding is not None else [0.5] * self._FACENET_DIM,
        )

    def test_returns_correct_feature_vector(self) -> None:
        """感情 7 + 顔角度 1 + 遮蔽物 1 + Facenet 128 の計 137 次元を返すこと。"""
        embedding = [float(i) for i in range(self._FACENET_DIM)]
        record = self._make_record(is_occluded=False, embedding=embedding)

        result = _extract_features(record)

        expected_head = [10.0, 5.0, 70.0, 3.0, 4.0, 2.0, 6.0, 1.5, 0.0]
        assert result[:9] == expected_head
        assert result[9:] == embedding
        assert len(result) == 9 + self._FACENET_DIM

    def test_is_occluded_true_encodes_as_one(self) -> None:
        """isOccluded=True の場合、1.0 がエンコードされること。"""
        record = self._make_record(is_occluded=True)

        result = _extract_features(record)

        assert result[8] == 1.0

    def test_is_occluded_false_encodes_as_zero(self) -> None:
        """isOccluded=False の場合、0.0 がエンコードされること。"""
        record = self._make_record(is_occluded=False)

        result = _extract_features(record)

        assert result[8] == 0.0

    def test_embedding_appended_to_features(self) -> None:
        """face_embedding が特徴量ベクトルの末尾に連結されること。"""
        embedding = [float(i) * 0.01 for i in range(self._FACENET_DIM)]
        record = self._make_record(embedding=embedding)

        result = _extract_features(record)

        assert result[9:] == embedding


# ---------------------------------------------------------------------------
# ScoringRepository
# ---------------------------------------------------------------------------


class TestScoringRepository:
    """ScoringRepository のテスト。"""

    def _make_repo(self, tmp_path: Path) -> ScoringRepository:
        """テスト用リポジトリを生成する（mock Engine 使用）。"""
        mock_engine = MagicMock()
        return ScoringRepository(
            data_root=tmp_path / "project",
            engine=mock_engine,
        )

    def _make_repo_with_engine(self, tmp_path: Path):
        """テスト用リポジトリと mock Engine を両方返す。"""
        mock_engine = MagicMock()
        repo = ScoringRepository(
            data_root=tmp_path / "project",
            engine=mock_engine,
        )
        return repo, mock_engine

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

    def _make_record(self) -> AnalysisRecord:
        """テスト用 AnalysisRecord を生成する。"""
        return AnalysisRecord(
            actor="actor_a",
            filename="img.jpg",
            shootingDate="2026-04-01",
            angry=0,
            fear=0,
            happy=80,
            sad=0,
            surprise=0,
            disgust=0,
            neutral=20,
            faceAngle=0.0,
            isOccluded=False,
            face_embedding=[0.1] * 128,
        )

    # --- loadRecords ---

    def test_load_records_returns_empty_when_no_rows(
        self, tmp_path: Path
    ) -> None:
        """analysis_records テーブルが空の場合、空リストを返すこと。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        self._setup_conn(mock_engine, rows=[])

        result = repo.loadRecords()

        assert result == []

    def test_load_records_returns_records_from_db(self, tmp_path: Path) -> None:
        """analysis_records テーブルのレコードを AnalysisRecord に変換して返すこと。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        embedding = [0.1] * 128
        row = SimpleNamespace(
            actor="actor_a",
            filename="img.jpg",
            shooting_date="2026-04-01",
            angry=0, fear=0, happy=80, sad=0,
            surprise=0, disgust=0, neutral=20,
            face_angle=0.0,
            is_occluded=0,
            face_embedding=json.dumps(embedding),
        )
        self._setup_conn(mock_engine, rows=[row])

        result = repo.loadRecords()

        assert len(result) == 1
        assert result[0].actor == "actor_a"
        assert result[0].filename == "img.jpg"
        assert result[0].face_embedding == embedding

    def test_load_records_executes_select_query(self, tmp_path: Path) -> None:
        """SELECT クエリが analysis_records テーブルに対して実行されること。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.loadRecords()

        mock_conn.execute.assert_called_once()

    # --- getActors ---

    def test_get_actors_returns_actor_ids_from_db(self, tmp_path: Path) -> None:
        """sorting_state テーブルから被写体 ID 一覧を返すこと。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        rows = [
            SimpleNamespace(actor_id="actor_a"),
            SimpleNamespace(actor_id="actor_b"),
        ]
        self._setup_conn(mock_engine, rows=rows)

        result = repo.getActors()

        assert result == ["actor_a", "actor_b"]

    def test_get_actors_executes_distinct_query(self, tmp_path: Path) -> None:
        """DISTINCT actor_id を ORDER BY で取得するクエリが実行されること。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.getActors()

        mock_conn.execute.assert_called_once()

    def test_get_actors_returns_empty_when_no_rows(self, tmp_path: Path) -> None:
        """テーブルが空の場合、空リストを返すこと。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        self._setup_conn(mock_engine, rows=[])

        result = repo.getActors()

        assert result == []

    # --- loadActorEntries ---

    def test_load_actor_entries_returns_dicts_from_db(self, tmp_path: Path) -> None:
        """sorting_state テーブルから dict リストを返すこと。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        row = SimpleNamespace(
            filename="img.jpg",
            shooting_date="2026-04-01",
            score=0.8,
            selection_state="ok",
            learned=False,
            selected_at=None,
        )
        self._setup_conn(mock_engine, rows=[row])

        result = repo.loadActorEntries("actor_a")

        assert len(result) == 1
        assert result[0]["filename"] == "img.jpg"
        assert result[0]["score"] == 0.8
        assert result[0]["selectionState"] == "ok"
        assert result[0]["learned"] is False

    def test_load_actor_entries_includes_learned_field(self, tmp_path: Path) -> None:
        """learned フィールドが bool 型で返されること。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        row = SimpleNamespace(
            filename="img.jpg",
            shooting_date="2026-04-01",
            score=None,
            selection_state="pending",
            learned=1,
            selected_at=None,
        )
        self._setup_conn(mock_engine, rows=[row])

        result = repo.loadActorEntries("actor_a")

        assert result[0]["learned"] is True

    def test_load_actor_entries_selects_learned_column(self, tmp_path: Path) -> None:
        """execute が呼ばれること（learned カラムを含む SELECT）。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.loadActorEntries("actor_a")

        mock_conn.execute.assert_called_once()

    def test_load_actor_entries_queries_with_actor_id(self, tmp_path: Path) -> None:
        """actor_id をパラメータとしてクエリが実行されること。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.loadActorEntries("actor_b")

        mock_conn.execute.assert_called_once()

    def test_load_actor_entries_returns_empty_when_no_rows(self, tmp_path: Path) -> None:
        """対象 actor のレコードが無い場合、空リストを返すこと。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        self._setup_conn(mock_engine, rows=[])

        result = repo.loadActorEntries("actor_a")

        assert result == []

    def test_load_actor_entries_order_by_does_not_use_nulls_last(self, tmp_path: Path) -> None:
        """MariaDB 非対応の NULLS LAST 構文を使わず IS NULL で NULL を末尾に並べること。"""
        from sqlalchemy.dialects import mysql as mysql_dialect

        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        mock_conn = self._setup_conn(mock_engine, rows=[])

        repo.loadActorEntries("actor_a")

        stmt = mock_conn.execute.call_args.args[0]
        compiled_sql = stmt.compile(dialect=mysql_dialect.dialect()).string

        assert "NULLS LAST" not in compiled_sql
        assert "IS NULL" in compiled_sql

    # --- updateScore ---

    def test_update_score_executes_update_sql(self, tmp_path: Path) -> None:
        """UPDATE sorting_state SQL が score を更新すること。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        mock_conn = self._setup_conn(mock_engine)

        repo.updateScore("actor_a", "img001.jpg", "2026-04-01", 0.85)

        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_update_score_commits_after_execute(self, tmp_path: Path) -> None:
        """execute 後に commit が呼ばれること。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        mock_conn = self._setup_conn(mock_engine)

        repo.updateScore("actor_a", "img001.jpg", "2026-04-01", 0.75)

        mock_conn.commit.assert_called_once_with()

    def test_update_score_does_not_set_learned(self, tmp_path: Path) -> None:
        """updateScore が learned を更新しないこと（pending エントリの score のみ更新）。"""
        from sqlalchemy.dialects import mysql as mysql_dialect

        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        mock_conn = self._setup_conn(mock_engine)

        repo.updateScore("actor_a", "img001.jpg", "2026-04-01", 0.85)

        stmt = mock_conn.execute.call_args.args[0]
        compiled_sql = stmt.compile(dialect=mysql_dialect.dialect()).string

        assert "learned" not in compiled_sql

    # --- saveModel ---

    def test_save_model_calls_joblib_dump(self, tmp_path: Path) -> None:
        """joblib.dump が正しいパスとモデルで呼ばれること。"""
        repo = self._make_repo(tmp_path)
        (tmp_path / "project").mkdir(parents=True, exist_ok=True)
        model = MagicMock()

        with patch("src.scoring.main.joblib.dump") as mock_dump:
            repo.saveModel("actor_a", model)

        expected_path = tmp_path / "project" / "actor_a_model.joblib"
        mock_dump.assert_called_once_with(model, expected_path)

    def test_save_model_creates_dir(self, tmp_path: Path) -> None:
        """モデルディレクトリが無くても作成して保存できること。"""
        repo = self._make_repo(tmp_path)

        with patch("src.scoring.main.joblib.dump"):
            repo.saveModel("actor_a", MagicMock())

        assert (tmp_path / "project").exists()

    # --- markLearned ---

    def test_mark_learned_executes_update_sql(self, tmp_path: Path) -> None:
        """UPDATE sorting_state で learned = true をセットするクエリが実行されること。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        mock_conn = self._setup_conn(mock_engine)

        repo.markLearned("actor_a", "img001.jpg", "2026-04-01")

        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    def test_mark_learned_commits_after_execute(self, tmp_path: Path) -> None:
        """execute 後に commit が呼ばれること。"""
        repo, mock_engine = self._make_repo_with_engine(tmp_path)
        mock_conn = self._setup_conn(mock_engine)

        repo.markLearned("actor_a", "img001.jpg", "2026-04-01")

        mock_conn.commit.assert_called_once_with()


# ---------------------------------------------------------------------------
# ModelTrainer
# ---------------------------------------------------------------------------


class TestModelTrainer:
    """ModelTrainer のテスト。"""

    def test_train_uses_gridsearch_cv3_when_enough_samples(self) -> None:
        """各クラス 3 件以上で GridSearchCV が cv=3 で呼ばれること。"""
        mock_estimator = MagicMock()
        mock_gs_instance = MagicMock()
        mock_gs_instance.best_estimator_ = mock_estimator
        mock_rf_instance = MagicMock()

        features = [[float(i), float(i + 1)] for i in range(6)]
        labels = [1, 1, 1, 0, 0, 0]

        expected_param_grid = {
            "n_estimators": [50, 100, 200],
            "max_depth": [None, 5, 10],
            "min_samples_split": [2, 5],
        }

        with patch(
            "src.scoring.main.GridSearchCV", return_value=mock_gs_instance
        ) as mock_gs:
            with patch(
                "src.scoring.main.RandomForestClassifier",
                return_value=mock_rf_instance,
            ) as mock_rf:
                trainer = ModelTrainer()
                result = trainer.train(features, labels)

        mock_rf.assert_called_once_with(random_state=42)
        mock_gs.assert_called_once_with(
            mock_rf_instance,
            expected_param_grid,
            cv=3,
            scoring="accuracy",
            n_jobs=-1,
        )
        mock_gs_instance.fit.assert_called_once()
        assert result == mock_estimator

    def test_train_uses_gridsearch_cv2_when_two_samples_per_class(self) -> None:
        """各クラス 2 件で GridSearchCV が cv=2 で呼ばれること。"""
        mock_gs_instance = MagicMock()
        mock_gs_instance.best_estimator_ = MagicMock()
        mock_rf_instance = MagicMock()

        features = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]]
        labels = [1, 1, 0, 0]

        with patch(
            "src.scoring.main.GridSearchCV", return_value=mock_gs_instance
        ) as mock_gs:
            with patch(
                "src.scoring.main.RandomForestClassifier",
                return_value=mock_rf_instance,
            ):
                trainer = ModelTrainer()
                trainer.train(features, labels)

        mock_gs.assert_called_once()
        assert mock_gs.call_args[1]["cv"] == 2

    def test_train_fits_directly_when_one_sample_per_class(self) -> None:
        """各クラス 1 件で CV できない場合、直接学習すること。"""
        mock_rf_instance = MagicMock()

        features = [[1.0, 2.0], [3.0, 4.0]]
        labels = [1, 0]  # 各 1 件 → cv_folds = min(3,1,1) = 1 < 2

        with patch("src.scoring.main.GridSearchCV") as mock_gs:
            with patch(
                "src.scoring.main.RandomForestClassifier",
                return_value=mock_rf_instance,
            ):
                trainer = ModelTrainer()
                result = trainer.train(features, labels)

        mock_gs.assert_not_called()
        mock_rf_instance.fit.assert_called_once()
        assert result == mock_rf_instance

    def test_train_fits_directly_when_single_class_only(self) -> None:
        """ok のみの単一クラスで CV できない場合、直接学習すること。"""
        mock_rf_instance = MagicMock()

        features = [[1.0, 2.0], [3.0, 4.0]]
        labels = [1, 1]  # ok のみ → n_ng=0, cv_folds=0

        with patch("src.scoring.main.GridSearchCV") as mock_gs:
            with patch(
                "src.scoring.main.RandomForestClassifier",
                return_value=mock_rf_instance,
            ):
                trainer = ModelTrainer()
                result = trainer.train(features, labels)

        mock_gs.assert_not_called()
        mock_rf_instance.fit.assert_called_once()
        assert result == mock_rf_instance


# ---------------------------------------------------------------------------
# PhotoScorer
# ---------------------------------------------------------------------------


class TestPhotoScorer:
    """PhotoScorer のテスト。"""

    def test_score_returns_ok_probabilities(self) -> None:
        """ok クラス（1）の確率をスコアとして返すこと。"""
        mock_model = MagicMock()
        mock_model.classes_ = [0, 1]
        mock_model.predict_proba.return_value = [[0.2, 0.8], [0.7, 0.3]]

        scorer = PhotoScorer()
        result = scorer.score(mock_model, [[1.0, 2.0], [3.0, 4.0]])

        mock_model.predict_proba.assert_called_once()
        assert result == [0.8, 0.3]

    def test_score_returns_zeros_when_no_ok_class(self) -> None:
        """classes_ に ok クラス（1）が無い場合、0.0 のリストを返すこと。"""
        mock_model = MagicMock()
        mock_model.classes_ = [0]

        scorer = PhotoScorer()
        result = scorer.score(mock_model, [[1.0, 2.0], [3.0, 4.0]])

        mock_model.predict_proba.assert_not_called()
        assert result == [0.0, 0.0]

    def test_score_rounds_to_4_decimal_places(self) -> None:
        """スコアが小数点以下 4 桁で丸められること。"""
        mock_model = MagicMock()
        mock_model.classes_ = [0, 1]
        mock_model.predict_proba.return_value = [[0.0, 0.123456789]]

        scorer = PhotoScorer()
        result = scorer.score(mock_model, [[1.0]])

        assert result == [0.1235]


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    """run のテスト。"""

    def _make_mocks(self):
        """テスト用モックセットを生成する。"""
        mock_repo = MagicMock()
        mock_repo.loadRecords.return_value = []
        mock_repo.getActors.return_value = []
        mock_trainer = MagicMock()
        mock_scorer = MagicMock()
        mock_engine = MagicMock()
        return mock_repo, mock_trainer, mock_scorer, mock_engine

    def test_calls_load_env(self) -> None:
        """_load_env が呼ばれること。"""
        mock_repo, mock_trainer, mock_scorer, mock_engine = self._make_mocks()

        with patch("src.scoring.main._load_env") as mock_load_env:
            with patch("src.scoring.main.tqdm", side_effect=lambda x, **kw: x):
                run(
                    repository=mock_repo,
                    trainer=mock_trainer,
                    scorer=mock_scorer,
                    data_root=Path("/tmp/proj"),
                    engine=mock_engine,
                )

        mock_load_env.assert_called_once()

    def test_uses_env_vars_when_no_di(self, monkeypatch) -> None:
        """DI が無い場合、環境変数からパスを取得し Engine を生成すること。"""
        monkeypatch.setenv("DATA_ROOT", "/tmp/project")
        mock_engine = MagicMock()

        with patch("src.scoring.main._load_env"):
            with patch("src.scoring.main.tqdm", side_effect=lambda x, **kw: x):
                with patch("src.scoring.main._create_engine", return_value=mock_engine) as mock_create_engine:
                    with patch("src.scoring.main.ScoringRepository") as mock_repo_cls:
                        with patch("src.scoring.main.ModelTrainer"):
                            with patch("src.scoring.main.PhotoScorer"):
                                mock_repo_cls.return_value.loadRecords.return_value = []
                                mock_repo_cls.return_value.getActors.return_value = []

                                run()

        mock_create_engine.assert_called_once()
        mock_repo_cls.assert_called_once_with(Path("/tmp/project"), mock_engine)

    def test_calls_scoring_for_each_actor(self) -> None:
        """各 actor に対して _run_scoring_for_actor が呼ばれること。"""
        mock_repo, mock_trainer, mock_scorer, mock_engine = self._make_mocks()
        mock_repo.getActors.return_value = ["actor_a", "actor_b"]

        with patch("src.scoring.main._load_env"):
            with patch("src.scoring.main.tqdm", side_effect=lambda x, **kw: x):
                with patch("src.scoring.main._run_scoring_for_actor") as mock_scoring:
                    run(
                        repository=mock_repo,
                        trainer=mock_trainer,
                        scorer=mock_scorer,
                        data_root=Path("/tmp/proj"),
                        engine=mock_engine,
                    )

        assert mock_scoring.call_count == 2
        actors_called = [c.args[0] for c in mock_scoring.call_args_list]
        assert actors_called == ["actor_a", "actor_b"]

    def test_tqdm_called_with_actors_desc_and_unit(self) -> None:
        """tqdm が actors・desc='Scoring'・unit='actor' で呼ばれること。"""
        mock_repo, mock_trainer, mock_scorer, mock_engine = self._make_mocks()
        mock_repo.getActors.return_value = ["actor_a", "actor_b"]

        with patch("src.scoring.main._load_env"):
            with patch("src.scoring.main.tqdm", side_effect=lambda x, **kw: x) as mock_tqdm:
                with patch("src.scoring.main._run_scoring_for_actor"):
                    run(
                        repository=mock_repo,
                        trainer=mock_trainer,
                        scorer=mock_scorer,
                        data_root=Path("/tmp/proj"),
                        engine=mock_engine,
                    )

        mock_tqdm.assert_called_once_with(["actor_a", "actor_b"], desc="Scoring", unit="actor")

    def test_loads_records_and_builds_record_map(self) -> None:
        """loadRecords が呼ばれ、record_map が構築されること。"""
        mock_repo, mock_trainer, mock_scorer, mock_engine = self._make_mocks()
        record = AnalysisRecord(
            actor="actor_a",
            filename="img.jpg",
            shootingDate="2026-04-01",
            angry=0,
            fear=0,
            happy=80,
            sad=0,
            surprise=0,
            disgust=0,
            neutral=20,
            faceAngle=0.0,
            isOccluded=False,
            face_embedding=[0.1] * 128,
        )
        mock_repo.loadRecords.return_value = [record]
        mock_repo.getActors.return_value = ["actor_a"]

        captured_record_map = {}

        def capture_scoring(actor, repo, trainer, scorer, record_map):
            captured_record_map.update(record_map)

        with patch("src.scoring.main._load_env"):
            with patch("src.scoring.main.tqdm", side_effect=lambda x, **kw: x):
                with patch(
                    "src.scoring.main._run_scoring_for_actor", side_effect=capture_scoring
                ):
                    run(
                        repository=mock_repo,
                        trainer=mock_trainer,
                        scorer=mock_scorer,
                        data_root=Path("/tmp/proj"),
                        engine=mock_engine,
                    )

        assert ("actor_a", "img.jpg") in captured_record_map
        assert captured_record_map[("actor_a", "img.jpg")] == record


# ---------------------------------------------------------------------------
# _run_scoring_for_actor
# ---------------------------------------------------------------------------


class TestRunScoringForActor:
    """_run_scoring_for_actor のテスト。"""

    def _make_record(
        self, filename: str, actor: str = "actor_a"
    ) -> AnalysisRecord:
        """テスト用 AnalysisRecord を生成する。"""
        return AnalysisRecord(
            actor=actor,
            filename=filename,
            shootingDate="2026-04-01",
            angry=0,
            fear=0,
            happy=80,
            sad=0,
            surprise=0,
            disgust=0,
            neutral=20,
            faceAngle=0.0,
            isOccluded=False,
            face_embedding=[0.1] * 128,
        )

    def _make_mock_repo(self, entries: list) -> MagicMock:
        """loadActorEntries が entries を返す mock リポジトリを生成する。"""
        repo = MagicMock(spec=ScoringRepository)
        repo.loadActorEntries.return_value = entries
        return repo

    # --- 学習なし ---

    def test_skips_training_when_no_labeled_entries(self) -> None:
        """labeled エントリが無い場合、学習・スコアリングがスキップされること。"""
        entries = [
            {
                "filename": "img.jpg",
                "shootingDate": "2026-04-01",
                "score": None,
                "selectionState": "pending",
                "learned": False,
                "selectedAt": None,
            }
        ]
        mock_trainer = MagicMock()
        mock_scorer = MagicMock()

        _run_scoring_for_actor(
            "actor_a",
            self._make_mock_repo(entries),
            mock_trainer,
            mock_scorer,
            {},
        )

        mock_trainer.train.assert_not_called()
        mock_scorer.score.assert_not_called()

    def test_trains_with_single_class_labeled_entries(self) -> None:
        """labeled エントリが単一クラスのみでも学習が実行されること。"""
        entries = [
            {
                "filename": "img1.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "learned": False,
                "selectedAt": None,
            },
            {
                "filename": "img2.jpg",
                "shootingDate": "2026-04-01",
                "score": None,
                "selectionState": "pending",
                "learned": False,
                "selectedAt": None,
            },
        ]
        record_map = {("actor_a", "img1.jpg"): self._make_record("img1.jpg")}
        mock_trainer = MagicMock()
        mock_scorer = MagicMock()

        _run_scoring_for_actor(
            "actor_a",
            self._make_mock_repo(entries),
            mock_trainer,
            mock_scorer,
            record_map,
        )

        mock_trainer.train.assert_called_once()
        mock_scorer.score.assert_not_called()  # img2.jpg が record_map に存在しないためスコアリング対象なし

    def test_skips_training_when_no_matching_records_in_pki(self) -> None:
        """labeled エントリが analysis.pki に存在しない場合、学習がスキップされること。"""
        entries = [
            {
                "filename": "img1.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "learned": False,
                "selectedAt": None,
            },
            {
                "filename": "img2.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "learned": False,
                "selectedAt": None,
            },
        ]
        mock_trainer = MagicMock()
        mock_scorer = MagicMock()

        # record_map が空 → マッチするレコードなし
        _run_scoring_for_actor(
            "actor_a",
            self._make_mock_repo(entries),
            mock_trainer,
            mock_scorer,
            {},
        )

        mock_trainer.train.assert_not_called()
        mock_scorer.score.assert_not_called()

    # --- 学習あり ---

    def test_trains_with_labeled_entries(self) -> None:
        """ok/ng の labeled エントリとレコードが揃っている場合、学習が実行されること。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "learned": False,
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "learned": False,
                "selectedAt": None,
            },
        ]
        record_map = {
            ("actor_a", "ok.jpg"): self._make_record("ok.jpg"),
            ("actor_a", "ng.jpg"): self._make_record("ng.jpg"),
        }
        mock_trainer = MagicMock()
        mock_scorer = MagicMock()
        repo = self._make_mock_repo(entries)

        _run_scoring_for_actor(
            "actor_a",
            repo,
            mock_trainer,
            mock_scorer,
            record_map,
        )

        mock_trainer.train.assert_called_once()
        features, labels = mock_trainer.train.call_args.args
        assert len(features) == 2
        assert set(labels) == {0, 1}

    def test_train_receives_correct_labels(self) -> None:
        """ok=1 / ng=0 のラベルで学習が呼ばれること。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "learned": False,
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "learned": False,
                "selectedAt": None,
            },
        ]
        record_map = {
            ("actor_a", "ok.jpg"): self._make_record("ok.jpg"),
            ("actor_a", "ng.jpg"): self._make_record("ng.jpg"),
        }
        mock_trainer = MagicMock()
        mock_scorer = MagicMock()
        repo = self._make_mock_repo(entries)

        _run_scoring_for_actor(
            "actor_a",
            repo,
            mock_trainer,
            mock_scorer,
            record_map,
        )

        _, labels = mock_trainer.train.call_args.args
        assert 1 in labels  # ok → 1
        assert 0 in labels  # ng → 0

    def test_scores_pending_entries_and_calls_update_score(self) -> None:
        """pending エントリがスコアリングされ、updateScore が呼ばれること。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "learned": False,
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "learned": False,
                "selectedAt": None,
            },
            {
                "filename": "pending.jpg",
                "shootingDate": "2026-04-01",
                "score": None,
                "selectionState": "pending",
                "learned": False,
                "selectedAt": None,
            },
        ]
        record_map = {
            ("actor_a", "ok.jpg"): self._make_record("ok.jpg"),
            ("actor_a", "ng.jpg"): self._make_record("ng.jpg"),
            ("actor_a", "pending.jpg"): self._make_record("pending.jpg"),
        }
        mock_trainer = MagicMock()
        mock_model = MagicMock()
        mock_trainer.train.return_value = mock_model
        mock_scorer = MagicMock()
        mock_scorer.score.return_value = [0.75]
        repo = self._make_mock_repo(entries)

        _run_scoring_for_actor(
            "actor_a", repo, mock_trainer, mock_scorer, record_map
        )

        mock_scorer.score.assert_called_once()
        repo.updateScore.assert_called_once_with(
            "actor_a", "pending.jpg", "2026-04-01", 0.75
        )

    def test_update_score_not_called_for_labeled_entries(self) -> None:
        """labeled エントリに対して updateScore が呼ばれないこと。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "learned": False,
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "learned": False,
                "selectedAt": None,
            },
        ]
        record_map = {
            ("actor_a", "ok.jpg"): self._make_record("ok.jpg"),
            ("actor_a", "ng.jpg"): self._make_record("ng.jpg"),
        }
        repo = self._make_mock_repo(entries)

        _run_scoring_for_actor(
            "actor_a", repo, MagicMock(), MagicMock(), record_map
        )

        repo.updateScore.assert_not_called()

    def test_skips_scoring_when_no_pending_records_in_pki(self) -> None:
        """pending エントリが analysis.pki に存在しない場合、スコアリングがスキップされること。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "learned": False,
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "learned": False,
                "selectedAt": None,
            },
            {
                "filename": "pending.jpg",
                "shootingDate": "2026-04-01",
                "score": None,
                "selectionState": "pending",
                "learned": False,
                "selectedAt": None,
            },
        ]
        # pending.jpg のレコードなし
        record_map = {
            ("actor_a", "ok.jpg"): self._make_record("ok.jpg"),
            ("actor_a", "ng.jpg"): self._make_record("ng.jpg"),
        }
        mock_trainer = MagicMock()
        mock_model = MagicMock()
        mock_trainer.train.return_value = mock_model
        mock_scorer = MagicMock()
        repo = self._make_mock_repo(entries)

        _run_scoring_for_actor(
            "actor_a",
            repo,
            mock_trainer,
            mock_scorer,
            record_map,
        )

        mock_scorer.score.assert_not_called()

    def test_saves_model_when_training_succeeds(self) -> None:
        """学習成功時に saveModel が正しい引数で呼ばれること。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "learned": False,
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "learned": False,
                "selectedAt": None,
            },
        ]
        record_map = {
            ("actor_a", "ok.jpg"): self._make_record("ok.jpg"),
            ("actor_a", "ng.jpg"): self._make_record("ng.jpg"),
        }
        mock_model = MagicMock()
        mock_trainer = MagicMock()
        mock_trainer.train.return_value = mock_model
        repo = self._make_mock_repo(entries)

        _run_scoring_for_actor(
            "actor_a", repo, mock_trainer, MagicMock(), record_map
        )

        repo.saveModel.assert_called_once_with("actor_a", mock_model)

    # --- 学習結果表示 ---

    def test_display_training_result_called_after_training(self) -> None:
        """学習成功時に _display_training_result が正しい引数で呼ばれること。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "learned": False,
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "learned": False,
                "selectedAt": None,
            },
        ]
        record_map = {
            ("actor_a", "ok.jpg"): self._make_record("ok.jpg"),
            ("actor_a", "ng.jpg"): self._make_record("ng.jpg"),
        }
        mock_model = MagicMock()
        mock_model.score.return_value = 0.95
        mock_trainer = MagicMock()
        mock_trainer.train.return_value = mock_model
        repo = self._make_mock_repo(entries)

        with patch("src.scoring.main._display_training_result") as mock_display:
            _run_scoring_for_actor(
                "actor_a", repo, mock_trainer, MagicMock(), record_map
            )

        mock_display.assert_called_once_with("actor_a", 1, 1, 0.95)

    def test_display_training_result_not_called_when_no_training(self) -> None:
        """学習がスキップされた場合は _display_training_result が呼ばれないこと。"""
        entries = [
            {
                "filename": "pending.jpg",
                "shootingDate": "2026-04-01",
                "score": None,
                "selectionState": "pending",
                "learned": False,
                "selectedAt": None,
            }
        ]
        repo = self._make_mock_repo(entries)

        with patch("src.scoring.main._display_training_result") as mock_display:
            _run_scoring_for_actor(
                "actor_a",
                repo,
                MagicMock(),
                MagicMock(),
                {},
            )

        mock_display.assert_not_called()


# ---------------------------------------------------------------------------
# _display_training_result
# ---------------------------------------------------------------------------


class TestDisplayTrainingResult:
    """_display_training_result のテスト。"""

    def test_prints_actor_ok_ng_accuracy(self, capsys) -> None:
        """actor・ok 数・ng 数・精度が出力されること。"""
        _display_training_result("actor_a", 10, 5, 0.9333)

        captured = capsys.readouterr()
        assert "actor_a" in captured.out
        assert "ok=10" in captured.out
        assert "ng=5" in captured.out
        assert "train_accuracy=0.9333" in captured.out

    def test_accuracy_formatted_to_4_decimal_places(self, capsys) -> None:
        """精度が小数点以下 4 桁でフォーマットされること。"""
        _display_training_result("actor_b", 3, 2, 0.666666)

        captured = capsys.readouterr()
        assert "0.6667" in captured.out

    def test_zero_samples_displayed(self, capsys) -> None:
        """ok=0 / ng=0 でもクラッシュせず表示されること。"""
        _display_training_result("actor_c", 0, 0, 0.0)

        captured = capsys.readouterr()
        assert "ok=0" in captured.out
        assert "ng=0" in captured.out
        assert "0.0000" in captured.out
