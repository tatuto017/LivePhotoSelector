# ディレクトリ構成

## Mac

### ローカル
```text
{PROJECT_ROOT}/
├── src/
│   ├── db_schema.py           # SQLAlchemy テーブル定義（Python共通）
│   ├── analysis/              # Python解析スクリプト (DeepFace)
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── analyzer_subprocess.py  # DeepFace解析サブプロセス（OOM Kill分離）
│   │   └── tests/             # Pytestテスト
│   │       ├── __init__.py
│   │       ├── test_main.py
│   │       └── test_analyzer_subprocess.py
│   ├── scoring/               # Pythonスコアリングスクリプト (Scikit-learn)
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── tests/             # Pytestテスト
│   │       ├── __init__.py
│   │       └── test_main.py
│   ├── finalize/              # Pythonデータ整理スクリプト
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── tests/             # Pytestテスト
│   │       ├── __init__.py
│   │       └── test_main.py
│   ├── sorting/               # Python振り分けスクリプト (CLIP/PyTorch)
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── tests/             # Pytestテスト
│   │       ├── __init__.py
│   │       ├── conftest.py    # torch・clip モック
│   │       └── test_main.py
│   ├── move/                  # Python移動スクリプト (SQLAlchemy)
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── tests/             # Pytestテスト
│   │       ├── __init__.py
│   │       └── test_main.py
│   └── mocks/                 # Vitest 用 MSW モックサーバー
│       ├── handlers.ts
│       └── server.ts
├── migrations/                # DBマイグレーションSQL
│   ├── 001_create_analysis_records.sql
│   └── 002_create_sorting_state.sql
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
│   ├── db.ts                  # MariaDB 接続プール生成
│   ├── schema.ts              # Drizzle テーブル定義
│   └── repositories/
│       ├── LocalAnalysisRepository.ts  # MariaDB 読み書き + 画像配信リポジトリ（サーバーサイド）
│       ├── PhotoRepository.ts          # pending 写真取得リポジトリ（クライアントサイド HTTP）
│       └── ResultRepository.ts         # 選択状態保存リポジトリ（クライアントサイド HTTP）
├── .venv/                     # Python仮想環境（Mac用）
└── requirements.txt           # Python依存パッケージ
```

### 解析作業ディレクトリ（`ANALYZE_ROOT` で指定、`PROJECT_ROOT` 外に配置可能）
```text
{ANALYZE_ROOT}/                # 環境変数 ANALYZE_ROOT で指定した任意のパス（Mac 側）
├── actor_a/
└── actor_b/
```

### データディレクトリ（`DATA_ROOT` で指定、`PROJECT_ROOT` 外に配置可能）
```text
{DATA_ROOT}/                   # 環境変数 DATA_ROOT で指定した任意のパス
├── {actor}_model.joblib       # 被写体別学習済みモデル
├── images/                    # 解析済み写真（ANALYZE_ROOT から手動移動）
│   ├── actor_a/
│   └── actor_b/
└── confirmed/                 # OK確定写真
    └── actor_a/
```

### 振り分け用ディレクトリ（`SORTING_ROOT` で指定、`PROJECT_ROOT` 外に配置可能）
```text
{SORTING_ROOT}/                # 環境変数 SORTING_ROOT で指定した任意のパス
├── member_features.pt         # 学習済みモデル
├── all_photos/                # 振り分け対象写真のディレクトリ
├── master_photos/             # 学習用写真ディレクトリ
│   ├── actor_a/
│   └── actor_b/
└── sorted_results/            # 振り分け結果ディレクトリ
    ├── actor_a/
    └── actor_b/
```

## Raspberry Pi
```text
{PROJECT_ROOT}/
└── data/
    ├── {actor}_model.joblib   # 被写体別学習済みモデル
    ├── images/                # 解析済み写真（ANALYZE_ROOT から手動移動）
    │   ├── actor_a/
    │   └── actor_b/
    └── confirmed/             # OK確定写真
        └── actor_a/
```

## MariaDB（Raspberry Pi 上で稼働）
- データベース名: `livephoto`（環境変数 `MYSQL_DATABASE` で設定）
- テーブル: `analysis_records`、`sorting_state`（[テーブル設計](spec-table.md) 参照）
