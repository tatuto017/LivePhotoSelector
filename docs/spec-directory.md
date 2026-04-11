# ディレクトリ構成

## Mac

### ローカル
```text
{PROJECT_ROOT}/
├── src/
│   ├── analysis/              # Python解析スクリプト (DeepFace)
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── tests/             # Pytestテスト
│   │       ├── __init__.py
│   │       └── test_main.py
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
│   └── mocks/                 # Vitest 用 MSW モックサーバー
│       ├── handlers.ts
│       └── server.ts
├── app/                       # Next.js App Router
│   ├── page.tsx               # 被写体一覧（Server Component）
│   ├── actors/[actor]/
│   │   └── page.tsx           # 写真選別（Server Component）
│   └── api/
│       └── actors/
│           ├── route.ts                       # GET /api/actors
│           └── [actor]/
│               ├── photos/[filename]/route.ts   # PATCH 選別状態
│               └── images/[filename]/route.ts   # GET 画像配信
├── components/
│   ├── PhotoCard.tsx          # 写真カード（スワイプ UI）
│   └── PhotoSelectionClient.tsx  # 写真選別クライアント
├── hooks/
│   ├── usePinchZoom.ts        # ピンチズーム・パンフック
│   └── usePhotoSelection.ts   # 選別状態管理フック
├── lib/
│   ├── types.ts               # 共通型定義
│   └── repositories/
│       ├── LocalAnalysisRepository.ts  # FS読み書きリポジトリ
│       └── ResultRepository.ts         # HTTP保存リポジトリ
├── .venv/                     # Python仮想環境
├── requirements.txt           # Python依存パッケージ
└── data/
```

### OneDrive
```text
{ONE_DRIVE_ROOT}/
├── data/
│   ├── analysis.json          # 選別データファイル
│   ├── analysis.pki           # 解析データファイル
│   ├── {actor}_model.joblib   # 被写体別の学習済みファイル
│   └── {actor}_analysis.json  # 被写体別の解析データファイル
├── inbox/                     # 解析前の写真置き場
│   ├── actor_a/
│   └── actor_b/
├── images/                    # 解析済み写真
│   ├── actor_a/
│   └── actor_b/
└── confirmed/                 # OK確定写真
    └── actor_a/
```

## Raspberry Pi
```text
{PROJECT_ROOT}/
└── data/
```

### OneDrive
```text
{ONE_DRIVE_ROOT}/
├── data/
│   ├── analysis.json          # 選別データファイル
│   ├── analysis.pki           # 解析データファイル
│   ├── {actor}_model.joblib   # 被写体別の学習済みファイル
│   └── {actor}_analysis.json  # 被写体別の解析データファイル
├── inbox/                     # 解析前の写真置き場（INBOX_ROOT）
│   ├── actor_a/
│   └── actor_b/
├── images/                    # 解析済み写真（IMAGES_ROOT）
│   ├── actor_a/
│   └── actor_b/
└── confirmed/                 # OK確定写真（ARCHIVE_ROOT）
    └── actor_a/
```
