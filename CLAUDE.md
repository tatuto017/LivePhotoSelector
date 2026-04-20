# Project Guide: Live Photo Selector (Raspberry Pi Edition)

ライブ撮影写真の「感情分析」「顔の向き」「遮蔽物」を DeepFace で解析し、Scikit-learnでスコアリングして
iPhone から高速に選別するための Web アプリ。

詳細ドキュメント:

- [仕様・UI/UX](docs/spec-base.md)
- [データフロー・ワークフロー](docs/workflow.md)
- [ディレクトリ構成](docs/spec-directory.md)
- [設計上の決定事項](docs/architecture.md)

---

## プロジェクト構成

| レイヤー | 技術 |
| --- | --- |
| フロントエンド | Next.js 15 (App Router), TypeScript, Tailwind CSS, framer-motion |
| バックエンド | Next.js API Routes, Drizzle ORM（MariaDB） |
| 解析スクリプト | Python 3.13, DeepFace, OpenCV (opencv-python-headless), Pillow, tf-keras, SQLAlchemy, python-dotenv, tqdm |
| スコアリングスクリプト | Python 3.13, Scikit-learn, pandas, SQLAlchemy, python-dotenv, tqdm |
| 振り分けスクリプト | Python 3.13, PyTorch, CLIP (OpenAI), Pillow, tqdm |
| データベース | MariaDB（Raspberry Pi 上で稼働） |
| ホスティング | Raspberry Pi 4 + Cloudflare Tunnel |

---

## ビルド・実行コマンド

**Frontend (Next.js)**:
- 開発: `npm run dev`
- ビルド: `npm run build`
- 本番起動: `npm start`

**Setup**:
- `npm install`
- `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

> コード変更後はビルドを行い結果を確認する、ビルド結果を確認出来るコマンド(ログ出力等)を提示し、手動実施を促し終了後に結果を確認すること。

---

## 環境変数

Next.js（Pi）と Python 解析スクリプト（Mac）で同じ変数名を共有する。

| 変数名 | 用途 |
| --- | --- |
| `PROJECT_ROOT` | プロジェクトのベースディレクトリ（Pi 側で使用） |
| `DATA_ROOT` | データディレクトリの絶対パス（Mac 側で使用。`PROJECT_ROOT` 外に配置可能） |
| `ANALYZE_ROOT` | 解析作業ディレクトリの絶対パス（Mac 側で使用。解析完了後に `DATA_ROOT` へ一括移動） |
| `SORTING_ROOT` | 振り分けディレクトリの絶対パス（Mac 側で使用。`PROJECT_ROOT` 外に配置可能） |
| `MYSQL_HOST` | MariaDB ホスト名 |
| `MYSQL_PORT` | MariaDB ポート番号 |
| `MYSQL_USER` | MariaDB ユーザー名 |
| `MYSQL_PASSWORD` | MariaDB パスワード |
| `MYSQL_DATABASE` | MariaDB データベース名 |

---

## テスト実行コマンド

- **Frontend**: `npm test`（package.json のスクリプトが `--coverage` を含むため追加不要。カバレッジ 100% 目標）
- **Analysis**: `.venv_docker/bin/python -m pytest src/analysis/tests/`（Docker 環境では `--cov` 不要。カバレッジ 100% 目標）
- **Scoring**: `.venv_docker/bin/python -m pytest src/scoring/tests/`（Docker 環境では `--cov` 不要。カバレッジ 100% 目標）
- **Finalize**: `.venv_docker/bin/python -m pytest src/finalize/tests/`（Docker 環境では `--cov` 不要。カバレッジ 100% 目標）
- **Sorting**: `.venv_docker/bin/python -m pytest src/sorting/tests/`（Docker 環境では `--cov` 不要。カバレッジ 100% 目標）

> テストは結果が確認出来るコマンド(ログ出力等)を提示し、手動実施を促し終了後に結果を確認すること。

---

## コーディング規約

- **命名規則**: メソッド名・変数名はキャメルケース（例: `userName`, `myFunction()`）
- **セキュリティ**: 認証情報はソースコードに直接記載しない（`.env` を使用）。画像配信時はパストラバーサル対策を必ず行う。
- **設計**: 依存性の注入（DI）で実装し、疎結合を保つ。
- **ドキュメント**: 全てのクラス・関数に Doc コメントを必ず記載する。
- **可読性**: 処理の意図が分かるよう、ロジックには適宜内部コメントを記載する。
- **DBアクセス**: DBアクセスはORマッパーを使用する。

---

## タスクガイダンス
- タスク実行時は `docs/tasks/*.md` にある指示書を最優先で確認すること。
- 作業完了
  - 指示書の TODO リストを更新する。
  - プロジェクト構成に更新があれば、プロジェクト構成を更新する。
    - 更新したら教えて下さい。

---

# 開発環境
- Dockerコンテナ上での開発であること留意すること
- ユニットテストは`.venv_docker`を使用すること
- `VSCode`の`Claude Code拡張`を使用している。

---

## 開発ワークフロー

**Research → Plan → Execute → Review → Ship** の順で進める。

1. **Research**: 既存実装・ライブラリを先に調査する（`gh search code`、Context7）
2. **Plan**: 必ずプランモードで開始。フェーズ分けしてゲート条件（テスト通過）を設ける
3. **Execute**: TDDで実装（テスト先行）
4. **Review**: `code-reviewer` エージェントで確認
5. **Ship**: ビルド確認後にコミット

---

## Claude Code セッション管理

- **新タスク = 新セッション** — 無関係なタスクは `/clear` でコンテキストを切り替える
- **コンテキスト 50% 到達で `/compact`** — 自動コンパクトより手動のほうが精度が高い
- **複数ファイルの調査はサブエージェントに委任** — 調査結果だけをメインコンテキストに返す
- **行き詰まったら `/rewind`** — 失敗した試みの前の状態に戻って再プロンプト

---

## Git 運用

- **1時間に1回、タスク完了時点でコミット**（後から squash merge する）
- **PRは小さく集中させる**（目安: 変更行数 p50 = 118行）
- 詳細は `.claude/rules/git.md` を参照

---

<important if="Python解析スクリプト（src/analysis/, src/scoring/, src/finalize/）を編集するとき">
- 仮想環境: `.venv_docker` を使用（Docker環境）
- モック: DeepFace・PIL・ファイル操作（shutil等）は必ずモック化
- DBモック: `_create_engine` をパッチし、`engine.connect().__enter__` で `mock_conn` を返す。行データは `types.SimpleNamespace` で attribute アクセスを模倣する
- テスト実行: `.venv_docker/bin/python -m pytest src/<module>/tests/`
</important>

<important if="Next.js フロントエンド・APIルート（app/, components/, hooks/, lib/）を編集するとき">
- テスト実行: `npm test`（`--coverage` は package.json のスクリプトに含まれているため重複指定しない）
- ビルド確認: `npm run build`（コード変更後は必ず実行）
- DBアクセスは Drizzle ORM 経由（直接クエリ禁止）。テーブル定義は `lib/schema.ts` を参照
</important>