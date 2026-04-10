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

## 画像配信のセキュリティ

- `LocalAnalysisRepository.readImageFile()` にてパストラバーサル対策を実施。
- 解決したパスが `imagesRoot` 配下であることを検証してから読み込む。
