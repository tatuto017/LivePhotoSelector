"""src.scoring.main のユニットテスト。"""

import json
import pickle
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.analysis.main import AnalysisRecord
from src.scoring.main import (
    ModelTrainer,
    PhotoScorer,
    ScoringRepository,
    _extract_features,
    _load_env,
    _run_scoring_for_actor,
    run,
)


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
        """テスト用リポジトリを生成する。"""
        return ScoringRepository(
            project_root=tmp_path / "project",
            one_drive_root=tmp_path / "onedrive",
        )

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

    def test_load_records_returns_empty_when_file_not_exists(
        self, tmp_path: Path
    ) -> None:
        """analysis.pki が存在しない場合、空リストを返すこと。"""
        repo = self._make_repo(tmp_path)

        result = repo.loadRecords()

        assert result == []

    def test_load_records_returns_records(self, tmp_path: Path) -> None:
        """analysis.pki からレコードを読み込めること。"""
        repo = self._make_repo(tmp_path)
        records = [self._make_record()]
        pki_path = tmp_path / "onedrive" / "data" / "analysis.pki"
        pki_path.parent.mkdir(parents=True)
        with open(pki_path, "wb") as f:
            pickle.dump(records, f)

        result = repo.loadRecords()

        assert len(result) == 1
        assert result[0].actor == "actor_a"
        assert result[0].filename == "img.jpg"

    # --- getActors ---

    def test_get_actors_returns_empty_when_dir_not_exists(
        self, tmp_path: Path
    ) -> None:
        """data ディレクトリが存在しない場合、空リストを返すこと。"""
        repo = self._make_repo(tmp_path)

        result = repo.getActors()

        assert result == []

    def test_get_actors_returns_actor_ids(self, tmp_path: Path) -> None:
        """*_analysis.json のファイル名から被写体 ID 一覧を返すこと。"""
        repo = self._make_repo(tmp_path)
        data_dir = tmp_path / "onedrive" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "actor_a_analysis.json").write_text("[]")
        (data_dir / "actor_b_analysis.json").write_text("[]")

        result = repo.getActors()

        assert result == ["actor_a", "actor_b"]

    def test_get_actors_ignores_non_analysis_json(self, tmp_path: Path) -> None:
        """*_analysis.json 以外のファイルを無視すること。"""
        repo = self._make_repo(tmp_path)
        data_dir = tmp_path / "onedrive" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "actor_a_analysis.json").write_text("[]")
        (data_dir / "other.json").write_text("{}")

        result = repo.getActors()

        assert result == ["actor_a"]

    # --- loadActorEntries ---

    def test_load_actor_entries_returns_empty_when_file_not_exists(
        self, tmp_path: Path
    ) -> None:
        """{actor}_analysis.json が存在しない場合、空リストを返すこと。"""
        repo = self._make_repo(tmp_path)

        result = repo.loadActorEntries("actor_a")

        assert result == []

    def test_load_actor_entries_returns_raw_dicts(self, tmp_path: Path) -> None:
        """{actor}_analysis.json から raw dict リストを返すこと。"""
        repo = self._make_repo(tmp_path)
        data_dir = tmp_path / "onedrive" / "data"
        data_dir.mkdir(parents=True)
        entries = [
            {
                "filename": "img.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "selectedAt": None,
            }
        ]
        (data_dir / "actor_a_analysis.json").write_text(json.dumps(entries))

        result = repo.loadActorEntries("actor_a")

        assert result == entries

    # --- saveActorEntries ---

    def test_save_actor_entries_creates_dir_and_saves(self, tmp_path: Path) -> None:
        """ディレクトリが無くても作成して保存できること。"""
        repo = self._make_repo(tmp_path)
        entries = [{"filename": "img.jpg", "score": 0.9, "selectionState": "pending"}]

        repo.saveActorEntries("actor_a", entries)

        path = tmp_path / "onedrive" / "data" / "actor_a_analysis.json"
        assert path.exists()
        with open(path) as f:
            saved = json.load(f)
        assert saved == entries

    def test_save_actor_entries_overwrites_existing(self, tmp_path: Path) -> None:
        """既存ファイルを上書きできること。"""
        repo = self._make_repo(tmp_path)
        data_dir = tmp_path / "onedrive" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "actor_a_analysis.json").write_text(
            json.dumps([{"filename": "old.jpg"}])
        )

        new_entries = [{"filename": "new.jpg"}]
        repo.saveActorEntries("actor_a", new_entries)

        with open(data_dir / "actor_a_analysis.json") as f:
            saved = json.load(f)
        assert saved == new_entries

    # --- saveModel ---

    def test_save_model_calls_joblib_dump(self, tmp_path: Path) -> None:
        """joblib.dump が正しいパスとモデルで呼ばれること。"""
        repo = self._make_repo(tmp_path)
        (tmp_path / "onedrive" / "data").mkdir(parents=True)
        model = MagicMock()

        with patch("src.scoring.main.joblib.dump") as mock_dump:
            repo.saveModel("actor_a", model)

        expected_path = tmp_path / "onedrive" / "data" / "actor_a_model.joblib"
        mock_dump.assert_called_once_with(model, expected_path)

    def test_save_model_creates_dir(self, tmp_path: Path) -> None:
        """モデルディレクトリが無くても作成して保存できること。"""
        repo = self._make_repo(tmp_path)

        with patch("src.scoring.main.joblib.dump"):
            repo.saveModel("actor_a", MagicMock())

        assert (tmp_path / "onedrive" / "data").exists()


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
        return mock_repo, mock_trainer, mock_scorer

    def test_calls_load_env(self) -> None:
        """_load_env が呼ばれること。"""
        mock_repo, mock_trainer, mock_scorer = self._make_mocks()

        with patch("src.scoring.main._load_env") as mock_load_env:
            with patch("src.scoring.main.tqdm", side_effect=lambda x, **kw: x):
                run(
                    repository=mock_repo,
                    trainer=mock_trainer,
                    scorer=mock_scorer,
                    project_root=Path("/tmp/proj"),
                    one_drive_root=Path("/tmp/od"),
                )

        mock_load_env.assert_called_once()

    def test_uses_env_vars_when_no_di(self, monkeypatch) -> None:
        """DI が無い場合、環境変数からパスを取得すること。"""
        monkeypatch.setenv("PROJECT_ROOT", "/tmp/project")
        monkeypatch.setenv("ONE_DRIVE_ROOT", "/tmp/onedrive")

        with patch("src.scoring.main._load_env"):
            with patch("src.scoring.main.tqdm", side_effect=lambda x, **kw: x):
                with patch("src.scoring.main.ScoringRepository") as mock_repo_cls:
                    with patch("src.scoring.main.ModelTrainer"):
                        with patch("src.scoring.main.PhotoScorer"):
                            mock_repo_cls.return_value.loadRecords.return_value = []
                            mock_repo_cls.return_value.getActors.return_value = []

                            run()

        mock_repo_cls.assert_called_once_with(
            Path("/tmp/project"), Path("/tmp/onedrive")
        )

    def test_calls_scoring_for_each_actor(self) -> None:
        """各 actor に対して _run_scoring_for_actor が呼ばれること。"""
        mock_repo, mock_trainer, mock_scorer = self._make_mocks()
        mock_repo.getActors.return_value = ["actor_a", "actor_b"]

        with patch("src.scoring.main._load_env"):
            with patch("src.scoring.main.tqdm", side_effect=lambda x, **kw: x):
                with patch("src.scoring.main._run_scoring_for_actor") as mock_scoring:
                    run(
                        repository=mock_repo,
                        trainer=mock_trainer,
                        scorer=mock_scorer,
                        project_root=Path("/tmp/proj"),
                        one_drive_root=Path("/tmp/od"),
                    )

        assert mock_scoring.call_count == 2
        actors_called = [c.args[0] for c in mock_scoring.call_args_list]
        assert actors_called == ["actor_a", "actor_b"]

    def test_tqdm_called_with_actors_desc_and_unit(self) -> None:
        """tqdm が actors・desc='Scoring'・unit='actor' で呼ばれること。"""
        mock_repo, mock_trainer, mock_scorer = self._make_mocks()
        mock_repo.getActors.return_value = ["actor_a", "actor_b"]

        with patch("src.scoring.main._load_env"):
            with patch("src.scoring.main.tqdm", side_effect=lambda x, **kw: x) as mock_tqdm:
                with patch("src.scoring.main._run_scoring_for_actor"):
                    run(
                        repository=mock_repo,
                        trainer=mock_trainer,
                        scorer=mock_scorer,
                        project_root=Path("/tmp/proj"),
                        one_drive_root=Path("/tmp/od"),
                    )

        mock_tqdm.assert_called_once_with(["actor_a", "actor_b"], desc="Scoring", unit="actor")

    def test_loads_records_and_builds_record_map(self) -> None:
        """loadRecords が呼ばれ、record_map が構築されること。"""
        mock_repo, mock_trainer, mock_scorer = self._make_mocks()
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
                        project_root=Path("/tmp/proj"),
                        one_drive_root=Path("/tmp/od"),
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

    def _make_repo(self, tmp_path: Path) -> ScoringRepository:
        """テスト用リポジトリを生成する。"""
        return ScoringRepository(
            project_root=tmp_path / "project",
            one_drive_root=tmp_path / "onedrive",
        )

    def _write_actor_entries(
        self, tmp_path: Path, actor: str, entries: list
    ) -> None:
        """テスト用 {actor}_analysis.json を書き込む。"""
        data_dir = tmp_path / "onedrive" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        with open(data_dir / f"{actor}_analysis.json", "w") as f:
            json.dump(entries, f)

    # --- 学習なし ---

    def test_skips_training_when_no_labeled_entries(self, tmp_path: Path) -> None:
        """labeled エントリが無い場合、学習・スコアリングがスキップされること。"""
        entries = [
            {
                "filename": "img.jpg",
                "shootingDate": "2026-04-01",
                "score": None,
                "selectionState": "pending",
                "selectedAt": None,
            }
        ]
        self._write_actor_entries(tmp_path, "actor_a", entries)
        mock_trainer = MagicMock()
        mock_scorer = MagicMock()

        _run_scoring_for_actor(
            "actor_a",
            self._make_repo(tmp_path),
            mock_trainer,
            mock_scorer,
            {},
        )

        mock_trainer.train.assert_not_called()
        mock_scorer.score.assert_not_called()

    def test_skips_training_when_single_class_labels(self, tmp_path: Path) -> None:
        """labeled エントリが単一クラスのみの場合、学習がスキップされること。"""
        entries = [
            {
                "filename": "img1.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "selectedAt": None,
            },
            {
                "filename": "img2.jpg",
                "shootingDate": "2026-04-01",
                "score": None,
                "selectionState": "pending",
                "selectedAt": None,
            },
        ]
        self._write_actor_entries(tmp_path, "actor_a", entries)
        record_map = {("actor_a", "img1.jpg"): self._make_record("img1.jpg")}
        mock_trainer = MagicMock()
        mock_scorer = MagicMock()

        _run_scoring_for_actor(
            "actor_a",
            self._make_repo(tmp_path),
            mock_trainer,
            mock_scorer,
            record_map,
        )

        mock_trainer.train.assert_not_called()
        mock_scorer.score.assert_not_called()

    def test_skips_training_when_no_matching_records_in_pki(
        self, tmp_path: Path
    ) -> None:
        """labeled エントリが analysis.pki に存在しない場合、学習がスキップされること。"""
        entries = [
            {
                "filename": "img1.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "selectedAt": None,
            },
            {
                "filename": "img2.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "selectedAt": None,
            },
        ]
        self._write_actor_entries(tmp_path, "actor_a", entries)
        mock_trainer = MagicMock()
        mock_scorer = MagicMock()

        # record_map が空 → マッチするレコードなし
        _run_scoring_for_actor(
            "actor_a",
            self._make_repo(tmp_path),
            mock_trainer,
            mock_scorer,
            {},
        )

        mock_trainer.train.assert_not_called()
        mock_scorer.score.assert_not_called()

    # --- 学習あり ---

    def test_trains_with_labeled_entries(self, tmp_path: Path) -> None:
        """ok/ng の labeled エントリとレコードが揃っている場合、学習が実行されること。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "selectedAt": None,
            },
        ]
        self._write_actor_entries(tmp_path, "actor_a", entries)
        record_map = {
            ("actor_a", "ok.jpg"): self._make_record("ok.jpg"),
            ("actor_a", "ng.jpg"): self._make_record("ng.jpg"),
        }
        mock_trainer = MagicMock()
        mock_scorer = MagicMock()

        repo = self._make_repo(tmp_path)
        with patch.object(repo, "saveModel"):
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

    def test_train_receives_correct_labels(self, tmp_path: Path) -> None:
        """ok=1 / ng=0 のラベルで学習が呼ばれること。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "selectedAt": None,
            },
        ]
        self._write_actor_entries(tmp_path, "actor_a", entries)
        record_map = {
            ("actor_a", "ok.jpg"): self._make_record("ok.jpg"),
            ("actor_a", "ng.jpg"): self._make_record("ng.jpg"),
        }
        mock_trainer = MagicMock()
        mock_scorer = MagicMock()

        repo = self._make_repo(tmp_path)
        with patch.object(repo, "saveModel"):
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

    def test_scores_pending_entries(self, tmp_path: Path) -> None:
        """pending エントリがスコアリングされること。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "selectedAt": None,
            },
            {
                "filename": "pending.jpg",
                "shootingDate": "2026-04-01",
                "score": None,
                "selectionState": "pending",
                "selectedAt": None,
            },
        ]
        self._write_actor_entries(tmp_path, "actor_a", entries)
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

        repo = self._make_repo(tmp_path)
        with patch.object(repo, "saveModel"):
            _run_scoring_for_actor(
                "actor_a", repo, mock_trainer, mock_scorer, record_map
            )

        mock_scorer.score.assert_called_once()
        saved = repo.loadActorEntries("actor_a")
        pending_entry = next(e for e in saved if e["filename"] == "pending.jpg")
        assert pending_entry["score"] == 0.75

    def test_skips_scoring_when_no_pending_records_in_pki(
        self, tmp_path: Path
    ) -> None:
        """pending エントリが analysis.pki に存在しない場合、スコアリングがスキップされること。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "selectedAt": None,
            },
            {
                "filename": "pending.jpg",
                "shootingDate": "2026-04-01",
                "score": None,
                "selectionState": "pending",
                "selectedAt": None,
            },
        ]
        self._write_actor_entries(tmp_path, "actor_a", entries)
        # pending.jpg のレコードなし
        record_map = {
            ("actor_a", "ok.jpg"): self._make_record("ok.jpg"),
            ("actor_a", "ng.jpg"): self._make_record("ng.jpg"),
        }
        mock_trainer = MagicMock()
        mock_model = MagicMock()
        mock_trainer.train.return_value = mock_model
        mock_scorer = MagicMock()

        repo = self._make_repo(tmp_path)
        with patch.object(repo, "saveModel"):
            _run_scoring_for_actor(
                "actor_a",
                repo,
                mock_trainer,
                mock_scorer,
                record_map,
            )

        mock_scorer.score.assert_not_called()

    # --- ファイル保存 ---

    def test_keeps_labeled_entries_in_actor_json(self, tmp_path: Path) -> None:
        """labeled エントリが {actor}_analysis.json に残ること。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "selectedAt": None,
            },
            {
                "filename": "pending.jpg",
                "shootingDate": "2026-04-01",
                "score": None,
                "selectionState": "pending",
                "selectedAt": None,
            },
        ]
        self._write_actor_entries(tmp_path, "actor_a", entries)

        repo = self._make_repo(tmp_path)
        _run_scoring_for_actor(
            "actor_a", repo, MagicMock(), MagicMock(), {}
        )

        saved = repo.loadActorEntries("actor_a")
        filenames = [e["filename"] for e in saved]
        assert "ok.jpg" in filenames
        assert "pending.jpg" in filenames

    def test_saves_model_when_training_succeeds(self, tmp_path: Path) -> None:
        """学習成功時に saveModel が正しい引数で呼ばれること。"""
        entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "selectedAt": None,
            },
        ]
        self._write_actor_entries(tmp_path, "actor_a", entries)
        record_map = {
            ("actor_a", "ok.jpg"): self._make_record("ok.jpg"),
            ("actor_a", "ng.jpg"): self._make_record("ng.jpg"),
        }
        mock_model = MagicMock()
        mock_trainer = MagicMock()
        mock_trainer.train.return_value = mock_model

        repo = self._make_repo(tmp_path)
        with patch.object(repo, "saveModel") as mock_save_model:
            _run_scoring_for_actor(
                "actor_a", repo, mock_trainer, MagicMock(), record_map
            )

        mock_save_model.assert_called_once_with("actor_a", mock_model)

    # --- diff マージ ---

    def test_merges_score_only_when_pi_changed_file(self, tmp_path: Path) -> None:
        """Pi が selectionState を書き換えた場合、score のみ更新して他フィールドを保持すること。"""
        # スナップショット: pending.jpg は pending
        snapshot_entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "selectedAt": None,
            },
            {
                "filename": "pending.jpg",
                "shootingDate": "2026-04-01",
                "score": None,
                "selectionState": "pending",
                "selectedAt": None,
            },
        ]
        # current: Pi が pending.jpg を ok に変更
        current_entries = [
            {
                "filename": "ok.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.8,
                "selectionState": "ok",
                "selectedAt": None,
            },
            {
                "filename": "ng.jpg",
                "shootingDate": "2026-04-01",
                "score": 0.2,
                "selectionState": "ng",
                "selectedAt": None,
            },
            {
                "filename": "pending.jpg",
                "shootingDate": "2026-04-01",
                "score": None,
                "selectionState": "ok",
                "selectedAt": "2026-04-10T00:00:00.000Z",
            },
        ]
        record_map = {
            ("actor_a", "ok.jpg"): self._make_record("ok.jpg"),
            ("actor_a", "ng.jpg"): self._make_record("ng.jpg"),
            ("actor_a", "pending.jpg"): self._make_record("pending.jpg"),
        }

        repo = self._make_repo(tmp_path)
        mock_trainer = MagicMock()
        mock_model = MagicMock()
        mock_trainer.train.return_value = mock_model
        mock_scorer = MagicMock()
        mock_scorer.score.return_value = [0.9]

        # 1 回目の loadActorEntries → snapshot、2 回目 → current
        mock_load = MagicMock(side_effect=[snapshot_entries, current_entries])
        mock_save = MagicMock()
        repo.loadActorEntries = mock_load
        repo.saveActorEntries = mock_save
        repo.saveModel = MagicMock()

        _run_scoring_for_actor(
            "actor_a", repo, mock_trainer, mock_scorer, record_map
        )

        saved_entries = mock_save.call_args.args[1]
        # 全エントリが保存されること
        filenames_saved = [e["filename"] for e in saved_entries]
        assert "ok.jpg" in filenames_saved
        assert "ng.jpg" in filenames_saved
        assert "pending.jpg" in filenames_saved
        pending_entry = next(
            e for e in saved_entries if e["filename"] == "pending.jpg"
        )
        # Pi の selectionState/selectedAt 変更は保持
        assert pending_entry["selectionState"] == "ok"
        assert pending_entry["selectedAt"] == "2026-04-10T00:00:00.000Z"
        # score は更新
        assert pending_entry["score"] == 0.9
