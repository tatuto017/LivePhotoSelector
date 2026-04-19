# Live Photo Selector

ライブ撮影写真の「感情分析」「顔の向き」「遮蔽物」を DeepFace で解析し、Scikit-learn でスコアリングして iPhone から高速に選別するための Web アプリ。

## 技術スタック

| レイヤー | 技術 |
|---|---|
| フロントエンド | Next.js 15 (App Router), TypeScript, Tailwind CSS, framer-motion |
| バックエンド | Next.js API Routes, Drizzle ORM（MariaDB） |
| 解析スクリプト | Python 3.13, DeepFace, Facenet, opencv-python-headless, Pillow, tf-keras, SQLAlchemy, tqdm |
| スコアリングスクリプト | Python 3.13, Scikit-learn, pandas, SQLAlchemy, tqdm |
| データ整理スクリプト | Python 3.13, SQLAlchemy |
| ホスティング | Raspberry Pi 4 + Cloudflare Tunnel |
| データベース | MySQL（Raspberry Pi 上で稼働） |
| ストレージ | Mac から Pi の `data/` ディレクトリに直接マウント |

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
| `MYSQL_HOST` | MySQL ホスト名 |
| `MYSQL_PORT` | MySQL ポート番号 |
| `MYSQL_USER` | MySQL ユーザー名 |
| `MYSQL_PASSWORD` | MySQL パスワード |
| `MYSQL_DATABASE` | MySQL データベース名 |

```bash
PROJECT_ROOT=/path/to/LivePhotoSelector
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=livephoto
MYSQL_PASSWORD=secret
MYSQL_DATABASE=livephoto
```

## 操作ワークフロー

```
1. 写真を data/inbox/{actor}/ に配置

2. Mac で解析（inbox → images へ移動 + MySQL に登録）
   bash analyze.sh
   ※ OOM Kill 時は自動再起動。file_list.txt が空になるまでループする
   ※ 1 枚処理するたびに file_list.txt からエントリを削除（再起動時の続きから再開対応）
   ※ MySQL に INSERT されるため Pi 側から即時参照可能

3. iPhone で Pi にアクセスして OK/NG 選別
   右スワイプ = OK  /  左スワイプ = NG
   選別結果は MySQL の sorting_state テーブルに即時書き込まれる

4. スコアリング（Scikit-learn で学習・スコア付与）
   python -m src.scoring.main

5. 写真整理（OK → confirmed/ 移動、NG → 削除）
   python -m src.finalize.main
```

## Raspberry Pi へのデプロイ

```bash
rsync -avz --delete \
  --exclude='.claude' \
  --exclude='.coverage' \
  --exclude='.env' \
  --exclude='.git' \
  --exclude='.gitignore' \
  --exclude='.next' \
  --exclude='.pytest_cache' \
  --exclude='.venv' \
  --exclude='.venv_docker' \
  --exclude='.vscode' \
  --exclude='.claudeignore' \
  --exclude='CLAUDE.md' \
  --exclude='README.md' \
  --exclude='analyze.sh' \
  --exclude='src' \
  --exclude='coverage' \
  --exclude='data' \
  --exclude='docs' \
  --exclude='migrations' \
  --exclude='node_modules' \
  --exclude='package-lock.json' \
  --exclude='vitest.config.ts' \
  --exclude='vitest.setup.ts' \
  /path/to/LivePhotoSelector/ pi@<PiのIPアドレス>:/path/to/LivePhotoSelector/
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
# 解析（data/inbox の写真を DeepFace で解析して MariaDB に登録）
# OOM Kill 時の自動再起動ループ込み
bash analyze.sh

# スコアリング（Scikit-learn で学習・スコア更新）
python -m src.scoring.main

# 写真整理（OK → confirmed/、NG → 削除）
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
│           ├── route.ts                          # GET /api/actors
│           └── [actor]/
│               ├── photos/route.ts               # GET 写真一覧
│               ├── photos/[filename]/route.ts    # PATCH 選別状態
│               └── images/[filename]/route.ts    # GET 画像配信
├── components/
│   ├── PhotoCard.tsx          # 写真カード（スワイプ UI）
│   └── PhotoSelectionClient.tsx  # 写真選別クライアント
├── hooks/
│   ├── usePinchZoom.ts        # ピンチズーム・パンフック
│   └── usePhotoSelection.ts   # 選別状態管理フック
├── lib/
│   ├── types.ts               # 共通型定義
│   ├── db.ts                  # Drizzle ORM / MariaDB 接続管理
│   ├── schema.ts              # Drizzle テーブル定義
│   └── repositories/
│       ├── PhotoRepository.ts          # Drizzle ORM リポジトリ
│       └── LocalAnalysisRepository.ts  # FS 読み書きリポジトリ
├── docs/                      # 仕様・設計ドキュメント
├── analyze.sh                 # 解析自動再起動スクリプト
└── requirements.txt           # Python 依存パッケージ
```

解析前の写真置き場:

```text
{ANALYZE_ROOT}/
    ├── actor_a/
    └── actor_b/
```

Pi のデータディレクトリ:

```text
{PROJECT_ROOT}/
├── data/
│   └── {actor}_model.joblib   # 被写体別学習済みモデル
├── images/                    # 解析済み写真
│   ├── actor_a/
│   └── actor_b/
└── confirmed/                 # OK 確定写真
    └── actor_a/
```

MySQL（Raspberry Pi 上で稼働）:
- データベース名: `livephoto`（環境変数 `MYSQL_DATABASE` で設定）
- テーブル: `sorting_state`（被写体ごとの選別状態を管理）

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [docs/spec-base.md](docs/spec-base.md) | 機能要件・UI/UX 仕様 |
| [docs/workflow.md](docs/workflow.md) | データフロー・操作ワークフロー |
| [docs/spec-table.md](docs/spec-table.md) | テーブル設計・データ形式 |
| [docs/spec-directory.md](docs/spec-directory.md) | ディレクトリ構成 |
| [docs/architecture.md](docs/architecture.md) | 設計上の決定事項 |
| [docs/spec-analysis.md](docs/spec-analysis.md) | DeepFace 解析仕様 |
| [docs/spec-scoring.md](docs/spec-scoring.md) | Scikit-learn スコアリング仕様 |
| [docs/spec-finalize.md](docs/spec-finalize.md) | データ整理仕様 |
