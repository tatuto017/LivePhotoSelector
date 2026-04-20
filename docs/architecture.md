# 設計上の決定事項

## Server Component / Client Component 境界

- **Server Component** (`page.tsx`): `LocalAnalysisRepository` を直接使用して MariaDB から被写体・写真データを取得する。Server Component では相対 URL を使った `fetch()` が使えないため、HTTP 経由ではなく直接 DB 読み込みを行う。
- **Client Component** (`PhotoSelectionClient.tsx`):
  - `PhotoRepository`: pending 写真を API 経由でページネーション取得する（クライアントサイド HTTP）。
  - `ResultRepository`: 選択結果を API 経由で保存する（クライアントサイド HTTP）。
  - いずれもクラスインスタンスのため Server → Client の props として渡せない。`useMemo` でクライアント側にてインスタンス化する。

## スワイプとピンチズームの競合回避

- `usePinchZoom` が `isZoomed`（scale > 1.05）を返す。
- `PhotoCard` では `drag={isZoomed ? false : "x"}` としてズーム中は framer-motion のドラッグを無効化する。
- ピンチ・パン操作時は `stopPropagation()` でスワイプへのイベント伝播を防ぐ。

## 楽観的更新とリトライ

- `confirmPhoto` 呼び出し時、API 応答を待たずに即座に写真を非表示にする（楽観的更新）。
- 失敗時は最大 3 回（`MAX_RETRIES=3`）、1 秒間隔（`RETRY_DELAY_MS=1000`）でリトライする。
- 全リトライ失敗時のみ写真を再表示してエラーバナーを表示する。
- テスト時は `retryDelayMs=0` を DI することで即時リトライを実現し、fake timer を使わない。

## Python の `.env` 読み込み

- `python-dotenv` を使い、`run()` 冒頭で `_load_env()` を呼んで `.env` を読み込む（`override=False`）。
- テスト時は `patch("src.analysis.main._load_env")` でスキップ可能。

## データファイルの配置

ファイルの用途に応じて `{DATA_ROOT}/`（Mac・Pi 共有マウント）に配置する。
Mac 側は環境変数 `DATA_ROOT` で任意のパスを指定でき、`PROJECT_ROOT` 外に配置できる。
解析結果は MariaDB の `analysis_records` テーブル、選択状態は `sorting_state` テーブルで管理する。

| ファイル | 配置 | 用途 |
| --- | --- | --- |
| `{actor}_model.joblib` | `{DATA_ROOT}/` | 学習済みモデル（Mac でのみ使用） |

### 解析結果の DB 登録フロー

Pi（選択 UI）は MariaDB の `sorting_state` テーブルを直接読み書きする。解析スクリプト側は以下の手順でデータを登録する。

1. **ファイル列挙**: `ANALYZE_ROOT/{actor}/` をファイルシステムから直接走査して解析対象を収集する。
2. **処理済みスキップ**: 起動時に `sorting_state` テーブルの `(actor_id, filename)` を取得し、既処理ファイルを除外する（OOM Kill 後の再起動対応）。
3. **並列解析**: 未処理ファイルを `ThreadPoolExecutor`（デフォルト 4 ワーカー）で並列に DeepFace 解析する。
4. **analysis_records INSERT**: 解析成功時のみレコードを INSERT する。同一 `(actor, filename)` が既に存在する場合はスキップする（INSERT IGNORE）。
5. **sorting_state INSERT**: 解析成功・失敗を問わず全ファイルのエントリを INSERT する。同一 `(actor_id, filename)` が既に存在する場合はスキップする（INSERT IGNORE）。
6. **ファイル移動なし**: 写真は解析後も `ANALYZE_ROOT` に留める。全解析完了後に手動で `DATA_ROOT/images/` へ移動する。

> `file_list.txt` は廃止。処理済み判定は `sorting_state` テーブルへの問い合わせで行う。

## OpenCV ヘッドレスモード

Docker コンテナ等の GUI なし環境では `opencv-python` が `libGL.so.1` を要求して起動失敗する。そのため `opencv-python-headless` を使用する。

- **対象**: 解析スクリプト（DeepFace が内部で OpenCV を使用）
- **影響なし**: DeepFace が使う顔検出・特徴量抽出は headless 版でも動作する。

## DeepFace の numpy 型変換

DeepFace が返す感情スコアは `numpy.float32` 型であり、そのまま JSON にシリアライズすると `TypeError` が発生する。そのため `PhotoAnalyzer.analyze` 内で `AnalysisRecord` に格納する際に `float()` で Python ネイティブ型に変換する。

- **対象フィールド**: `angry` / `fear` / `happy` / `sad` / `surprise` / `disgust` / `neutral`
- **初期 score 計算**: `_run_analyze` 内の `max_val` も同様に `float(max_val)` で変換してから `round()` を適用する。

## 解析スクリプトのクラッシュ耐性

Raspberry Pi (QEMU x86_64 エミュレーション) は OOM Kill でプロセスが強制終了されるリスクがある。以下の対策を実施している。

### 増分保存（per-image save）

1 枚解析するたびに以下を順番に実行し、OOM Kill 後に再起動しても続きから再開できる。

1. DeepFace 解析（サブプロセス）
2. `analysis_records` テーブルに INSERT する（重複は INSERT IGNORE でスキップ）
3. `sorting_state` テーブルに INSERT する（重複は INSERT IGNORE でスキップ）

再起動時は `sorting_state` テーブルの既処理キーを取得して未処理ファイルに絞り込むため、`file_list.txt` によるアトミック削除は不要。

### サブプロセスによる OOM Kill 分離

`PhotoAnalyzer.analyze()` は DeepFace/TF のモデル読み込みを **サブプロセス**（`src.analysis.analyzer_subprocess`）で実行する。

- **目的**: TF ランタイム＋感情モデルの読み込みがメモリを圧迫し、メインプロセスごと OOM Kill されると無限ループに陥る問題を防ぐ。
- **動作**: サブプロセスが OOM Kill（exit 137）や解析エラーで終了した場合、メインプロセスは `None` として扱い次の画像に進む。
- **効果**: メインプロセスは TF を一切読み込まないため軽量に保たれ、OOM Kill の対象にならない。サブプロセス終了ごとに TF・モデルのメモリが完全解放される。

サブプロセス内では以下のメモリ削減対策を実施している:

- **TF スレッド数の制限**: `TF_NUM_INTRAOP_THREADS=1` / `TF_NUM_INTEROP_THREADS=1` / `OMP_NUM_THREADS=1` を DeepFace インポート前に設定し、TF のスレッドプール用メモリを削減する。
- **画像リサイズ**: PIL で長辺 1920px 以内にリサイズしてから numpy 配列で DeepFace に渡す。6000x4000px 等の大きな画像のメモリ使用量を約 1/10 に削減する。

### 自動再起動ループ（analyze.sh）

```bash
bash analyze.sh
```

`sorting_state` テーブルの未処理ファイル数が 0 になるまで `python -m src.analysis.main` を再起動し続ける。正常終了（exit 0）または未処理ファイルがなくなった時点でループを終了する。

## 画像配信のセキュリティ

- `LocalAnalysisRepository.readImageFile()` にてパストラバーサル対策を実施。
- 解決したパスが `imagesRoot`（`{PROJECT_ROOT}/data/images/`）配下であることを検証してから読み込む（Pi 側）。

## 振り分けスクリプトのアーキテクチャ

### モード分岐（`--learn` フラグ）

振り分けスクリプトは `--learn` の有無で 2 つのモードを持つ。

| モード | コマンド | 処理 |
| --- | --- | --- |
| 振り分けのみ（デフォルト） | `python -m src.sorting.main` | `run()` → `Classifier.classify()` |
| 学習のみ | `python -m src.sorting.main --learn` | `learn()` → `Learner.learn()` |

同一実行で学習と振り分けを同時に行う設計は採用しない。学習後に特徴量が更新されるため、振り分けは別途実行する。

### CLIPによる特徴量データベース設計

- モデル: `ViT-L/14`（OpenAI CLIP）。float32 に統一して MPS / CPU で動作する。
- 学習: `master_photos/{actor}/` の画像から特徴量ベクトルを抽出し、`member_features.pt`（`actor名 → Tensor` の辞書）に追記保存する。学習済み画像は処理後に削除する。
- 振り分け: 各 actor の特徴量の平均ベクトルとのコサイン類似度（内積）で最近傍 actor を判定し、`sorted_results/{actor}/` へ移動する。
- 抽出エラーが発生した画像はスキップし（ファイルは削除しない）、次の画像の処理を続行する。

### 依存性の注入（DI）

`run()` / `learn()` の引数に `FeatureRepository`・`FeatureExtractor`・`Classifier` / `Learner` を注入できる。省略した場合は関数内でデフォルトインスタンスを生成する。モデルのロード（`clip.load()`）はコストが高いため、テストではすべてモック化する。

### 振り分けモジュールのテスト戦略

`torch` / `clip` は `.venv_docker` にインストールされていないため、`conftest.py` で `sys.modules` に直接スタブを登録してから `main.py` をインポートする。これにより `torch.load` / `torch.save` / `clip.load` を `MagicMock` で制御し、実際のモデルなしでロジックのみをテストできる。
