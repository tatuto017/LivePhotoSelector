"""単一画像の DeepFace 解析を行うサブプロセスモジュール。

PhotoAnalyzer.analyze() からサブプロセスとして呼び出される。
TF/DeepFace のモデルをロードして 1 枚の画像を解析し、結果を JSON で stdout に出力する。
プロセス終了時にメモリが完全に解放されるため、OOM Kill による無限ループを防ぐ。

メモリ削減のため以下の対策を実施している:
- TF スレッド数を 1 に制限（DeepFace インポート前に環境変数で設定）
- 画像を _MAX_IMAGE_SIZE px 以内にリサイズして numpy 配列で DeepFace に渡す

Usage:
    python -m src.analysis.analyzer_subprocess <img_path> <actor>

Exit codes:
    0: 解析成功（stdout に JSON 出力）
    1: 解析失敗（stderr にエラーメッセージ出力）
"""

import json
import math
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image as PILImage

# TF スレッド数を 1 に制限してメモリ使用量を削減する。
# DeepFace（TF）をインポートする前に設定しなければ効果がないため、モジュールレベルで記述する。
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

# 画像の長辺上限（ピクセル）。大きな画像はこのサイズにリサイズして処理する。
_MAX_IMAGE_SIZE = 1920


def _calculate_face_angle(left_eye: list, right_eye: list) -> float:
    """両目の座標からロール角（度数）を計算する。

    Args:
        left_eye: 左目の座標 [x, y]。
        right_eye: 右目の座標 [x, y]。

    Returns:
        ロール角（度数）。
    """
    dx = right_eye[0] - left_eye[0]
    dy = right_eye[1] - left_eye[1]
    return math.degrees(math.atan2(dy, dx))


def _load_image_array(img_path: Path) -> np.ndarray:
    """画像を読み込み、長辺が _MAX_IMAGE_SIZE 以内になるようリサイズして numpy 配列で返す。

    大きな画像をそのまま DeepFace に渡すと多量のメモリを消費するため、
    事前にリサイズして DeepFace の入力メモリを抑制する。

    Args:
        img_path: 画像ファイルのパス。

    Returns:
        RGB numpy 配列 (H, W, 3)。
    """
    pil_img = PILImage.open(img_path).convert("RGB")
    pil_img.thumbnail((_MAX_IMAGE_SIZE, _MAX_IMAGE_SIZE), PILImage.LANCZOS)
    return np.array(pil_img)


def analyze(img_path: Path, actor: str) -> dict:
    """DeepFace で画像を解析して結果 dict を返す。

    Args:
        img_path: 解析する画像ファイルのパス。
        actor: 被写体 ID。

    Returns:
        解析結果 dict（JSON シリアライズ可能）。face_embedding を含む。

    Raises:
        Exception: 解析に失敗した場合。
    """
    from deepface import DeepFace  # noqa: PLC0415

    # リサイズ済みの numpy 配列を渡してメモリ使用量を削減する
    img_array = _load_image_array(img_path)

    # 感情解析
    analysis_results = DeepFace.analyze(
        img_path=img_array,
        actions=["emotion"],
        enforce_detection=False,
    )
    result = analysis_results[0]
    emotion: dict = result["emotion"]
    region: dict = result["region"]

    # Facenet による顔特徴量ベクトル（128 次元）
    represent_results = DeepFace.represent(
        img_path=img_array,
        model_name="Facenet",
        enforce_detection=False,
    )
    face_embedding: list = [float(v) for v in represent_results[0]["embedding"]]

    left_eye: list = region.get("left_eye") or [0, 0]
    right_eye: list = region.get("right_eye") or [0, 0]
    face_angle = _calculate_face_angle(left_eye, right_eye)

    max_emotion_score = max(emotion.values()) / 100.0
    is_occluded = bool(max_emotion_score < 0.4)

    return {
        "actor": actor,
        "filename": img_path.name,
        "angry": float(emotion.get("angry", 0.0)),
        "fear": float(emotion.get("fear", 0.0)),
        "happy": float(emotion.get("happy", 0.0)),
        "sad": float(emotion.get("sad", 0.0)),
        "surprise": float(emotion.get("surprise", 0.0)),
        "disgust": float(emotion.get("disgust", 0.0)),
        "neutral": float(emotion.get("neutral", 0.0)),
        "faceAngle": face_angle,
        "isOccluded": is_occluded,
        "face_embedding": face_embedding,
    }


def main() -> None:
    """コマンドライン引数から画像パスと被写体 ID を受け取り解析を実行する。"""
    if len(sys.argv) != 3:
        print("Usage: python -m src.analysis.analyzer_subprocess <img_path> <actor>", file=sys.stderr)
        sys.exit(1)

    img_path = Path(sys.argv[1])
    actor = sys.argv[2]

    try:
        result = analyze(img_path, actor)
        print(json.dumps(result))
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
