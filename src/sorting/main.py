"""torchとCLIPによる写真の振り分け・学習スクリプト。

SORTING_ROOT/all_photos/ の写真を、SORTING_ROOT/member_features.pt の
学習済み特徴量データベースを使って人物別に振り分ける。
学習モードでは SORTING_ROOT/master_photos/{actor}/ の写真から特徴量を構築・更新する。

Usage:
    python -m src.sorting.main           # 振り分けのみ
    python -m src.sorting.main --learn   # 学習のみ
"""

import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import torch
import clip
from PIL import Image
from dotenv import load_dotenv
from tqdm import tqdm


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

FEATURES_FILE = "member_features.pt"
TARGET_DIR = "all_photos"
OUTPUT_DIR = "sorted_results"
MASTER_DIR = "master_photos"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


# ---------------------------------------------------------------------------
# 環境変数
# ---------------------------------------------------------------------------


def _load_env() -> None:
    """プロジェクトルートの .env を読み込む。既存の環境変数は上書きしない。"""
    load_dotenv(override=False)


def _get_device() -> str:
    """使用デバイスを決定する（MPS優先、なければCPU）。

    Returns:
        デバイス文字列（"mps" または "cpu"）。
    """
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _load_model(device: str):
    """CLIPモデルをロードしてfloat32に統一する。

    Args:
        device: 使用デバイス文字列。

    Returns:
        (model, preprocess) のタプル。
    """
    model, preprocess = clip.load("ViT-L/14", device=device)
    model = model.float()
    return model, preprocess


# ---------------------------------------------------------------------------
# 特徴量リポジトリ
# ---------------------------------------------------------------------------


class FeatureRepository:
    """member_features.pt の読み書きと画像ファイル操作を担う。"""

    def loadFeatures(self, features_path: Path) -> dict:
        """member_features.pt から特徴量データベースを読み込む。

        Args:
            features_path: member_features.pt のパス。

        Returns:
            actor名 → Tensor の辞書。ファイルが存在しない場合は空辞書。
        """
        if not features_path.exists():
            return {}
        data = torch.load(str(features_path), map_location="cpu", weights_only=False)
        return {k: v.float() for k, v in data.items()}

    def saveFeatures(self, features_path: Path, features_db: dict) -> None:
        """特徴量データベースを member_features.pt に保存する。

        Args:
            features_path: member_features.pt のパス。
            features_db: actor名 → Tensor の辞書。
        """
        torch.save({k: v for k, v in features_db.items()}, str(features_path))

    def listMasterActors(self, master_dir: Path) -> list:
        """master_photos ディレクトリ配下の actor ディレクトリ名リストを返す。

        Args:
            master_dir: master_photos ディレクトリのパス。

        Returns:
            actor ディレクトリ名のリスト。ディレクトリが存在しない場合は空リスト。
        """
        if not master_dir.exists():
            return []
        return [d for d in os.listdir(str(master_dir)) if (master_dir / d).is_dir()]

    def listActorImages(self, actor_dir: Path) -> list:
        """actor ディレクトリ配下の画像ファイル名リストを返す。

        Args:
            actor_dir: actor ディレクトリのパス。

        Returns:
            画像ファイル名のリスト（拡張子でフィルタ済み）。
        """
        return [
            f for f in os.listdir(str(actor_dir))
            if f.lower().endswith(IMAGE_EXTENSIONS)
        ]

    def listTargetImages(self, target_dir: Path) -> list:
        """all_photos ディレクトリ配下の画像ファイル名リストを返す。

        Args:
            target_dir: all_photos ディレクトリのパス。

        Returns:
            画像ファイル名のリスト（拡張子でフィルタ済み）。
        """
        return [
            f for f in os.listdir(str(target_dir))
            if f.lower().endswith(IMAGE_EXTENSIONS)
        ]

    def moveImage(self, src: Path, dst_dir: Path, filename: str) -> None:
        """画像ファイルを振り分け結果ディレクトリに移動する。

        Args:
            src: 移動元のファイルパス。
            dst_dir: 移動先ディレクトリのパス。
            filename: ファイル名。
        """
        os.makedirs(str(dst_dir), exist_ok=True)
        shutil.move(str(src), str(dst_dir / filename))

    def deleteImage(self, path: Path) -> None:
        """画像ファイルを削除する。

        Args:
            path: 削除するファイルのパス。
        """
        os.remove(str(path))


# ---------------------------------------------------------------------------
# 特徴量抽出器
# ---------------------------------------------------------------------------


class FeatureExtractor:
    """CLIPモデルで画像の特徴量ベクトルを抽出する。"""

    def __init__(self, model, preprocess, device: str) -> None:
        """初期化。

        Args:
            model: CLIPモデル（encode_imageメソッドを持つ）。
            preprocess: 画像前処理関数。
            device: 使用デバイス文字列。
        """
        self._model = model
        self._preprocess = preprocess
        self._device = device

    def extract(self, image_path: Path):
        """画像から正規化済み特徴量ベクトルを抽出する。

        Args:
            image_path: 対象画像のパス。

        Returns:
            正規化済み特徴量 Tensor（shape: [1, D]）。
        """
        img = (
            self._preprocess(Image.open(str(image_path)))
            .unsqueeze(0)
            .to(self._device)
            .float()
        )
        with torch.no_grad():
            feat = self._model.encode_image(img)
            feat /= feat.norm(dim=-1, keepdim=True)
        return feat.cpu()


# ---------------------------------------------------------------------------
# 学習クラス
# ---------------------------------------------------------------------------


class Learner:
    """学習モード: master_photos の写真からメンバー特徴量を構築・更新する。"""

    def __init__(self, repository: FeatureRepository, extractor: FeatureExtractor) -> None:
        """初期化。

        Args:
            repository: FeatureRepository インスタンス。
            extractor: FeatureExtractor インスタンス。
        """
        self._repository = repository
        self._extractor = extractor

    def learn(self, master_dir: Path, features_path: Path, features_db: dict) -> dict:
        """master_photos の写真を学習し、特徴量データベースを更新・保存する。

        各 actor ディレクトリの画像から特徴量を抽出して既存 DB に追記し、
        学習済み画像を削除する。結果を features_path に保存する。

        Args:
            master_dir: master_photos ディレクトリのパス。
            features_path: member_features.pt のパス。
            features_db: 既存の特徴量データベース（更新のベースとして使用）。

        Returns:
            更新後の特徴量データベース。
        """
        actors = self._repository.listMasterActors(master_dir)
        if not actors:
            print("学習用データがありません。")
            return features_db

        # 既存 DB をコピーして更新する（元を変えない）
        updated_db = dict(features_db)

        for actor in tqdm(actors, desc="Learning Progress", unit="actor"):
            actor_dir = master_dir / actor
            img_files = self._repository.listActorImages(actor_dir)
            if not img_files:
                continue

            new_feats = []
            for filename in img_files:
                img_path = actor_dir / filename
                try:
                    feat = self._extractor.extract(img_path)
                    new_feats.append(feat)
                    self._repository.deleteImage(img_path)
                except Exception as e:
                    tqdm.write(f"学習エラー {filename}: {e}")

            if not new_feats:
                continue

            new_tensor = torch.cat(new_feats, dim=0)
            if actor in updated_db:
                updated_db[actor] = torch.cat([updated_db[actor], new_tensor], dim=0)
            else:
                updated_db[actor] = new_tensor

        self._repository.saveFeatures(features_path, updated_db)
        print("学習が完了しました！")
        return updated_db


# ---------------------------------------------------------------------------
# 振り分けクラス
# ---------------------------------------------------------------------------


class Classifier:
    """振り分けモード: all_photos の写真をsorted_resultsに振り分ける。"""

    def __init__(self, repository: FeatureRepository, extractor: FeatureExtractor) -> None:
        """初期化。

        Args:
            repository: FeatureRepository インスタンス。
            extractor: FeatureExtractor インスタンス。
        """
        self._repository = repository
        self._extractor = extractor

    def classify(self, target_dir: Path, output_dir: Path, features_db: dict, max_workers: int = 4) -> None:
        """all_photos の写真を人物別に振り分ける。

        Args:
            target_dir: all_photos ディレクトリのパス。
            output_dir: sorted_results ディレクトリのパス。
            features_db: 学習済み特徴量データベース。
            max_workers: 並列ワーカー数（デフォルト 4）。
        """
        if not features_db:
            print("学習データがありません。")
            return

        img_files = self._repository.listTargetImages(target_dir)
        if not img_files:
            print("画像が見つかりません。")
            return

        rep_feats = {
            actor: feat.mean(dim=0, keepdim=True).float()
            for actor, feat in features_db.items()
        }

        def _process_one(filename: str) -> None:
            img_path = target_dir / filename
            try:
                target_feat = self._extractor.extract(img_path)
                scores = {
                    actor: (target_feat @ f.T).item()
                    for actor, f in rep_feats.items()
                }
                best_match = max(scores, key=scores.get)
                self._repository.moveImage(img_path, output_dir / best_match, filename)
            except Exception as e:
                tqdm.write(f"振り分けエラー {filename}: {e}")

        print(f"{len(img_files)}枚の振り分けを開始します...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_one, f): f for f in img_files}
            for _ in tqdm(as_completed(futures), total=len(img_files), desc="Sorting Progress", unit="photo"):
                pass

        print("すべての振り分けが完了しました！")


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------


def learn(
    repository: Optional[FeatureRepository] = None,
    extractor: Optional[FeatureExtractor] = None,
    learner: Optional[Learner] = None,
    sorting_root: Optional[Path] = None,
) -> None:
    """学習のメイン処理。

    master_photos/ の写真から特徴量を抽出し、member_features.pt を更新する。

    Args:
        repository: FeatureRepository インスタンス（DI 用）。
        extractor: FeatureExtractor インスタンス（DI 用）。
        learner: Learner インスタンス（DI 用）。
        sorting_root: SORTING_ROOT パス（DI 用）。省略時は環境変数を使用。
    """
    _load_env()

    if sorting_root is None:
        sorting_root = Path(os.environ["SORTING_ROOT"])

    if extractor is None:
        device = _get_device()
        model, preprocess = _load_model(device)
        extractor = FeatureExtractor(model, preprocess, device)

    if repository is None:
        repository = FeatureRepository()

    if learner is None:
        learner = Learner(repository, extractor)

    features_path = sorting_root / FEATURES_FILE
    master_dir = sorting_root / MASTER_DIR

    features_db = repository.loadFeatures(features_path)
    learner.learn(master_dir, features_path, features_db)

    print("[INFO] Learning complete.")


def run(
    repository: Optional[FeatureRepository] = None,
    extractor: Optional[FeatureExtractor] = None,
    classifier: Optional[Classifier] = None,
    sorting_root: Optional[Path] = None,
    max_workers: int = 4,
) -> None:
    """振り分けのメイン処理。

    member_features.pt の学習済み特徴量データベースを読み込み、
    all_photos/ の写真を人物別に sorted_results/ へ振り分ける。

    Args:
        repository: FeatureRepository インスタンス（DI 用）。
        extractor: FeatureExtractor インスタンス（DI 用）。
        classifier: Classifier インスタンス（DI 用）。
        sorting_root: SORTING_ROOT パス（DI 用）。省略時は環境変数を使用。
        max_workers: 並列ワーカー数（デフォルト 4）。
    """
    _load_env()

    if sorting_root is None:
        sorting_root = Path(os.environ["SORTING_ROOT"])

    if extractor is None:
        device = _get_device()
        model, preprocess = _load_model(device)
        extractor = FeatureExtractor(model, preprocess, device)

    if repository is None:
        repository = FeatureRepository()

    if classifier is None:
        classifier = Classifier(repository, extractor)

    features_path = sorting_root / FEATURES_FILE
    target_dir = sorting_root / TARGET_DIR
    output_dir = sorting_root / OUTPUT_DIR

    features_db = repository.loadFeatures(features_path)
    classifier.classify(target_dir, output_dir, features_db, max_workers=max_workers)

    print("[INFO] Sorting complete.")


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="写真振り分けスクリプト")
    parser.add_argument("--learn", action="store_true", help="学習モードで実行する")
    parser.add_argument("--workers", type=int, default=4, help="並列ワーカー数（デフォルト: 4）")
    args = parser.parse_args()

    if args.learn:
        learn()
    else:
        run(max_workers=args.workers)
