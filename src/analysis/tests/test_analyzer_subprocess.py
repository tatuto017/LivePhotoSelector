"""src.analysis.analyzer_subprocess のユニットテスト。"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest
from PIL import Image as PILImage

from src.analysis.analyzer_subprocess import (
    _MAX_IMAGE_SIZE,
    _calculate_face_angle,
    _load_image_array,
    analyze,
    main,
)

# Facenet 埋め込みの次元数
_FACENET_DIM = 128


# ---------------------------------------------------------------------------
# _calculate_face_angle
# ---------------------------------------------------------------------------


class TestCalculateFaceAngle:
    """_calculate_face_angle のテスト。"""

    def test_returns_zero_for_horizontal_eyes(self) -> None:
        """左右の目が水平に並んでいる場合 0 度を返すこと。"""
        result = _calculate_face_angle([30, 40], [70, 40])
        assert result == pytest.approx(0.0)

    def test_returns_positive_angle_for_tilted_right(self) -> None:
        """右目が左目より下にある場合（右傾き）正の角度を返すこと。"""
        result = _calculate_face_angle([0, 0], [10, 10])
        assert result == pytest.approx(45.0)

    def test_returns_negative_angle_for_tilted_left(self) -> None:
        """右目が左目より上にある場合（左傾き）負の角度を返すこと。"""
        result = _calculate_face_angle([0, 10], [10, 0])
        assert result == pytest.approx(-45.0)

    def test_returns_zero_for_same_coordinates(self) -> None:
        """両目の座標が同じ場合 0 度を返すこと。"""
        result = _calculate_face_angle([0, 0], [0, 0])
        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _load_image_array
# ---------------------------------------------------------------------------


class TestLoadImageArray:
    """_load_image_array のテスト。"""

    def _save_image(self, tmp_path: Path, size: tuple, filename: str = "img.jpg") -> Path:
        """テスト用の JPEG 画像ファイルを作成して返す。"""
        img_path = tmp_path / filename
        PILImage.new("RGB", size, color=(128, 64, 32)).save(img_path, "JPEG")
        return img_path

    def test_returns_rgb_numpy_array(self, tmp_path: Path) -> None:
        """RGB numpy 配列を返すこと。"""
        img_path = self._save_image(tmp_path, (100, 100))

        result = _load_image_array(img_path)

        assert isinstance(result, np.ndarray)
        assert result.ndim == 3
        assert result.shape[2] == 3  # RGB

    def test_resizes_large_image_to_within_max_size(self, tmp_path: Path) -> None:
        """長辺が _MAX_IMAGE_SIZE を超える画像をリサイズすること。"""
        img_path = self._save_image(tmp_path, (1000, 800))

        result = _load_image_array(img_path)

        h, w = result.shape[:2]
        assert max(h, w) <= _MAX_IMAGE_SIZE

    def test_does_not_upscale_small_image(self, tmp_path: Path) -> None:
        """長辺が _MAX_IMAGE_SIZE 未満の画像を拡大しないこと。"""
        small_size = _MAX_IMAGE_SIZE // 2
        img_path = self._save_image(tmp_path, (small_size, small_size))

        result = _load_image_array(img_path)

        h, w = result.shape[:2]
        assert max(h, w) == small_size

    def test_preserves_aspect_ratio_on_resize(self, tmp_path: Path) -> None:
        """リサイズ時にアスペクト比を維持すること。"""
        # 2:1 のアスペクト比
        img_path = self._save_image(tmp_path, (1200, 600))

        result = _load_image_array(img_path)

        h, w = result.shape[:2]
        assert abs(w / h - 2.0) < 0.05  # アスペクト比が概ね 2:1 を維持


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------


class TestAnalyze:
    """analyze のテスト。"""

    # テスト用の固定 numpy 配列（DeepFace への入力として使用）
    _DUMMY_IMG_ARRAY = np.zeros((100, 100, 3), dtype=np.uint8)

    def _make_deepface_result(
        self,
        happy: float = 80.0,
        left_eye=None,
        right_eye=None,
    ) -> list:
        """DeepFace.analyze のモック戻り値を生成する。"""
        return [
            {
                "emotion": {
                    "angry": 5.0,
                    "fear": 2.0,
                    "happy": happy,
                    "sad": 3.0,
                    "surprise": 4.0,
                    "disgust": 1.0,
                    "neutral": 5.0,
                },
                "region": {
                    "left_eye": left_eye if left_eye is not None else [30, 40],
                    "right_eye": right_eye if right_eye is not None else [70, 40],
                },
            }
        ]

    def _make_mock_deepface(self, analyze_result=None, embedding=None):
        """sys.modules["deepface"] に差し込む MagicMock を生成する。"""
        mock_df = MagicMock()
        mock_df.analyze.return_value = (
            analyze_result if analyze_result is not None else self._make_deepface_result()
        )
        mock_df.represent.return_value = [
            {"embedding": embedding if embedding is not None else [0.1] * _FACENET_DIM}
        ]
        mock_module = MagicMock()
        mock_module.DeepFace = mock_df
        return mock_module, mock_df

    def test_returns_dict_on_success(self, tmp_path: Path) -> None:
        """正常系: 解析成功時に結果 dict を返すこと。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        mock_module, mock_df = self._make_mock_deepface()

        with patch("src.analysis.analyzer_subprocess._load_image_array", return_value=self._DUMMY_IMG_ARRAY) as mock_load:
            with patch.dict("sys.modules", {"deepface": mock_module}):
                result = analyze(img_path, "actor_a")

        assert result["actor"] == "actor_a"
        assert result["filename"] == "img.jpg"
        assert result["happy"] == pytest.approx(80.0)
        assert result["faceAngle"] == pytest.approx(0.0)  # 左右水平
        assert result["isOccluded"] is False  # 80/100 = 0.8 >= 0.4
        assert result["face_embedding"] == [0.1] * _FACENET_DIM

        # _load_image_array の引数検証
        mock_load.assert_called_once_with(img_path)

        # DeepFace.analyze に numpy 配列が渡されること
        mock_df.analyze.assert_called_once_with(
            img_path=self._DUMMY_IMG_ARRAY,
            actions=["emotion"],
            enforce_detection=False,
        )

        # DeepFace.represent に numpy 配列が渡されること
        mock_df.represent.assert_called_once_with(
            img_path=self._DUMMY_IMG_ARRAY,
            model_name="Facenet",
            enforce_detection=False,
        )

    def test_emotion_values_are_python_float(self, tmp_path: Path) -> None:
        """numpy.float32 ではなく Python float として返すこと（JSON 直列化対応）。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        numpy_result = [
            {
                "emotion": {
                    "angry": np.float32(5.0),
                    "fear": np.float32(2.0),
                    "happy": np.float32(80.0),
                    "sad": np.float32(3.0),
                    "surprise": np.float32(4.0),
                    "disgust": np.float32(1.0),
                    "neutral": np.float32(5.0),
                },
                "region": {"left_eye": [30, 40], "right_eye": [70, 40]},
            }
        ]
        mock_module, _ = self._make_mock_deepface(analyze_result=numpy_result)

        with patch("src.analysis.analyzer_subprocess._load_image_array", return_value=self._DUMMY_IMG_ARRAY):
            with patch.dict("sys.modules", {"deepface": mock_module}):
                result = analyze(img_path, "actor_a")

        # JSON シリアライズが成功すること（numpy.float32 は失敗する）
        serialized = json.dumps(result)
        assert isinstance(json.loads(serialized)["happy"], float)

    def test_face_embedding_values_are_python_float(self, tmp_path: Path) -> None:
        """face_embedding が Python float のリストとして返ること（JSON 直列化対応）。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        numpy_embedding = [np.float32(v) for v in [0.1] * _FACENET_DIM]
        mock_module, _ = self._make_mock_deepface(embedding=numpy_embedding)

        with patch("src.analysis.analyzer_subprocess._load_image_array", return_value=self._DUMMY_IMG_ARRAY):
            with patch.dict("sys.modules", {"deepface": mock_module}):
                result = analyze(img_path, "actor_a")

        serialized = json.dumps(result)
        embedding = json.loads(serialized)["face_embedding"]
        assert len(embedding) == _FACENET_DIM
        assert all(isinstance(v, float) for v in embedding)

    def test_is_occluded_true_when_max_score_below_threshold(self, tmp_path: Path) -> None:
        """最大感情スコアが 40 未満のとき isOccluded=True になること。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        mock_module, _ = self._make_mock_deepface(
            analyze_result=self._make_deepface_result(happy=30.0)
        )

        with patch("src.analysis.analyzer_subprocess._load_image_array", return_value=self._DUMMY_IMG_ARRAY):
            with patch.dict("sys.modules", {"deepface": mock_module}):
                result = analyze(img_path, "actor_a")

        assert result["isOccluded"] is True

    def test_uses_zero_for_missing_eye_coordinates(self, tmp_path: Path) -> None:
        """left_eye / right_eye が None のとき [0, 0] にフォールバックすること。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        mock_module, _ = self._make_mock_deepface(
            analyze_result=self._make_deepface_result(left_eye=None, right_eye=None)
        )

        with patch("src.analysis.analyzer_subprocess._load_image_array", return_value=self._DUMMY_IMG_ARRAY):
            with patch.dict("sys.modules", {"deepface": mock_module}):
                result = analyze(img_path, "actor_a")

        assert result["faceAngle"] == pytest.approx(0.0)

    def test_raises_exception_on_deepface_failure(self, tmp_path: Path) -> None:
        """DeepFace.analyze が例外を送出した場合、例外を再送出すること。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        mock_module = MagicMock()
        mock_module.DeepFace.analyze.side_effect = Exception("no face")

        with patch("src.analysis.analyzer_subprocess._load_image_array", return_value=self._DUMMY_IMG_ARRAY):
            with patch.dict("sys.modules", {"deepface": mock_module}):
                with pytest.raises(Exception, match="no face"):
                    analyze(img_path, "actor_a")

    def test_raises_exception_on_load_image_failure(self, tmp_path: Path) -> None:
        """_load_image_array が例外を送出した場合、例外を再送出すること。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        mock_module = MagicMock()
        with patch.dict("sys.modules", {"deepface": mock_module}):
            with patch(
                "src.analysis.analyzer_subprocess._load_image_array",
                side_effect=OSError("cannot open image"),
            ):
                with pytest.raises(OSError, match="cannot open image"):
                    analyze(img_path, "actor_a")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    """main のテスト。"""

    def _make_analyze_result(self) -> dict:
        """analyze の戻り値となる dict を生成する。"""
        return {
            "actor": "actor_a",
            "filename": "img.jpg",
            "angry": 5.0,
            "fear": 2.0,
            "happy": 80.0,
            "sad": 3.0,
            "surprise": 4.0,
            "disgust": 1.0,
            "neutral": 5.0,
            "faceAngle": 0.0,
            "isOccluded": False,
        }

    def test_exits_with_1_when_argument_count_is_wrong(self, capsys) -> None:
        """引数が不正な場合 exit code 1 で終了すること。"""
        with patch.object(sys, "argv", ["prog"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Usage:" in captured.err

    def test_prints_json_and_exits_with_0_on_success(self, tmp_path: Path, capsys) -> None:
        """解析成功時に JSON を stdout に出力して exit code 0 で終了すること。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()
        expected = self._make_analyze_result()

        with patch.object(sys, "argv", ["prog", str(img_path), "actor_a"]):
            with patch("src.analysis.analyzer_subprocess.analyze", return_value=expected) as mock_analyze:
                with pytest.raises(SystemExit) as exc_info:
                    main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out) == expected
        mock_analyze.assert_called_once_with(img_path, "actor_a")

    def test_prints_error_and_exits_with_1_on_failure(self, tmp_path: Path, capsys) -> None:
        """解析失敗時にエラーを stderr に出力して exit code 1 で終了すること。"""
        img_path = tmp_path / "img.jpg"
        img_path.touch()

        with patch.object(sys, "argv", ["prog", str(img_path), "actor_a"]):
            with patch(
                "src.analysis.analyzer_subprocess.analyze",
                side_effect=Exception("no face"),
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "ERROR: no face" in captured.err
