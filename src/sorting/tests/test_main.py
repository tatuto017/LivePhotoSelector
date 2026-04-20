"""src.sorting.main のユニットテスト。"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# conftest.py で torch・clip がモック化されてから src.sorting.main をインポートする
from src.sorting.main import (
    Classifier,
    FeatureExtractor,
    FeatureRepository,
    Learner,
    _get_device,
    _load_env,
    _load_model,
    learn,
    run,
    FEATURES_FILE,
    MASTER_DIR,
    OUTPUT_DIR,
    TARGET_DIR,
)


# ---------------------------------------------------------------------------
# _load_env
# ---------------------------------------------------------------------------


class TestLoadEnv:
    """_load_env のテスト。"""

    def test_calls_load_dotenv_with_override_false(self) -> None:
        """load_dotenv が override=False で呼ばれること。"""
        with patch("src.sorting.main.load_dotenv") as mock_load:
            _load_env()

        mock_load.assert_called_once_with(override=False)


# ---------------------------------------------------------------------------
# _get_device
# ---------------------------------------------------------------------------


class TestGetDevice:
    """_get_device のテスト。"""

    def test_returns_mps_when_mps_available(self) -> None:
        """MPS が利用可能な場合 "mps" を返すこと。"""
        with patch("src.sorting.main.torch") as mock_torch:
            mock_torch.backends.mps.is_available.return_value = True

            result = _get_device()

        assert result == "mps"

    def test_returns_cpu_when_mps_unavailable(self) -> None:
        """MPS が利用不可の場合 "cpu" を返すこと。"""
        with patch("src.sorting.main.torch") as mock_torch:
            mock_torch.backends.mps.is_available.return_value = False

            result = _get_device()

        assert result == "cpu"


# ---------------------------------------------------------------------------
# _load_model
# ---------------------------------------------------------------------------


class TestLoadModel:
    """_load_model のテスト。"""

    def test_loads_clip_model_and_applies_float(self) -> None:
        """clip.load が呼ばれ、model.float() が適用されること。"""
        mock_model = MagicMock()
        mock_preprocess = MagicMock()

        with patch("src.sorting.main.clip") as mock_clip:
            mock_clip.load.return_value = (mock_model, mock_preprocess)

            result_model, result_preprocess = _load_model("cpu")

        mock_clip.load.assert_called_once_with("ViT-L/14", device="cpu")
        mock_model.float.assert_called_once()
        assert result_preprocess is mock_preprocess


# ---------------------------------------------------------------------------
# FeatureRepository
# ---------------------------------------------------------------------------


class TestFeatureRepository:
    """FeatureRepository のテスト。"""

    # --- loadFeatures ---

    def test_load_features_returns_empty_when_file_not_exists(self, tmp_path: Path) -> None:
        """features_path が存在しない場合、空辞書を返すこと。"""
        repo = FeatureRepository()
        features_path = tmp_path / "member_features.pt"

        result = repo.loadFeatures(features_path)

        assert result == {}

    def test_load_features_calls_torch_load_when_file_exists(self, tmp_path: Path) -> None:
        """features_path が存在する場合、torch.load が呼ばれること。"""
        repo = FeatureRepository()
        features_path = tmp_path / "member_features.pt"
        features_path.touch()

        mock_data = {"actor_a": MagicMock()}

        with patch("src.sorting.main.torch") as mock_torch:
            mock_torch.load.return_value = mock_data

            result = repo.loadFeatures(features_path)

        mock_torch.load.assert_called_once_with(
            str(features_path), map_location="cpu", weights_only=False
        )

    def test_load_features_applies_float_to_all_tensors(self, tmp_path: Path) -> None:
        """読み込んだ各 Tensor に .float() が適用されること。"""
        repo = FeatureRepository()
        features_path = tmp_path / "member_features.pt"
        features_path.touch()

        mock_tensor = MagicMock()
        mock_data = {"actor_a": mock_tensor}

        with patch("src.sorting.main.torch") as mock_torch:
            mock_torch.load.return_value = mock_data

            result = repo.loadFeatures(features_path)

        mock_tensor.float.assert_called_once()
        assert result == {"actor_a": mock_tensor.float.return_value}

    # --- saveFeatures ---

    def test_save_features_calls_torch_save_with_correct_args(self, tmp_path: Path) -> None:
        """torch.save が正しいパスと辞書で呼ばれること。"""
        repo = FeatureRepository()
        features_path = tmp_path / "member_features.pt"
        mock_tensor = MagicMock()
        features_db = {"actor_a": mock_tensor}

        with patch("src.sorting.main.torch") as mock_torch:
            repo.saveFeatures(features_path, features_db)

        mock_torch.save.assert_called_once_with(
            {"actor_a": mock_tensor}, str(features_path)
        )

    # --- listMasterActors ---

    def test_list_master_actors_returns_empty_when_dir_not_exists(self, tmp_path: Path) -> None:
        """master_dir が存在しない場合、空リストを返すこと。"""
        repo = FeatureRepository()
        master_dir = tmp_path / "master_photos"

        result = repo.listMasterActors(master_dir)

        assert result == []

    def test_list_master_actors_returns_only_directories(self, tmp_path: Path) -> None:
        """ディレクトリ名のみ返すこと（ファイルは除外）。"""
        repo = FeatureRepository()
        master_dir = tmp_path / "master_photos"
        master_dir.mkdir()
        (master_dir / "actor_a").mkdir()
        (master_dir / "actor_b").mkdir()
        (master_dir / "notes.txt").touch()

        result = repo.listMasterActors(master_dir)

        assert sorted(result) == ["actor_a", "actor_b"]

    # --- listActorImages ---

    def test_list_actor_images_returns_image_files(self, tmp_path: Path) -> None:
        """png・jpg・jpeg ファイルのみ返すこと。"""
        repo = FeatureRepository()
        actor_dir = tmp_path / "actor_a"

        with patch("src.sorting.main.os.listdir", return_value=["img1.jpg", "img2.png", "notes.txt"]):
            result = repo.listActorImages(actor_dir)

        assert sorted(result) == ["img1.jpg", "img2.png"]

    def test_list_actor_images_excludes_non_images(self, tmp_path: Path) -> None:
        """画像以外のファイルは返さないこと。"""
        repo = FeatureRepository()
        actor_dir = tmp_path / "actor_a"

        with patch("src.sorting.main.os.listdir", return_value=["readme.md", ".DS_Store"]):
            result = repo.listActorImages(actor_dir)

        assert result == []

    # --- listTargetImages ---

    def test_list_target_images_returns_image_files(self, tmp_path: Path) -> None:
        """png・jpg・jpeg ファイルのみ返すこと。"""
        repo = FeatureRepository()
        target_dir = tmp_path / "all_photos"

        with patch("src.sorting.main.os.listdir", return_value=["img1.jpg", "img2.png", "notes.txt"]):
            result = repo.listTargetImages(target_dir)

        assert sorted(result) == ["img1.jpg", "img2.png"]

    def test_list_target_images_excludes_non_images(self, tmp_path: Path) -> None:
        """画像以外のファイルは返さないこと。"""
        repo = FeatureRepository()
        target_dir = tmp_path / "all_photos"

        with patch("src.sorting.main.os.listdir", return_value=["readme.md", ".DS_Store"]):
            result = repo.listTargetImages(target_dir)

        assert result == []

    # --- moveImage ---

    def test_move_image_creates_dst_dir_and_moves_file(self, tmp_path: Path) -> None:
        """os.makedirs と shutil.move が正しい引数で呼ばれること。"""
        repo = FeatureRepository()
        src = tmp_path / "all_photos" / "img.jpg"
        dst_dir = tmp_path / "sorted_results" / "actor_a"

        with patch("src.sorting.main.os.makedirs") as mock_makedirs:
            with patch("src.sorting.main.shutil.move") as mock_move:
                repo.moveImage(src, dst_dir, "img.jpg")

        mock_makedirs.assert_called_once_with(str(dst_dir), exist_ok=True)
        mock_move.assert_called_once_with(str(src), str(dst_dir / "img.jpg"))

    # --- deleteImage ---

    def test_delete_image_calls_os_remove_with_correct_path(self, tmp_path: Path) -> None:
        """os.remove が正しいパスで呼ばれること。"""
        repo = FeatureRepository()
        img_path = tmp_path / "master_photos" / "actor_a" / "img.jpg"

        with patch("src.sorting.main.os.remove") as mock_remove:
            repo.deleteImage(img_path)

        mock_remove.assert_called_once_with(str(img_path))


# ---------------------------------------------------------------------------
# FeatureExtractor
# ---------------------------------------------------------------------------


class TestFeatureExtractor:
    """FeatureExtractor のテスト。"""

    def _make_extractor(self):
        """テスト用 FeatureExtractor を生成する。"""
        mock_model = MagicMock()
        mock_preprocess = MagicMock()
        return FeatureExtractor(mock_model, mock_preprocess, "cpu"), mock_model, mock_preprocess

    def test_extract_opens_image_with_path(self, tmp_path: Path) -> None:
        """Image.open が正しいパスで呼ばれること。"""
        extractor, _, _ = self._make_extractor()
        img_path = tmp_path / "img.jpg"

        with patch("src.sorting.main.Image.open") as mock_open:
            extractor.extract(img_path)

        mock_open.assert_called_once_with(str(img_path))

    def test_extract_calls_preprocess_with_opened_image(self, tmp_path: Path) -> None:
        """preprocess が Image.open の戻り値で呼ばれること。"""
        extractor, _, mock_preprocess = self._make_extractor()
        img_path = tmp_path / "img.jpg"
        mock_opened = MagicMock()

        with patch("src.sorting.main.Image.open", return_value=mock_opened):
            extractor.extract(img_path)

        mock_preprocess.assert_called_once_with(mock_opened)

    def test_extract_calls_encode_image_on_model(self, tmp_path: Path) -> None:
        """model.encode_image が呼ばれること。"""
        extractor, mock_model, _ = self._make_extractor()
        img_path = tmp_path / "img.jpg"

        with patch("src.sorting.main.Image.open"):
            extractor.extract(img_path)

        mock_model.encode_image.assert_called_once()

    def test_extract_normalizes_feature_vector(self, tmp_path: Path) -> None:
        """特徴量がノルムで正規化されること（feat /= feat.norm が呼ばれること）。"""
        extractor, mock_model, _ = self._make_extractor()
        img_path = tmp_path / "img.jpg"
        mock_feat = MagicMock()
        mock_model.encode_image.return_value = mock_feat

        with patch("src.sorting.main.Image.open"):
            result = extractor.extract(img_path)

        mock_feat.norm.assert_called_once_with(dim=-1, keepdim=True)


# ---------------------------------------------------------------------------
# Learner
# ---------------------------------------------------------------------------


class TestLearner:
    """Learner のテスト。"""

    def _make_learner(self):
        """テスト用 Learner を生成する。"""
        mock_repo = MagicMock(spec=FeatureRepository)
        mock_extractor = MagicMock(spec=FeatureExtractor)
        learner = Learner(mock_repo, mock_extractor)
        return learner, mock_repo, mock_extractor

    def test_learn_prints_and_returns_when_no_actors(self, tmp_path: Path, capsys) -> None:
        """master_dir に actor がいない場合、メッセージを出力して元の DB を返すこと。"""
        learner, mock_repo, _ = self._make_learner()
        mock_repo.listMasterActors.return_value = []
        features_path = tmp_path / FEATURES_FILE
        features_db = {"actor_a": MagicMock()}

        result = learner.learn(tmp_path / MASTER_DIR, features_path, features_db)

        captured = capsys.readouterr()
        assert "学習用データがありません。" in captured.out
        assert result is features_db
        mock_repo.saveFeatures.assert_not_called()

    def test_learn_skips_actor_with_no_images(self, tmp_path: Path) -> None:
        """画像のない actor はスキップされること。"""
        learner, mock_repo, mock_extractor = self._make_learner()
        mock_repo.listMasterActors.return_value = ["actor_a"]
        mock_repo.listActorImages.return_value = []
        features_path = tmp_path / FEATURES_FILE

        with patch("src.sorting.main.tqdm", side_effect=lambda x, **kw: x):
            learner.learn(tmp_path / MASTER_DIR, features_path, {})

        mock_extractor.extract.assert_not_called()

    def test_learn_extracts_features_and_deletes_image(self, tmp_path: Path) -> None:
        """特徴量抽出後に deleteImage が呼ばれること。"""
        learner, mock_repo, mock_extractor = self._make_learner()
        master_dir = tmp_path / MASTER_DIR
        mock_repo.listMasterActors.return_value = ["actor_a"]
        mock_repo.listActorImages.return_value = ["img.jpg"]
        features_path = tmp_path / FEATURES_FILE

        mock_feat = MagicMock()
        mock_extractor.extract.return_value = mock_feat

        with patch("src.sorting.main.tqdm", side_effect=lambda x, **kw: x):
            with patch("src.sorting.main.torch") as mock_torch:
                mock_torch.cat.return_value = MagicMock()
                learner.learn(master_dir, features_path, {})

        mock_extractor.extract.assert_called_once_with(master_dir / "actor_a" / "img.jpg")
        mock_repo.deleteImage.assert_called_once_with(master_dir / "actor_a" / "img.jpg")

    def test_learn_adds_new_actor_to_db(self, tmp_path: Path) -> None:
        """新規 actor の特徴量が DB に追加されること。"""
        learner, mock_repo, mock_extractor = self._make_learner()
        master_dir = tmp_path / MASTER_DIR
        mock_repo.listMasterActors.return_value = ["actor_new"]
        mock_repo.listActorImages.return_value = ["img.jpg"]
        features_path = tmp_path / FEATURES_FILE

        mock_feat = MagicMock()
        mock_extractor.extract.return_value = mock_feat
        mock_new_tensor = MagicMock()

        with patch("src.sorting.main.tqdm", side_effect=lambda x, **kw: x):
            with patch("src.sorting.main.torch") as mock_torch:
                mock_torch.cat.return_value = mock_new_tensor
                result = learner.learn(master_dir, features_path, {})

        assert "actor_new" in result
        assert result["actor_new"] is mock_new_tensor

    def test_learn_appends_to_existing_actor_in_db(self, tmp_path: Path) -> None:
        """既存 actor の特徴量が追記されること。"""
        learner, mock_repo, mock_extractor = self._make_learner()
        master_dir = tmp_path / MASTER_DIR
        mock_repo.listMasterActors.return_value = ["actor_a"]
        mock_repo.listActorImages.return_value = ["img.jpg"]
        features_path = tmp_path / FEATURES_FILE

        existing_tensor = MagicMock()
        features_db = {"actor_a": existing_tensor}

        mock_feat = MagicMock()
        mock_extractor.extract.return_value = mock_feat
        mock_new_tensor = MagicMock()
        mock_merged_tensor = MagicMock()

        with patch("src.sorting.main.tqdm", side_effect=lambda x, **kw: x):
            with patch("src.sorting.main.torch") as mock_torch:
                mock_torch.cat.side_effect = [mock_new_tensor, mock_merged_tensor]
                result = learner.learn(master_dir, features_path, features_db)

        # torch.cat が2回呼ばれ、2回目で既存テンソルと結合されること
        assert mock_torch.cat.call_count == 2
        assert result["actor_a"] is mock_merged_tensor

    def test_learn_handles_extract_error_gracefully(self, tmp_path: Path) -> None:
        """画像抽出でエラーが発生しても処理が続行されること。"""
        learner, mock_repo, mock_extractor = self._make_learner()
        master_dir = tmp_path / MASTER_DIR
        mock_repo.listMasterActors.return_value = ["actor_a"]
        mock_repo.listActorImages.return_value = ["bad.jpg", "good.jpg"]
        features_path = tmp_path / FEATURES_FILE

        mock_feat = MagicMock()
        mock_extractor.extract.side_effect = [Exception("error"), mock_feat]

        with patch("src.sorting.main.tqdm", side_effect=lambda x, **kw: x):
            with patch("src.sorting.main.tqdm.write"):
                with patch("src.sorting.main.torch") as mock_torch:
                    mock_torch.cat.return_value = MagicMock()
                    learner.learn(master_dir, features_path, {})

        # エラーが発生しても2枚目が処理されること
        assert mock_extractor.extract.call_count == 2
        # エラーした画像は削除されないこと
        mock_repo.deleteImage.assert_called_once_with(master_dir / "actor_a" / "good.jpg")

    def test_learn_saves_features_after_processing(self, tmp_path: Path) -> None:
        """学習後に saveFeatures が呼ばれること。"""
        learner, mock_repo, mock_extractor = self._make_learner()
        master_dir = tmp_path / MASTER_DIR
        mock_repo.listMasterActors.return_value = ["actor_a"]
        mock_repo.listActorImages.return_value = ["img.jpg"]
        features_path = tmp_path / FEATURES_FILE

        mock_extractor.extract.return_value = MagicMock()

        with patch("src.sorting.main.tqdm", side_effect=lambda x, **kw: x):
            with patch("src.sorting.main.torch") as mock_torch:
                mock_torch.cat.return_value = MagicMock()
                learner.learn(master_dir, features_path, {})

        mock_repo.saveFeatures.assert_called_once_with(features_path, mock_repo.saveFeatures.call_args[0][1])

    def test_learn_prints_completion_message(self, tmp_path: Path, capsys) -> None:
        """学習完了メッセージが出力されること。"""
        learner, mock_repo, mock_extractor = self._make_learner()
        master_dir = tmp_path / MASTER_DIR
        mock_repo.listMasterActors.return_value = ["actor_a"]
        mock_repo.listActorImages.return_value = ["img.jpg"]
        features_path = tmp_path / FEATURES_FILE

        mock_extractor.extract.return_value = MagicMock()

        with patch("src.sorting.main.tqdm", side_effect=lambda x, **kw: x):
            with patch("src.sorting.main.torch") as mock_torch:
                mock_torch.cat.return_value = MagicMock()
                learner.learn(master_dir, features_path, {})

        captured = capsys.readouterr()
        assert "学習が完了しました！" in captured.out


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class TestClassifier:
    """Classifier のテスト。"""

    def _make_classifier(self):
        """テスト用 Classifier を生成する。"""
        mock_repo = MagicMock(spec=FeatureRepository)
        mock_extractor = MagicMock(spec=FeatureExtractor)
        classifier = Classifier(mock_repo, mock_extractor)
        return classifier, mock_repo, mock_extractor

    def test_classify_prints_and_returns_when_no_features_db(self, tmp_path: Path, capsys) -> None:
        """features_db が空の場合、メッセージを出力して処理を終了すること。"""
        classifier, mock_repo, _ = self._make_classifier()

        classifier.classify(tmp_path / TARGET_DIR, tmp_path / OUTPUT_DIR, {})

        captured = capsys.readouterr()
        assert "学習データがありません。" in captured.out
        mock_repo.listTargetImages.assert_not_called()

    def test_classify_prints_and_returns_when_no_images(self, tmp_path: Path, capsys) -> None:
        """画像が存在しない場合、メッセージを出力して処理を終了すること。"""
        classifier, mock_repo, mock_extractor = self._make_classifier()
        mock_repo.listTargetImages.return_value = []
        features_db = {"actor_a": MagicMock()}

        classifier.classify(tmp_path / TARGET_DIR, tmp_path / OUTPUT_DIR, features_db)

        captured = capsys.readouterr()
        assert "画像が見つかりません。" in captured.out
        mock_extractor.extract.assert_not_called()

    def test_classify_moves_image_to_best_match_single_actor(self, tmp_path: Path) -> None:
        """1 actor の場合、その actor のディレクトリに画像が移動されること。"""
        classifier, mock_repo, mock_extractor = self._make_classifier()
        target_dir = tmp_path / TARGET_DIR
        output_dir = tmp_path / OUTPUT_DIR
        mock_repo.listTargetImages.return_value = ["img.jpg"]

        mock_tensor = MagicMock()
        features_db = {"actor_a": mock_tensor}

        mock_target_feat = MagicMock()
        mock_extractor.extract.return_value = mock_target_feat
        mock_score_tensor = MagicMock()
        mock_score_tensor.item.return_value = 0.9
        mock_target_feat.__matmul__ = MagicMock(return_value=mock_score_tensor)

        with patch("src.sorting.main.tqdm", side_effect=lambda x, **kw: x):
            classifier.classify(target_dir, output_dir, features_db)

        mock_repo.moveImage.assert_called_once_with(
            target_dir / "img.jpg",
            output_dir / "actor_a",
            "img.jpg",
        )

    def test_classify_selects_actor_with_highest_score(self, tmp_path: Path) -> None:
        """スコアが最大の actor のディレクトリに画像が移動されること。"""
        classifier, mock_repo, mock_extractor = self._make_classifier()
        target_dir = tmp_path / TARGET_DIR
        output_dir = tmp_path / OUTPUT_DIR
        mock_repo.listTargetImages.return_value = ["img.jpg"]

        mock_tensor_a = MagicMock()
        mock_tensor_b = MagicMock()
        features_db = {"actor_a": mock_tensor_a, "actor_b": mock_tensor_b}

        mock_target_feat = MagicMock()
        mock_extractor.extract.return_value = mock_target_feat

        mock_rep_a = MagicMock()
        mock_rep_b = MagicMock()
        mock_tensor_a.mean.return_value.float.return_value = mock_rep_a
        mock_tensor_b.mean.return_value.float.return_value = mock_rep_b

        def matmul_side_effect(x):
            result = MagicMock()
            if x is mock_rep_a.T:
                result.item.return_value = 0.3
            else:
                result.item.return_value = 0.9
            return result

        mock_target_feat.__matmul__ = MagicMock(side_effect=matmul_side_effect)

        with patch("src.sorting.main.tqdm", side_effect=lambda x, **kw: x):
            classifier.classify(target_dir, output_dir, features_db)

        mock_repo.moveImage.assert_called_once_with(
            target_dir / "img.jpg",
            output_dir / "actor_b",
            "img.jpg",
        )

    def test_classify_handles_error_gracefully(self, tmp_path: Path) -> None:
        """振り分け中にエラーが発生しても処理が続行されること。"""
        classifier, mock_repo, mock_extractor = self._make_classifier()
        target_dir = tmp_path / TARGET_DIR
        output_dir = tmp_path / OUTPUT_DIR
        mock_repo.listTargetImages.return_value = ["bad.jpg", "good.jpg"]
        features_db = {"actor_a": MagicMock()}

        mock_extractor.extract.side_effect = [Exception("error"), MagicMock()]

        with patch("src.sorting.main.tqdm", side_effect=lambda x, **kw: x):
            with patch("src.sorting.main.tqdm.write"):
                classifier.classify(target_dir, output_dir, features_db)

        assert mock_extractor.extract.call_count == 2

    def test_classify_prints_progress_message(self, tmp_path: Path, capsys) -> None:
        """振り分け開始メッセージが出力されること。"""
        classifier, mock_repo, mock_extractor = self._make_classifier()
        mock_repo.listTargetImages.return_value = ["img.jpg"]
        features_db = {"actor_a": MagicMock()}

        mock_target_feat = MagicMock()
        mock_extractor.extract.return_value = mock_target_feat
        mock_score = MagicMock()
        mock_score.item.return_value = 0.9
        mock_target_feat.__matmul__ = MagicMock(return_value=mock_score)

        with patch("src.sorting.main.tqdm", side_effect=lambda x, **kw: x):
            classifier.classify(tmp_path / TARGET_DIR, tmp_path / OUTPUT_DIR, features_db)

        captured = capsys.readouterr()
        assert "1枚の振り分けを開始します" in captured.out
        assert "すべての振り分けが完了しました！" in captured.out


# ---------------------------------------------------------------------------
# learn
# ---------------------------------------------------------------------------


class TestLearn:
    """learn のテスト。"""

    def _make_mocks(self):
        """テスト用モックセットを生成する。"""
        mock_repo = MagicMock(spec=FeatureRepository)
        mock_repo.loadFeatures.return_value = {}
        mock_extractor = MagicMock(spec=FeatureExtractor)
        mock_learner = MagicMock(spec=Learner)
        return mock_repo, mock_extractor, mock_learner

    def test_calls_load_env(self) -> None:
        """_load_env が呼ばれること。"""
        mock_repo, mock_extractor, mock_learner = self._make_mocks()

        with patch("src.sorting.main._load_env") as mock_load_env:
            learn(
                repository=mock_repo,
                extractor=mock_extractor,
                learner=mock_learner,
                sorting_root=Path("/tmp/sorting"),
            )

        mock_load_env.assert_called_once()

    def test_uses_sorting_root_env_var_when_not_provided(self, monkeypatch) -> None:
        """sorting_root が None の場合、SORTING_ROOT 環境変数からパスを取得すること。"""
        monkeypatch.setenv("SORTING_ROOT", "/tmp/sorting_test")
        mock_repo, mock_extractor, mock_learner = self._make_mocks()

        with patch("src.sorting.main._load_env"):
            learn(
                repository=mock_repo,
                extractor=mock_extractor,
                learner=mock_learner,
            )

        mock_repo.loadFeatures.assert_called_once_with(
            Path("/tmp/sorting_test") / FEATURES_FILE
        )

    def test_creates_extractor_when_not_provided(self, monkeypatch) -> None:
        """extractor が None の場合、_get_device・_load_model・FeatureExtractor で生成されること。"""
        monkeypatch.setenv("SORTING_ROOT", "/tmp/sorting")
        mock_repo, _, mock_learner = self._make_mocks()
        mock_model = MagicMock()
        mock_preprocess = MagicMock()

        with patch("src.sorting.main._load_env"):
            with patch("src.sorting.main._get_device", return_value="cpu") as mock_get_device:
                with patch("src.sorting.main._load_model", return_value=(mock_model, mock_preprocess)) as mock_load_model:
                    with patch("src.sorting.main.FeatureExtractor") as mock_extractor_cls:
                        learn(
                            repository=mock_repo,
                            learner=mock_learner,
                        )

        mock_get_device.assert_called_once()
        mock_load_model.assert_called_once_with("cpu")
        mock_extractor_cls.assert_called_once_with(mock_model, mock_preprocess, "cpu")

    def test_creates_repository_when_not_provided(self, monkeypatch) -> None:
        """repository が None の場合、FeatureRepository が生成されること。"""
        monkeypatch.setenv("SORTING_ROOT", "/tmp/sorting")
        _, mock_extractor, mock_learner = self._make_mocks()

        with patch("src.sorting.main._load_env"):
            with patch("src.sorting.main.FeatureRepository") as mock_repo_cls:
                mock_repo_cls.return_value.loadFeatures.return_value = {}
                learn(
                    extractor=mock_extractor,
                    learner=mock_learner,
                )

        mock_repo_cls.assert_called_once()

    def test_creates_learner_when_not_provided(self, monkeypatch) -> None:
        """learner が None の場合、Learner が生成されること。"""
        monkeypatch.setenv("SORTING_ROOT", "/tmp/sorting")
        mock_repo, mock_extractor, _ = self._make_mocks()

        with patch("src.sorting.main._load_env"):
            with patch("src.sorting.main.Learner") as mock_learner_cls:
                learn(
                    repository=mock_repo,
                    extractor=mock_extractor,
                )

        mock_learner_cls.assert_called_once_with(mock_repo, mock_extractor)

    def test_calls_load_features_then_learn(self) -> None:
        """loadFeatures → learner.learn の順に呼ばれること。"""
        mock_repo, mock_extractor, mock_learner = self._make_mocks()
        sorting_root = Path("/tmp/sorting")
        features_db = {"actor_a": MagicMock()}
        mock_repo.loadFeatures.return_value = features_db

        call_order = []
        mock_repo.loadFeatures.side_effect = lambda *a: (call_order.append("load"), features_db)[1]
        mock_learner.learn.side_effect = lambda *a: call_order.append("learn")

        with patch("src.sorting.main._load_env"):
            learn(
                repository=mock_repo,
                extractor=mock_extractor,
                learner=mock_learner,
                sorting_root=sorting_root,
            )

        assert call_order == ["load", "learn"]
        mock_learner.learn.assert_called_once_with(
            sorting_root / MASTER_DIR,
            sorting_root / FEATURES_FILE,
            features_db,
        )


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    """run のテスト。"""

    def _make_mocks(self):
        """テスト用モックセットを生成する。"""
        mock_repo = MagicMock(spec=FeatureRepository)
        mock_repo.loadFeatures.return_value = {}
        mock_extractor = MagicMock(spec=FeatureExtractor)
        mock_classifier = MagicMock(spec=Classifier)
        return mock_repo, mock_extractor, mock_classifier

    def test_calls_load_env(self) -> None:
        """_load_env が呼ばれること。"""
        mock_repo, mock_extractor, mock_classifier = self._make_mocks()

        with patch("src.sorting.main._load_env") as mock_load_env:
            run(
                repository=mock_repo,
                extractor=mock_extractor,
                classifier=mock_classifier,
                sorting_root=Path("/tmp/sorting"),
            )

        mock_load_env.assert_called_once()

    def test_uses_sorting_root_env_var_when_not_provided(self, monkeypatch) -> None:
        """sorting_root が None の場合、SORTING_ROOT 環境変数からパスを取得すること。"""
        monkeypatch.setenv("SORTING_ROOT", "/tmp/sorting_test")
        mock_repo, mock_extractor, mock_classifier = self._make_mocks()

        with patch("src.sorting.main._load_env"):
            run(
                repository=mock_repo,
                extractor=mock_extractor,
                classifier=mock_classifier,
            )

        mock_repo.loadFeatures.assert_called_once_with(
            Path("/tmp/sorting_test") / FEATURES_FILE
        )

    def test_creates_extractor_when_not_provided(self, monkeypatch) -> None:
        """extractor が None の場合、_get_device・_load_model・FeatureExtractor で生成されること。"""
        monkeypatch.setenv("SORTING_ROOT", "/tmp/sorting")
        mock_repo, _, mock_classifier = self._make_mocks()
        mock_model = MagicMock()
        mock_preprocess = MagicMock()

        with patch("src.sorting.main._load_env"):
            with patch("src.sorting.main._get_device", return_value="cpu") as mock_get_device:
                with patch("src.sorting.main._load_model", return_value=(mock_model, mock_preprocess)) as mock_load_model:
                    with patch("src.sorting.main.FeatureExtractor") as mock_extractor_cls:
                        run(
                            repository=mock_repo,
                            classifier=mock_classifier,
                        )

        mock_get_device.assert_called_once()
        mock_load_model.assert_called_once_with("cpu")
        mock_extractor_cls.assert_called_once_with(mock_model, mock_preprocess, "cpu")

    def test_creates_repository_when_not_provided(self, monkeypatch) -> None:
        """repository が None の場合、FeatureRepository が生成されること。"""
        monkeypatch.setenv("SORTING_ROOT", "/tmp/sorting")
        _, mock_extractor, mock_classifier = self._make_mocks()

        with patch("src.sorting.main._load_env"):
            with patch("src.sorting.main.FeatureRepository") as mock_repo_cls:
                mock_repo_cls.return_value.loadFeatures.return_value = {}
                run(
                    extractor=mock_extractor,
                    classifier=mock_classifier,
                )

        mock_repo_cls.assert_called_once()

    def test_creates_classifier_when_not_provided(self, monkeypatch) -> None:
        """classifier が None の場合、Classifier が生成されること。"""
        monkeypatch.setenv("SORTING_ROOT", "/tmp/sorting")
        mock_repo, mock_extractor, _ = self._make_mocks()

        with patch("src.sorting.main._load_env"):
            with patch("src.sorting.main.Classifier") as mock_classifier_cls:
                run(
                    repository=mock_repo,
                    extractor=mock_extractor,
                )

        mock_classifier_cls.assert_called_once_with(mock_repo, mock_extractor)

    def test_calls_load_features_then_classify(self) -> None:
        """loadFeatures → classifier.classify の順に呼ばれること。"""
        mock_repo, mock_extractor, mock_classifier = self._make_mocks()
        sorting_root = Path("/tmp/sorting")
        features_db = {"actor_a": MagicMock()}
        mock_repo.loadFeatures.return_value = features_db

        call_order = []
        mock_repo.loadFeatures.side_effect = lambda *a: (call_order.append("load"), features_db)[1]
        mock_classifier.classify.side_effect = lambda *a, **kw: call_order.append("classify")

        with patch("src.sorting.main._load_env"):
            run(
                repository=mock_repo,
                extractor=mock_extractor,
                classifier=mock_classifier,
                sorting_root=sorting_root,
            )

        assert call_order == ["load", "classify"]
        mock_classifier.classify.assert_called_once_with(
            sorting_root / TARGET_DIR,
            sorting_root / OUTPUT_DIR,
            features_db,
            max_workers=4,
        )
