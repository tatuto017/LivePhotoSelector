# Live Photo Selector

ライブ撮影写真の「感情分析」「顔の向き」「遮蔽物」を DeepFace で解析し、Scikit-learn でスコアリングして iPhone から高速に選別するための Web アプリ。

## 技術スタック

| レイヤー | 技術 |
|---|---|
| フロントエンド | Next.js 15 (App Router), TypeScript, Tailwind CSS, framer-motion |
| バックエンド | Next.js API Routes, Drizzle ORM（MariaDB） |
| 解析スクリプト | Python 3.13, DeepFace, Facenet, opencv-python-headless, Pillow, tf-keras, SQLAlchemy, python-dotenv, tqdm |
| スコアリングスクリプト | Python 3.13, Scikit-learn, pandas, SQLAlchemy, python-dotenv, tqdm |
| データ整理スクリプト | Python 3.13, SQLAlchemy, python-dotenv |
| 振り分けスクリプト | Python 3.13, PyTorch, CLIP (OpenAI), Pillow, tqdm |
| 移動スクリプト | Python 3.13, SQLAlchemy, python-dotenv |
| データベース | MariaDB（Raspberry Pi 上で稼働） |
| ホスティング | Raspberry Pi 4 + Cloudflare Tunnel |
| ストレージ | Mac の `DATA_ROOT` ディレクトリを Pi の `data/` にマウント |

## 操作ワークフロー

```text
1. 振り分け（CLIP の学習済み特徴量を使って全体写真を被写体別に振り分け）
   python -m src.sorting.main

2. 振り分けミスした写真を学習させる
   # 事前に SORTING_ROOT/master_photos/{actor}/ に学習させる写真を配置する
   # 学習後、配置した写真は自動的に削除され member_features.pt が更新される
   python -m src.sorting.main --learn

3. 振り分け済み写真を解析作業ディレクトリへ移動
   python -m src.move.main
   ※ sorting_state に同名エントリ（learned=false）が存在する場合はリネームして移動

4. 写真を {DATA_ROOT}/inbox/{actor}/ に配置する

5. Mac で解析（inbox → images へ移動 + MariaDB に登録）
   bash analyze.sh
   ※ OOM Kill 時は自動再起動。file_list.txt が空になるまでループする
   ※ 1 枚処理するたびに file_list.txt からエントリを削除（再起動後の続きから再開対応）
   ※ MariaDB に INSERT されるため Pi 側から即時参照可能

6. iPhone で Pi にアクセスして OK/NG 選択
   右スワイプ = OK  /  左スワイプ = NG
   選択結果は MariaDB の sorting_state テーブルに即時書き込まれる

7. スコアリング（演者ごとの傾向を学習・スコア更新）
   python -m src.scoring.main

8. 写真整理（OK → confirmed/ へ移動、NG → 削除）
   python -m src.finalize.main
```

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
# .env を編集して各パスと DB 接続情報を設定
```

#### 4. 初回実行時の注意

初回実行時に DeepFace が感情モデル・Facenet モデルをダウンロードする（合計 約 100MB）。  
ダウンロード先は `~/.deepface/weights/`。

### 環境変数

Next.js（Pi）と Python スクリプト（Mac）で同じ変数名を共有する。

| 変数名 | 説明 |
|---|---|
| `PROJECT_ROOT` | プロジェクトのベースディレクトリ（Pi 側で使用） |
| `DATA_ROOT` | データディレクトリの絶対パス（Mac 側で使用。`PROJECT_ROOT` 外に配置可能） |
| `ANALYZE_ROOT` | 解析作業ディレクトリの絶対パス（Mac 側で使用。解析前の写真置き場） |
| `SORTING_ROOT` | 振り分けディレクトリの絶対パス（Mac 側で使用。`PROJECT_ROOT` 外に配置可能） |
| `MYSQL_HOST` | MariaDB ホスト名 |
| `MYSQL_PORT` | MariaDB ポート番号 |
| `MYSQL_USER` | MariaDB ユーザー名 |
| `MYSQL_PASSWORD` | MariaDB パスワード |
| `MYSQL_DATABASE` | MariaDB データベース名 |

```bash
PROJECT_ROOT=/path/to/LivePhotoSelector
DATA_ROOT=/path/to/data
ANALYZE_ROOT=/path/to/analyze
SORTING_ROOT=/path/to/sorting
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=livephoto
MYSQL_PASSWORD=secret
MYSQL_DATABASE=livephoto
```

## 実行コマンド

### フロントエンド

```bash
npm run dev       # 開発サーバー起動
npm run build     # 本番ビルド
npm start         # 本番起動
```

### Python スクリプト

```bash
# 解析（inbox の写真を DeepFace で解析して MariaDB に登録）
# OOM Kill 時の自動再起動ループ込み
bash analyze.sh

# スコアリング（Scikit-learn で学習・スコア更新）
python -m src.scoring.main

# 写真整理（OK → confirmed/、NG → 削除）
python -m src.finalize.main

# 振り分け（被写体別振り分け、デフォルト 4 並列）
python -m src.sorting.main

# 振り分け（並列数を指定）
python -m src.sorting.main --workers 8

# 学習（master_photos/ の写真から特徴量を更新）
python -m src.sorting.main --learn

# 移動（振り分け済み写真を ANALYZE_ROOT へ移動、デフォルト 4 並列）
python -m src.move.main

# 移動（並列数を指定）
python -m src.move.main --workers 8
```

## テスト

```bash
# フロントエンド（カバレッジ 100% 目標）
npm test

# 解析スクリプト（カバレッジ 100% 目標）
.venv_docker/bin/python -m pytest src/analysis/tests/

# スコアリングスクリプト（カバレッジ 100% 目標）
.venv_docker/bin/python -m pytest src/scoring/tests/

# データ整理スクリプト（カバレッジ 100% 目標）
.venv_docker/bin/python -m pytest src/finalize/tests/

# 振り分けスクリプト（カバレッジ 100% 目標）
.venv_docker/bin/python -m pytest src/sorting/tests/

# 移動スクリプト（カバレッジ 100% 目標）
.venv_docker/bin/python -m pytest src/move/tests/
```

## Raspberry Pi へのデプロイ

```bash
rsync -avz --delete \
  --exclude='.claude' \
  --exclude='.claudeignore' \
  --exclude='.coverage' \
  --exclude='.env' \
  --exclude='.git' \
  --exclude='.gitignore' \
  --exclude='.next' \
  --exclude='.pytest_cache' \
  --exclude='.venv' \
  --exclude='.venv_docker' \
  --exclude='.vscode' \
  --exclude='CLAUDE.md' \
  --exclude='README.md' \
  --exclude='analyze.sh' \
  --exclude='src' \
  --exclude='coverage' \
  --exclude='data' \
  --exclude='docs' \
  --exclude='node_modules' \
  --exclude='package-lock.json' \
  --exclude='vitest.config.ts' \
  --exclude='vitest.setup.ts' \
  /path/to/LivePhotoSelector/ pi@<PiのIPアドレス>:/path/to/LivePhotoSelector/
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
│   ├── sorting/               # Python 振り分けスクリプト (CLIP/PyTorch)
│   │   ├── main.py
│   │   └── tests/
│   ├── move/                  # Python 移動スクリプト (SQLAlchemy)
│   │   ├── main.py
│   │   └── tests/
│   └── mocks/                 # Vitest 用 MSW モックサーバー
│       ├── handlers.ts
│       └── server.ts
├── app/                       # Next.js App Router
│   ├── page.tsx               # 被写体一覧（Server Component）
│   ├── actors/[actor]/
│   │   └── page.tsx           # 写真選択（Server Component）
│   └── api/
│       └── actors/
│           ├── route.ts                          # GET /api/actors
│           └── [actor]/
│               ├── photos/route.ts               # GET pending 写真一覧（ページネーション）
│               ├── photos/[filename]/route.ts    # PATCH 選択状態
│               └── images/[filename]/route.ts    # GET 画像配信
├── components/
│   ├── PhotoCard.tsx          # 写真カード（スワイプ UI）
│   └── PhotoSelectionClient.tsx  # 写真選択クライアント
├── hooks/
│   ├── usePinchZoom.ts        # ピンチズーム・パンフック
│   └── usePhotoSelection.ts   # 選択状態管理フック
├── lib/
│   ├── types.ts               # 共通型定義
│   ├── db.ts                  # MariaDB 接続プール（Drizzle ORM）
│   ├── schema.ts              # Drizzle テーブル定義
│   └── repositories/
│       ├── LocalAnalysisRepository.ts  # MariaDB 読み書き + 画像配信（サーバーサイド）
│       ├── PhotoRepository.ts          # pending 写真取得（クライアントサイド HTTP）
│       └── ResultRepository.ts         # 選択状態保存（クライアントサイド HTTP）
├── migrations/                # DB マイグレーション SQL
│   ├── 001_create_analysis_records.sql
│   └── 002_create_sorting_state.sql
├── docs/                      # 仕様・設計ドキュメント
├── analyze.sh                 # 解析自動再起動スクリプト
└── requirements.txt           # Python 依存パッケージ
```

解析作業ディレクトリ（`ANALYZE_ROOT` で指定、`PROJECT_ROOT` 外に配置可能）:

```text
{ANALYZE_ROOT}/
├── actor_a/
└── actor_b/
```

振り分け用ディレクトリ（`SORTING_ROOT` で指定、`PROJECT_ROOT` 外に配置可能）:

```text
{SORTING_ROOT}/
├── member_features.pt         # 学習済みモデル
├── all_photos/                # 振り分け対象写真
├── master_photos/             # 学習用写真
│   ├── actor_a/
│   └── actor_b/
└── sorted_results/            # 振り分け結果
    ├── actor_a/
    └── actor_b/
```

データディレクトリ（`DATA_ROOT` で指定、`PROJECT_ROOT` 外に配置可能）:

```text
{DATA_ROOT}/
├── {actor}_model.joblib       # 被写体別学習済みモデル
├── images/                    # 解析済み写真
│   ├── actor_a/
│   └── actor_b/
└── confirmed/                 # OK 確定写真
    └── actor_a/
```

MariaDB（Raspberry Pi 上で稼働）:
- データベース名: `livephoto`（環境変数 `MYSQL_DATABASE` で設定）
- テーブル: `analysis_records`、`sorting_state`（[テーブル設計](docs/spec-table.md) 参照）

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
| [docs/spec-sorting.md](docs/spec-sorting.md) | 振り分け仕様 |
| [docs/spec-move.md](docs/spec-move.md) | 移動仕様 |
| [docs/DESIGN.md](docs/DESIGN.md) | UI デザイン仕様 |
