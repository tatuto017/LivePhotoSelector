# 基本仕様

## 機能要件

- **被写体管理**: 撮影対象（アーティスト/メンバー等）は複数人を想定し、対象単位で選別・管理できるようにする。
- **モバイル最適化**: 写真選択画面は主に iPhone からの操作を想定した UI/UX とする。
- **動的読み込みと更新**:
  - OK/NG が確定された画像は画面から即座に非表示にする（楽観的更新）。
  - 写真の読み込みは、表示写真1枚 + 5枚まで先読みする動的ロードにする。
- **選択結果保存**
  - スワイプ操作でのOK/NG の確定時に、選択結果をテーブルに保存する。
     - `sorting_state` の `selectionState`に選択結果を保存する。
     - `sorting_state` の `selected_at` に選択日時を保存する。
     - `actor_id`, `filename`, `shooting_date` をキーにして更新する。
- **データ管理**:
  - 被写体の選別状態は MySQL データベース（`sorting_state` テーブル）に保存する。
  - データ整理時に、選別結果がOKの写真は確定済みフォルダに移動、NGの写真は削除する。
  - Scikit-learnの学習データは、各々の被写体に特化させる為に被写体別に分ける。
- **保存アクション**: スワイプで OK/NG を即座に確定させる。
- **解析**: DeepFace による重い解析は Mac のみで実行する。Raspberry Pi（Next.js）側には DeepFace をインストールしない。
  - [解析仕様](spec-analysis.md)
- **スコアリング**: Scikit-learnによる学習とスコアリングはMac のみで実行する。Raspberry Pi（Next.js）側には Scikit-learn をインストールしない。
  - [スコアリング仕様](spec-scoring.md)
- **データ整理**: スコアリング後にデータの整理を行う。
  - [データ整理仕様](spec-finalize.md)
- **振り分け済み写真の移動**: 振り分け済みの写真を解析作業ディレクトリに移動する。
  - [写真移動仕様](spec-move.md)
- **外部アクセス**: Cloudflare Tunnel を使用して iPhone（外出先）から Raspberry Pi に安全にアクセスする。
- **選別基準**: 演者の主観を最優先とする。スコアリングはソート・フィルタリングの補助指標として利用する。
- **撮影日管理**: 選別結果に撮影日（`shootingDate`）を含める。EXIF から取得し `YYYY-MM-DD` 形式で保存する。同名ファイルでも撮影日が異なる場合は別エントリとして管理する。
- **振り分け**: 被写体別に写真を振り分ける。

## UI/UX

- 被写体ページの先頭に「← NG | ピンチで拡大 | OK →」の説明バーを表示する。
- 次の写真が見えないようにする。
  - 横長写真の場合、次の写真が見えてしまう。
- iPhone で片手で高速に OK/NG を選択できるスワイプ UI（右: OK、左: NG）。
- ピンチイン/アウトで写真の拡大/縮小、拡大中は 1 本指で上下左右パン移動ができる。
- ズーム中はスワイプを無効化し、誤操作を防ぐ。
- `score`の高い順に写真を表示し、意思決定を加速する。
- 保存失敗時はリトライを最大 3 回（1 秒間隔）行い、全失敗時のみエラーバナーを表示する。
- 被写体一覧・写真一覧に枚数は表示しない。

## 環境変数

Next.js（Pi）と Python 解析スクリプト（Mac）で環境依存の部分は環境変数で対応する。
環境変数は`.env` で設定する。

| 変数名 | 説明 |
| --- | --- |
| `PROJECT_ROOT` | プロジェクトのベースディレクトリ（Pi 側で使用） |
| `DATA_ROOT` | データディレクトリの絶対パス（Mac 側で使用。`PROJECT_ROOT` 外に配置可能） |
| `ANALYZE_ROOT` | 解析作業ディレクトリの絶対パス（Mac 側で使用。`PROJECT_ROOT` 外に配置可能。解析完了後に `DATA_ROOT` へ手動で一括移動） |
| `SORTING_ROOT` | 振り分けディレクトリの絶対パス（Mac 側で使用。`PROJECT_ROOT` 外に配置可能） |
| `MYSQL_HOST` | MySQL ホスト名 |
| `MYSQL_PORT` | MySQL ポート番号 |
| `MYSQL_USER` | MySQL ユーザー名 |
| `MYSQL_PASSWORD` | MySQL パスワード |
| `MYSQL_DATABASE` | MySQL データベース名 |

**設定例（Mac）:**
```bash
DATA_ROOT=/Volumes/PiShare/data
ANALYZE_ROOT=/tmp/livephoto_analyze
MYSQL_HOST=raspberrypi.local
MYSQL_PORT=3306
MYSQL_USER=livephoto
MYSQL_PASSWORD=secret
MYSQL_DATABASE=livephoto
```

**設定例（Pi）:**
```bash
PROJECT_ROOT=/path/to/LivePhotoSelector
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=livephoto
MYSQL_PASSWORD=secret
MYSQL_DATABASE=livephoto
```
