# torchによる、写真の振り分け機能

## 処理概要
CLIP（ViT-L/14）で抽出した特徴量を使用して、写真を人物別に振り分ける。
学習モードと振り分けモードを実装する。

## 学習モード
1. `学習用写真ディレクトリ` に入っている写真から CLIP で特徴量を抽出する。
2. 学習結果を `member_features.pt` に保存する。
3. 学習したファイルを削除する。

## 振り分けモード
1. `振り分け対象写真のディレクトリ` の写真を読み込む。
2. CLIP で各写真の特徴量ベクトルを抽出する。
3. `member_features.pt` の人物別代表特徴量とコサイン類似度を比較し、最も類似度が高い人物に判定する。
4. `振り分け結果ディレクトリ` に写真を移動する。
5. デフォルト4並列（`ThreadPoolExecutor`）で処理する。

## デバイス
- **特徴量抽出**: MPS（Apple GPU）が利用可能な場合は MPS を使用、なければ CPU。
- **特徴量データベース**: CPU に統一して保持（`map_location="cpu"`）。
- **行列演算**: 全テンソルを CPU に揃えてコサイン類似度を計算する。

## 使用方法

```bash
# 振り分けのみ（デフォルト 4 並列）
python -m src.sorting.main

# 振り分けのみ（並列数を指定）
python -m src.sorting.main --workers 8

# 学習のみ
python -m src.sorting.main --learn
```

## クラス構成

| クラス | 役割 |
| --- | --- |
| `FeatureRepository` | `member_features.pt` の読み書き・画像ファイル操作 |
| `FeatureExtractor` | CLIP モデルで画像の特徴量ベクトルを抽出（正規化済み） |
| `Learner` | 学習モード: `master_photos/` から特徴量を構築・更新 |
| `Classifier` | 振り分けモード: `all_photos/` を `sorted_results/` に並列振り分け |

## ドキュメント
- [spec-directory.md](spec-directory.md) — 振り分け用ディレクトリ構成
