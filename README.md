# Live Photo Selector

ライブ撮影写真の「感情分析」「顔の向き」「遮蔽物」を DeepFace で解析し、Scikit-learn でスコアリングして iPhone から高速に選別するための Web アプリ。

## 技術スタック

| レイヤー | 技術 |
|---|---|
| フロントエンド | Next.js 15 (App Router), TypeScript, Tailwind CSS, framer-motion |
| バックエンド | Next.js API Routes（ローカル FS 直接読み書き） |
| 解析スクリプト | Python 3.13, DeepFace, Facenet, opencv-python-headless, Pillow, tf-keras, tqdm |
| スコアリングスクリプト | Python 3.13, Scikit-learn, pandas, tqdm |
| データ整理スクリプト | Python 3.13 |
| ホスティング | Raspberry Pi 4 + Cloudflare Tunnel |
| ストレージ | OneDrive（Mac・Pi 双方にローカルマウント） |

## セットアップ

### フロントエンド（Raspberry Pi）

```bash
npm install
cp .env.example .env
# .env に環境変数を設定
npm run dev
```

### Python スクリプト（Mac）

#### 1. Python 3.13 のインストール

Homebrew でインストールする。

```bash
brew install python@3.13
```

#### 2. 仮想環境のセットアップ

`python3` コマンドは macOS システムの古い Python を指す場合があるため、Homebrew のフルパスで仮想環境を作成する。

```bash
/opt/homebrew/bin/python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

#### 3. 環境変数の設定

```bash
cp .env.example .env
# .env を編集して各パスを設定
```

#### 4. 初回実行時の注意

初回実行時に DeepFace が感情モデル・Facenet モデルをダウンロードする（合計 約 100MB）。
ダウンロード先は `~/.deepface/weights/`。

### 環境変数

`.env` に以下を設定する。

| 変数名 | 説明 |
|---|---|
| `PROJECT_ROOT` | プロジェクトのベースディレクトリ |
| `ONE_DRIVE_ROOT` | OneDrive のベースディレクトリ |

```bash
PROJECT_ROOT=/path/to/LivePhotoSelector
ONE_DRIVE_ROOT=/path/to/OneDrive/LivePhotoSelector
```

## 操作ワークフロー

```
1. 写真を OneDrive の inbox/{actor}/ に配置

2. Mac で解析（inbox → images 移動 + analysis.pki / {actor}_analysis.json 更新）
   bash analyze.sh
   ※ OOM Kill 時は自動再起動。inbox が空になるまでループする

3. iPhone で Pi にアクセスして OK/NG 選別
   右スワイプ = OK  /  左スワイプ = NG

4. スコアリング（Scikit-learn で学習・スコア付与）
   python -m src.scoring.main

5. 写真整理（OK → confirmed/ 移動、NG → 削除、ok/ng エントリを analysis.json へ移動）
   python -m src.finalize.main
```

## 実行コマンド

### フロントエンド

```bash
npm run dev       # 開発サーバー起動
npm run build     # 本番ビルド
npm start         # 本番起動
```

### 解析スクリプト

```bash
# 仮想環境を有効化してから実行する
source .venv/bin/activate

# 解析（INBOX の写真を DeepFace で解析して IMAGES へ移動）
# OOM Kill 時の自動再起動ループ込み
bash analyze.sh

# スコアリング（Scikit-learn で学習・スコア更新）
python -m src.scoring.main

# 写真整理（OK → confirmed/、NG → 削除、ok/ng エントリを analysis.json へ移動）
python -m src.finalize.main
```

## テスト

```bash
# フロントエンド（カバレッジ 100% 目標）
npm test -- --coverage

# 解析スクリプト（カバレッジ 100% 目標）
python -m pytest src/analysis/tests/ --cov=src/analysis --cov-report=term-missing

# スコアリングスクリプト（カバレッジ 100% 目標）
python -m pytest src/scoring/tests/ --cov=src/scoring --cov-report=term-missing

# データ整理スクリプト（カバレッジ 100% 目標）
python -m pytest src/finalize/tests/ --cov=src/finalize --cov-report=term-missing
```

## ディレクトリ構成

```text
{PROJECT_ROOT}/
├── src/
│   ├── analysis/              # Python 解析スクリプト (DeepFace)
│   │   ├── main.py
│   │   └── tests/
│   ├── scoring/               # Python スコアリングスクリプト (Scikit-learn)
│   │   ├── main.py
│   │   └── tests/
│   ├── finalize/              # Python データ整理スクリプト
│   │   ├── main.py
│   │   └── tests/
│   └── mocks/                 # Vitest 用 MSW モックサーバー
│       ├── handlers.ts
│       └── server.ts
├── app/                       # Next.js App Router
│   ├── page.tsx               # 被写体一覧（Server Component）
│   ├── actors/[actor]/
│   │   └── page.tsx           # 写真選別（Server Component）
│   └── api/
│       └── actors/
│           ├── route.ts                      # GET /api/actors
│           └── [actor]/
│               ├── photos/[filename]/route.ts  # PATCH 選別状態
│               └── images/[filename]/route.ts  # GET 画像配信
├── components/
│   ├── PhotoCard.tsx          # 写真カード（スワイプ UI）
│   └── PhotoSelectionClient.tsx  # 写真選別クライアント
├── hooks/
│   ├── usePinchZoom.ts        # ピンチズーム・パンフック
│   └── usePhotoSelection.ts   # 選別状態管理フック
├── lib/
│   ├── types.ts               # 共通型定義
│   └── repositories/
│       ├── LocalAnalysisRepository.ts  # FS 読み書きリポジトリ
│       └── ResultRepository.ts         # HTTP 保存リポジトリ
├── docs/                      # 仕様・設計ドキュメント
├── analyze.sh                 # 解析自動再起動スクリプト
└── requirements.txt           # Python 依存パッケージ
```

OneDrive 共有ディレクトリ（Mac ↔ Pi 共有）:

```text
{ONE_DRIVE_ROOT}/
├── data/
│   ├── analysis.pki           # DeepFace 解析データ
│   ├── {actor}_analysis.json  # 被写体別選別データ
│   └── {actor}_model.joblib   # 被写体別学習済みモデル
├── inbox/                     # 解析前の写真置き場
├── images/                    # 解析済み写真
└── confirmed/                 # OK 確定写真
```

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [docs/spec-base.md](docs/spec-base.md) | 機能要件・UI/UX 仕様 |
| [docs/workflow.md](docs/workflow.md) | データフロー・操作ワークフロー |
| [docs/spec-data-format.md](docs/spec-data-format.md) | JSON / PKL データ形式 |
| [docs/spec-directory.md](docs/spec-directory.md) | ディレクトリ構成 |
| [docs/architecture.md](docs/architecture.md) | 設計上の決定事項 |
| [docs/spec-analysis.md](docs/spec-analysis.md) | DeepFace 解析仕様 |
| [docs/spec-scoring.md](docs/spec-scoring.md) | Scikit-learn スコアリング仕様 |
| [docs/spec-finalize.md](docs/spec-finalize.md) | データ整理仕様 |
