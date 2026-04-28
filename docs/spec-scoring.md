# Scikit-learnによる、スコアリング機能

## 処理概要

`sorting_state` テーブルの選択結果（ok/ng）を Scikit-learn に学習させ、`pending` の写真データをスコアリングして `score` を更新する。
被写体ごとに独立して学習・スコアリングを行う。

## 処理フロー

1. `sorting_state` から被写体 ID 一覧を取得する
2. 被写体ごとに以下を実行する（`tqdm` で進捗表示）
   1. `sorting_state` から被写体の全エントリを取得し、以下に分割する
      - **labeled**: `selection_state` が `ok` または `ng`、かつ `learned = false`
      - **pending**: `selection_state` が `pending`
   2. labeled エントリの `(actor, filename)` をキーに `analysis_records` から対応レコードを取得して特徴量に変換する
   3. **labeled エントリがある場合のみ**学習を実行する
      - ランダムフォレスト + GridSearchCV でハイパーパラメータチューニング
      - 学習済みモデルを `DATA_ROOT/{actor}_model.joblib` に保存する
      - labeled エントリの `learned` を `true` に更新する
      - labeled エントリの更新内容を `sorting_state` に反映する。
      - 学習結果（サンプル数・訓練精度）を標準出力に表示する
   4. pending エントリをスコアリングして `score` を更新する
      - pending エントリの更新内容を `sorting_state` に反映する。

## 特徴量

137 次元の特徴量ベクトルを使用する。

| 次元 | 内容 |
| --- | --- |
| 7 次元 | 感情スコア（angry, fear, happy, sad, surprise, disgust, neutral） |
| 1 次元 | 顔のロール角（face_angle） |
| 1 次元 | 遮蔽物フラグ（is_occluded: 1.0 / 0.0） |
| 128 次元 | Facenet 埋め込みベクトル（face_embedding） |

## 学習アルゴリズム

`RandomForestClassifier` + `GridSearchCV` によるハイパーパラメータ最適化。

**ハイパーパラメータ探索範囲:**

| パラメータ | 候補値 |
| --- | --- |
| `n_estimators` | 50, 100, 200 |
| `max_depth` | None, 5, 10 |
| `min_samples_split` | 2, 5 |

**CV 分割数:** `min(3, n_ok, n_ng)` で決定。2 未満になる場合（サンプル不足）は GridSearchCV を使わず直接学習する。

**学習条件:** ok・ng の両クラスが揃っていない場合は学習・スコアリングをスキップする。

## スコアの計算

`model.predict_proba()` から ok クラスの確率を取得し、小数点 4 桁に丸める。

```python
score = round(predict_proba[ok_index], 4)  # 0.0〜1.0
```

## DB の更新タイミング

| 操作 | タイミング | 対象レコード |
| --- | --- | --- |
| `learned = true` | 学習完了後 | 学習に使用した ok/ng レコード |
| `score` 更新 | スコアリング完了後 | pending レコード（モデルが存在する場合のみ） |

## モデルの保存先

```
DATA_ROOT/{actor}_model.joblib
```
