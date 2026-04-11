# 設計上の決定事項

## Server Component / Client Component 境界

- **Server Component** (`page.tsx`): `LocalAnalysisRepository` を直接使用して FS から写真データを取得する。Server Component では相対 URL を使った `fetch()` が使えないため、HTTP 経由ではなく直接 FS 読み込みを行う。
- **Client Component** (`PhotoSelectionClient.tsx`): `ResultRepository` はクラスインスタンスのため Server → Client の props として渡せない。`useMemo` でクライアント側にてインスタンス化する。

## スワイプとピンチズームの競合回避

- `usePinchZoom` が `isZoomed`（scale > 1.05）を返す。
- `PhotoCard` では `drag={isZoomed ? false : "x"}` としてズーム中は framer-motion のドラッグを無効化する。
- ピンチ・パン操作時は `stopPropagation()` でスワイプへのイベント伝播を防ぐ。

## 楽観的更新とリトライ

- `confirmPhoto` 呼び出し時、API 応答を待たずに即座に写真を非表示にする（楽観的更新）。
- 失敗時は最大 3 回（`MAX_RETRIES=3`）、1 秒間隔（`RETRY_DELAY_MS=1000`）でリトライする。
- 全リトライ失敗時のみ写真を再表示してエラーバナーを表示する。
- テスト時は `retryDelayMs=0` を DI することで即時リトライを実現し、fake timer を使わない。

## スコアリングの安全なマージ戦略

スコア計算中に Pi 側が `{actor}_analysis.json` を更新している可能性があるため、以下の手順で競合を回避する:

1. スコア計算前のスナップショットと、データ更新用でスナップショットをコピーする。
2. スコアリング処理で、結果をデータ更新用ファイルに反映する。
3. スナップショットと`{actor}_analysis.json`が同じなら、そのまま更新用ファイルを`{actor}_analysis.json`に上書きする。
4. 差分あり（Pi が書き込んだ）なら、`{actor}_analysis.json`の`score` のみをマージして保存。

## Python の `.env` 読み込み

- `python-dotenv` を使い、`run()` 冒頭で `_load_env()` を呼んで `.env` を読み込む（`override=False`）。
- テスト時は `patch("src.analysis.main._load_env")` でスキップ可能。

## データファイルの OneDrive 一元管理

`analysis.json`・`analysis.pki`・`{actor}_model.joblib` の 3 ファイルを `{ONE_DRIVE_ROOT}/data/` に配置する。

- **理由**: Mac（解析・スコアリング実行環境）と Raspberry Pi（選別 UI 実行環境）の双方が OneDrive をマウントしているため、PROJECT_ROOT に置くと環境ごとに別ファイルになり同期が取れない。OneDrive に一元化することで両環境から同一ファイルを参照できる。
- **影響**: `{PROJECT_ROOT}/data/` はローカル専用の一時ファイル等の用途に限定され、現時点では使用ファイルなし。

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

1 枚解析するたびに `analysis.pki` と `{actor}_analysis.json` を保存し、`inbox → images` への移動はその後に行う。OOM Kill 後に再起動しても既処理ファイルはスキップされ、続きから再開できる。

### アトミック書き込み

`saveRecords` / `saveActorEntries` は以下の手順で書き込む。書き込み中の Kill によるファイル破損を防ぐ。

1. 同一ディレクトリ内に一時ファイルを作成して書き込む
2. `shutil.move` で宛先ファイルに上書き（同一 FS 内なので atomic rename）

### JSON 破損フォールバック

`loadActorEntries` は `JSONDecodeError` を捕捉して空リストを返す。破損した場合は当該アクターの JSON を再構築できる。

### サブプロセスによる OOM Kill 分離

`PhotoAnalyzer.analyze()` は DeepFace/TF のモデル読み込みを **サブプロセス**（`src.analysis.analyzer_subprocess`）で実行する。

- **目的**: TF ランタイム＋感情モデルの読み込みがメモリを圧迫し、メインプロセスごと OOM Kill されると無限ループに陥る問題を防ぐ。
- **動作**: サブプロセスが OOM Kill（exit 137）や解析エラーで終了した場合、メインプロセスは `None` として扱い次の画像に進む。
- **効果**: メインプロセスは TF を一切読み込まないため軽量に保たれ、OOM Kill の対象にならない。サブプロセス終了ごとに TF・モデルのメモリが完全解放される。

サブプロセス内では以下のメモリ削減対策を実施している:

- **TF スレッド数の制限**: `TF_NUM_INTRAOP_THREADS=1` / `TF_NUM_INTEROP_THREADS=1` / `OMP_NUM_THREADS=1` を DeepFace インポート前に設定し、TF のスレッドプール用メモリを削減する。
- **画像リサイズ**: PIL で長辺 640px 以内にリサイズしてから numpy 配列で DeepFace に渡す。6000x4000px 等の大きな画像のメモリ使用量を約 1/90 に削減する。

### 自動再起動ループ（analyze.sh）

```bash
bash analyze.sh
```

`inbox` にファイルが残っている限り `python -m src.analysis.main` を再起動し続ける。正常終了（exit 0）または inbox が空になった時点でループを終了する。

## 画像配信のセキュリティ

- `LocalAnalysisRepository.readImageFile()` にてパストラバーサル対策を実施。
- 解決したパスが `imagesRoot` 配下であることを検証してから読み込む。
