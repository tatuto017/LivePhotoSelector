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
│   ├── scoring/               # Pythonスコアリングスクリプト (Scikit-learn)
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── tests/             # Pytestテスト
│   └── sorting/               # Python振り分けスクリプト (Ollama llama3.2-vision)
│       ├── __init__.py
│       ├── main.py
│       └── tests/             # Pytestテスト
├── .venv/                     # Python仮想環境
├── requirements.txt           # Python依存パッケージ
└── data/
    ├── analysis.json          # 選別データファイル
    ├── analysis.pki           # 解析データファイル
    └── {actor}_model.joblib   # 被写体別の学習済みファイル
```

### OneDrive
```text
{ONE_DRIVE_ROOT}/
├── data/
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
    ├── analysis.json          # 選別データファイル
    ├── analysis.pki           # 解析データファイル
    └── {actor}_model.joblib   # 被写体別の学習済みファイル
```

### OneDrive
```text
{ONE_DRIVE_ROOT}/
├── data/
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
