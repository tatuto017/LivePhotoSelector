"""Scikit-learn による学習とスコアリングスクリプト。

sorting_state テーブルの選別結果 (ok/ng) を Scikit-learn に学習させ、
pending の写真データをスコアリングして DB を更新する。

Usage:
    python -m src.scoring.main
"""

import json
import os
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GridSearchCV
from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import Engine
from tqdm import tqdm

from src.analysis.main import AnalysisRecord
from src.db_schema import analysis_records, sorting_state


# ---------------------------------------------------------------------------
# 環境変数
# ---------------------------------------------------------------------------


def _load_env() -> None:
    """プロジェクトルートの .env を読み込む。既存の環境変数は上書きしない。"""
    load_dotenv(override=False)


def _create_engine() -> Engine:
    """環境変数から SQLAlchemy エンジンを生成する。

    Returns:
        SQLAlchemy Engine（PyMySQL ドライバー使用）。
    """
    host = os.environ["MYSQL_HOST"]
    port = os.environ.get("MYSQL_PORT", "3306")
    user = os.environ["MYSQL_USER"]
    password = os.environ["MYSQL_PASSWORD"]
    database = os.environ["MYSQL_DATABASE"]
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    return create_engine(url)


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
    """analysis_records テーブル / sorting_state テーブル / {actor}_model.joblib の読み書きを担う。"""

    def __init__(self, data_root: Path, engine: Engine) -> None:
        """初期化。

        Args:
            data_root: データルートディレクトリ（モデルファイルを含む）。
            engine: SQLAlchemy Engine。
        """
        self._model_dir = data_root
        self._engine = engine

    def loadRecords(self) -> list:
        """analysis_records テーブルから全解析レコードを読み込む。

        Returns:
            AnalysisRecord のリスト。レコードが存在しない場合は空リスト。
        """
        stmt = select(
            analysis_records.c.actor,
            analysis_records.c.filename,
            analysis_records.c.shooting_date,
            analysis_records.c.angry,
            analysis_records.c.fear,
            analysis_records.c.happy,
            analysis_records.c.sad,
            analysis_records.c.surprise,
            analysis_records.c.disgust,
            analysis_records.c.neutral,
            analysis_records.c.face_angle,
            analysis_records.c.is_occluded,
            analysis_records.c.face_embedding,
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [
            AnalysisRecord(
                actor=row.actor,
                filename=row.filename,
                shootingDate=str(row.shooting_date),
                angry=row.angry,
                fear=row.fear,
                happy=row.happy,
                sad=row.sad,
                surprise=row.surprise,
                disgust=row.disgust,
                neutral=row.neutral,
                faceAngle=row.face_angle,
                isOccluded=bool(row.is_occluded),
                face_embedding=json.loads(row.face_embedding)
                if isinstance(row.face_embedding, str)
                else row.face_embedding,
            )
            for row in rows
        ]

    def getActors(self) -> list:
        """sorting_state テーブルから被写体 ID 一覧を返す。

        Returns:
            被写体 ID のリスト（ソート済み）。
        """
        stmt = (
            select(sorting_state.c.actor_id)
            .distinct()
            .order_by(sorting_state.c.actor_id)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [row.actor_id for row in rows]

    def loadActorEntries(self, actor: str) -> list:
        """sorting_state テーブルから被写体の選別エントリを dict リストで返す。

        Args:
            actor: 被写体 ID。

        Returns:
            エントリの dict リスト。
        """
        stmt = (
            select(
                sorting_state.c.filename,
                sorting_state.c.shooting_date,
                sorting_state.c.score,
                sorting_state.c.selection_state,
                sorting_state.c.learned,
                sorting_state.c.selected_at,
            )
            .where(sorting_state.c.actor_id == actor)
            .order_by(sorting_state.c.score.desc().nulls_last())
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        result = []
        for row in rows:
            result.append({
                "filename": row.filename,
                "shootingDate": str(row.shooting_date),
                "score": float(row.score) if row.score is not None else None,
                "selectionState": row.selection_state,
                "learned": bool(row.learned),
                "selectedAt": str(row.selected_at) if row.selected_at is not None else None,
            })
        return result

    def updateScore(self, actor: str, filename: str, shootingDate: str, score: float) -> None:
        """sorting_state テーブルの score と learned を更新する。

        Args:
            actor: 被写体 ID。
            filename: ファイル名。
            shootingDate: 撮影日 (YYYY-MM-DD)。
            score: 更新後のスコア（0.0〜1.0）。
        """
        stmt = (
            update(sorting_state)
            .where(
                sorting_state.c.actor_id == actor,
                sorting_state.c.filename == filename,
                sorting_state.c.shooting_date == shootingDate,
            )
            .values(score=score, learned=True)
        )
        with self._engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()

    def markLearned(self, actor: str, filename: str, shootingDate: str) -> None:
        """sorting_state テーブルの learned を true に更新する。

        学習に使用した ok/ng レコードを学習済みとしてマークする。

        Args:
            actor: 被写体 ID。
            filename: ファイル名。
            shootingDate: 撮影日 (YYYY-MM-DD)。
        """
        stmt = (
            update(sorting_state)
            .where(
                sorting_state.c.actor_id == actor,
                sorting_state.c.filename == filename,
                sorting_state.c.shooting_date == shootingDate,
            )
            .values(learned=True)
        )
        with self._engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()

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
    data_root: Optional[Path] = None,
    engine: Optional[Engine] = None,
) -> None:
    """スコアリングのメイン処理。

    全被写体に対して学習・スコアリングを実行し、sorting_state テーブルを更新する。

    Args:
        repository: ScoringRepository インスタンス（DI 用）。
        trainer: ModelTrainer インスタンス（DI 用）。
        scorer: PhotoScorer インスタンス（DI 用）。
        data_root: データルートパス（DI 用）。省略時は DATA_ROOT 環境変数を使用。
        engine: SQLAlchemy Engine（DI 用）。
    """
    _load_env()

    if data_root is None:
        data_root = Path(os.environ["DATA_ROOT"])
    if engine is None:
        engine = _create_engine()
    if repository is None:
        repository = ScoringRepository(data_root, engine)
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

    1. DB からエントリ取得 → labeled/pending 分割
    2. ランダムフォレストで学習（labeled データ使用）
    3. pending データをスコアリング
    4. pending エントリのスコアを DB に更新

    Args:
        actor: 被写体 ID。
        repository: ScoringRepository インスタンス。
        trainer: ModelTrainer インスタンス。
        scorer: PhotoScorer インスタンス。
        record_map: (actor, filename) → AnalysisRecord のマップ。
    """
    # 1. エントリ取得（未学習の ok/ng レコードのみ学習対象とする）
    entries = repository.loadActorEntries(actor)
    labeled = [
        e for e in entries
        if e.get("selectionState") in ("ok", "ng") and not e.get("learned")
    ]
    pending = [e for e in entries if e.get("selectionState") == "pending"]

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

        # 学習に使用した ok/ng レコードを学習済みとしてマークする
        for entry in labeled:
            repository.markLearned(actor, entry["filename"], entry["shootingDate"])

        # 学習結果を被写体別で表示する
        X_train = np.array(train_features)
        y_train = np.array(train_labels)
        accuracy = float(model.score(X_train, y_train))
        n_ok = int(np.sum(y_train == 1))
        n_ng = int(np.sum(y_train == 0))
        _display_training_result(actor, n_ok, n_ng, accuracy)

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

    # 4. pending エントリのスコアを DB に更新
    pending_map = {e["filename"]: e for e in pending}
    for filename, score in score_map.items():
        entry = pending_map.get(filename)
        if entry is not None:
            repository.updateScore(actor, filename, entry["shootingDate"], score)


def _display_training_result(
    actor: str, n_ok: int, n_ng: int, accuracy: float
) -> None:
    """学習結果を標準出力に表示する。

    Args:
        actor: 被写体 ID。
        n_ok: 学習データ中の ok サンプル数。
        n_ng: 学習データ中の ng サンプル数。
        accuracy: 学習データに対する分類精度（0.0〜1.0）。
    """
    print(
        f"[RESULT] {actor}: "
        f"ok={n_ok}, ng={n_ng}, "
        f"train_accuracy={accuracy:.4f}"
    )


if __name__ == "__main__":  # pragma: no cover
    run()
