# Project Guide: Live Photo Selector (Raspberry Pi Edition)

ライブ撮影写真の「感情分析」「顔の向き」「遮蔽物」を DeepFace で解析し、Scikit-learnでスコアリングして
iPhone から高速に選別するための Web アプリ。

詳細ドキュメント:

- [仕様・UI/UX](docs/spec-base.md)
- [データフロー・ワークフロー](docs/workflow.md)
- [データ形式](docs/spec-data-format.md)
- [ディレクトリ構成](docs/spec-directory.md)
- [設計上の決定事項](docs/architecture.md)

---

## プロジェクト構成

| レイヤー | 技術 |
| --- | --- |
| フロントエンド | Next.js 15 (App Router), TypeScript, Tailwind CSS, framer-motion |
| バックエンド | Next.js API Routes（ローカル FS 直接読み書き） |
| 解析スクリプト | Python 3.13, DeepFace, OpenCV (opencv-python-headless), Pillow, tf-keras, python-dotenv, tqdm |
| スコアリングスクリプト | Python 3.13, Scikit-learn, pandas, python-dotenv, tqdm |
| ホスティング | Raspberry Pi 4 + Cloudflare Tunnel |
| ストレージ | OneDrive（Mac・Pi 双方にローカルマウント） |

---

## ビルド・実行コマンド

**Frontend (Next.js)**:
- 開発: `npm run dev`
- ビルド: `npm run build`
- 本番起動: `npm start`

**Setup**:
- `npm install`
- `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

> コード変更後は必ず `npm run build` まで実行して確認すること。

---

## 環境変数

Next.js（Pi）と Python 解析スクリプト（Mac）で同じ変数名を共有する。

| 変数名 | 用途 |
| --- | --- |
| `PROJECT_ROOT` | プロジェクトのベースディレクトリ |
| `ONE_DRIVE_ROOT` | OneDriveのベースディレクトリ |

---

## テスト実行コマンド

- **Frontend**: `npm test -- --coverage`（カバレッジ 100% 目標）
- **Analysis**: `python -m pytest src/analysis/tests/ --cov=src/analysis --cov-report=term-missing`（カバレッジ 100% 目標）
- **Scoring**: `python -m pytest src/scoring/tests/ --cov=src/scoring --cov-report=term-missing`（カバレッジ 100% 目標）

---

## コーディング規約

- **命名規則**: メソッド名・変数名はキャメルケース（例: `userName`, `myFunction()`）
- **セキュリティ**: 認証情報はソースコードに直接記載しない（`.env` を使用）。画像配信時はパストラバーサル対策を必ず行う。
- **設計**: 依存性の注入（DI）で実装し、疎結合を保つ。
- **ドキュメント**: 全てのクラス・関数に Doc コメントを必ず記載する。
- **可読性**: 処理の意図が分かるよう、ロジックには適宜内部コメントを記載する。

---

## タスクガイダンス
- タスク実行時は `docs/tasks/*.md` にある指示書を最優先で確認すること。
- 作業完了
  - 指示書の TODO リストを更新する。
  - プロジェクト構成に更新があれば、プロジェクト構成を更新する。
    - 更新したら教えて下さい。
  - memoryに記憶する。

---

# 開発環境
- Dockerコンテナ上での開発であること留意すること

---