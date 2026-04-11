"""Scikit-learn による学習とスコアリングスクリプト。

{actor}_analysis.json の選別結果 (ok/ng) を Scikit-learn に学習させ、
pending の写真データをスコアリングして更新する。

Usage:
    python -m src.scoring.main
"""

import json
import os
import pickle
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GridSearchCV
from tqdm import tqdm

# analysis.pki デシリアライズのため AnalysisRecord をインポート
from src.analysis.main import AnalysisRecord  # noqa: F401


# ---------------------------------------------------------------------------
# 環境変数
# ---------------------------------------------------------------------------


def _load_env() -> None:
    """プロジェクトルートの .env を読み込む。既存の環境変数は上書きしない。"""
    load_dotenv(override=False)


# ---------------------------------------------------------------------------
# 特徴量抽出
# ---------------------------------------------------------------------------


def _extract_features(record: AnalysisRecord) -> list:
    """AnalysisRecord から特徴量ベクトルを生成する。

    感情スコア 7 次元 + 顔角度 1 次元 + 遮蔽物フラグ 1 次元 + Facenet 埋め込み 128 次元の計 137 次元。

    Args:
        record: 解析レコード。

    Returns:
        特徴量のフラットなリスト。
    """
    return [
        record.angry,
        record.fear,
        record.happy,
        record.sad,
        record.surprise,
        record.disgust,
        record.neutral,
        record.faceAngle,
        1.0 if record.isOccluded else 0.0,
    ] + [float(v) for v in record.face_embedding]


# ---------------------------------------------------------------------------
# スコアリングリポジトリ
# ---------------------------------------------------------------------------


class ScoringRepository:
    """analysis.pki / {actor}_analysis.json / {actor}_model.joblib の読み書きを担う。"""

    def __init__(self, project_root: Path, one_drive_root: Path) -> None:
        """初期化。

        Args:
            project_root: プロジェクトルートディレクトリ。
            one_drive_root: OneDrive ルートディレクトリ。
        """
        self._pki_path = one_drive_root / "data" / "analysis.pki"
        self._model_dir = one_drive_root / "data"
        self._data_dir = one_drive_root / "data"

    def loadRecords(self) -> list:
        """analysis.pki から解析レコードを読み込む。

        Returns:
            AnalysisRecord のリスト。ファイルが存在しない場合は空リスト。
        """
        if not self._pki_path.exists():
            return []
        with open(self._pki_path, "rb") as f:
            return pickle.load(f)

    def getActors(self) -> list:
        """OneDrive data ディレクトリ内の被写体 ID 一覧を返す。

        {actor}_analysis.json ファイル名から被写体 ID を取得する。

        Returns:
            被写体 ID のリスト（ソート済み）。ディレクトリが存在しない場合は空リスト。
        """
        if not self._data_dir.exists():
            return []
        actors = []
        for p in sorted(self._data_dir.glob("*_analysis.json")):
            actor = p.stem.replace("_analysis", "")
            actors.append(actor)
        return actors

    def loadActorEntries(self, actor: str) -> list:
        """{actor}_analysis.json から選別エントリを raw dict として読み込む。

        Args:
            actor: 被写体 ID。

        Returns:
            エントリの dict リスト。ファイルが存在しない場合は空リスト。
        """
        path = self._data_dir / f"{actor}_analysis.json"
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def saveActorEntries(self, actor: str, entries: list) -> None:
        """{actor}_analysis.json に選別エントリを保存する。

        Args:
            actor: 被写体 ID。
            entries: エントリの dict リスト。
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        path = self._data_dir / f"{actor}_analysis.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    def saveModel(self, actor: str, model) -> None:
        """学習済みモデルを {actor}_model.joblib に保存する。

        Args:
            actor: 被写体 ID。
            model: 学習済み Scikit-learn モデル。
        """
        self._model_dir.mkdir(parents=True, exist_ok=True)
        path = self._model_dir / f"{actor}_model.joblib"
        joblib.dump(model, path)


# ---------------------------------------------------------------------------
# モデルトレーナー
# ---------------------------------------------------------------------------


class ModelTrainer:
    """RandomForest + ハイパーパラメータチューニングで学習する。"""

    def train(self, features: list, labels: list):
        """RandomForestClassifier を GridSearchCV でハイパーパラメータ最適化して学習する。

        各クラスのサンプル数が少なく CV が実施できない場合は直接学習する。

        Args:
            features: 特徴量ベクトルのリスト。
            labels: ラベルリスト（1=ok, 0=ng）。

        Returns:
            学習済み RandomForestClassifier。
        """
        X = np.array(features)
        y = np.array(labels)
        rf = RandomForestClassifier(random_state=42)

        # 各クラスのサンプル数に応じて CV 分割数を決定
        n_ok = int(np.sum(y == 1))
        n_ng = int(np.sum(y == 0))
        cv_folds = min(3, n_ok, n_ng)

        if cv_folds < 2:
            # サンプル不足で CV できない場合は直接学習
            rf.fit(X, y)
            return rf

        param_grid = {
            "n_estimators": [50, 100, 200],
            "max_depth": [None, 5, 10],
            "min_samples_split": [2, 5],
        }
        grid_search = GridSearchCV(
            rf,
            param_grid,
            cv=cv_folds,
            scoring="accuracy",
            n_jobs=-1,
        )
        grid_search.fit(X, y)
        return grid_search.best_estimator_


# ---------------------------------------------------------------------------
# フォトスコアラー
# ---------------------------------------------------------------------------


class PhotoScorer:
    """学習済みモデルで写真をスコアリングする。"""

    def score(self, model, features: list) -> list:
        """特徴量リストから ok 確率スコアを計算する。

        Args:
            model: 学習済みモデル（predict_proba をサポートするもの）。
            features: 特徴量ベクトルのリスト。

        Returns:
            スコア（ok 確率、0.0〜1.0）のリスト。ok クラスが存在しない場合は 0.0 のリスト。
        """
        classes = list(model.classes_)
        if 1 not in classes:
            return [0.0] * len(features)
        X = np.array(features)
        probas = model.predict_proba(X)
        ok_idx = classes.index(1)
        return [round(float(p[ok_idx]), 4) for p in probas]


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------


def run(
    repository: Optional[ScoringRepository] = None,
    trainer: Optional[ModelTrainer] = None,
    scorer: Optional[PhotoScorer] = None,
    project_root: Optional[Path] = None,
    one_drive_root: Optional[Path] = None,
) -> None:
    """スコアリングのメイン処理。

    全被写体に対して学習・スコアリングを実行し、{actor}_analysis.json を更新する。

    Args:
        repository: ScoringRepository インスタンス（DI 用）。
        trainer: ModelTrainer インスタンス（DI 用）。
        scorer: PhotoScorer インスタンス（DI 用）。
        project_root: プロジェクトルートパス（DI 用）。
        one_drive_root: OneDrive ルートパス（DI 用）。
    """
    _load_env()

    if project_root is None:
        project_root = Path(os.environ["PROJECT_ROOT"])
    if one_drive_root is None:
        one_drive_root = Path(os.environ["ONE_DRIVE_ROOT"])
    if repository is None:
        repository = ScoringRepository(project_root, one_drive_root)
    if trainer is None:
        trainer = ModelTrainer()
    if scorer is None:
        scorer = PhotoScorer()

    records = repository.loadRecords()
    # (actor, filename) → AnalysisRecord のマップ
    record_map = {(r.actor, r.filename): r for r in records}

    actors = repository.getActors()

    for actor in tqdm(actors, desc="Scoring", unit="actor"):
        print(f"[INFO] Scoring actor: {actor}")
        _run_scoring_for_actor(
            actor, repository, trainer, scorer, record_map
        )

    print("[INFO] Scoring complete.")


def _run_scoring_for_actor(
    actor: str,
    repository: ScoringRepository,
    trainer: ModelTrainer,
    scorer: PhotoScorer,
    record_map: dict,
) -> None:
    """被写体ごとのスコアリング処理。

    1. スナップショット取得 → labeled/pending 分割
    2. ランダムフォレストで学習（labeled データ使用）
    3. pending データをスコアリング
    4. {actor}_analysis.json を再読み込みしてスコアのみマージ（Pi 差分対応）

    Args:
        actor: 被写体 ID。
        repository: ScoringRepository インスタンス。
        trainer: ModelTrainer インスタンス。
        scorer: PhotoScorer インスタンス。
        record_map: (actor, filename) → AnalysisRecord のマップ。
    """
    # 1. スナップショット取得
    snapshot = repository.loadActorEntries(actor)
    labeled = [e for e in snapshot if e.get("selectionState") in ("ok", "ng")]
    pending = [e for e in snapshot if e.get("selectionState") == "pending"]

    # 2. 学習
    model = None
    train_features = []
    train_labels = []
    for entry in labeled:
        record = record_map.get((actor, entry["filename"]))
        if record is None:
            continue
        train_features.append(_extract_features(record))
        train_labels.append(1 if entry["selectionState"] == "ok" else 0)

    has_both_classes = len(set(train_labels)) >= 2
    if train_features and has_both_classes:
        model = trainer.train(train_features, train_labels)
        repository.saveModel(actor, model)
        print(f"[INFO] Model saved for actor: {actor}")

    # 3. スコアリング
    score_map: dict = {}
    if model is not None:
        score_features = []
        score_filenames = []
        for entry in pending:
            record = record_map.get((actor, entry["filename"]))
            if record is None:
                continue
            score_features.append(_extract_features(record))
            score_filenames.append(entry["filename"])

        if score_features:
            scores = scorer.score(model, score_features)
            score_map = dict(zip(score_filenames, scores))

    # 4. 安全なマージ: current を再読み込みして pending の score のみ更新
    #    Pi が書き込んだ可能性があるため snapshot ではなく current を再読み込みする
    current = repository.loadActorEntries(actor)
    for entry in current:
        if entry["filename"] in score_map:
            entry["score"] = score_map[entry["filename"]]

    repository.saveActorEntries(actor, current)


if __name__ == "__main__":  # pragma: no cover
    run()
