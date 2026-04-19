# DeepFaceによる解析仕様

## 処理概要

`ANALYZE_ROOT/{actor}/` の写真を DeepFace で解析し、`analysis_records` と `sorting_state` テーブルに結果を保存する。

解析対象ファイルはファイルシステムから直接取得する（`file_list.txt` は不要）。
`sorting_state` に既に存在するファイルはスキップするため、OOM Kill 後に再起動しても安全に途中から再開できる。

写真ファイルは解析後は `ANALYZE_ROOT` に留め、全解析完了後に手動でのファイルの移動を促す  
 `src.finalize.main --publish` フェーズで `sorting_state` の `public` を `true` へ更新する。

## 処理フロー

1. `ANALYZE_ROOT` 直下の被写体ディレクトリ（`{actor}/`）を列挙する
2. `analysis_records` から `(actor, filename)` の既存セットを取得する
3. `sorting_state` から処理済み `(actor_id, filename)` のセットを取得する
4. 未処理ファイルを `ThreadPoolExecutor`（デフォルト `--workers 4`）で並列解析する
   - 各画像はサブプロセス（`src.analysis.analyzer_subprocess`）で DeepFace 解析を実行し、OOM Kill がメインプロセスに波及しないよう分離する
   - DB 書き込みと共有キャッシュの更新はスレッドロックで保護する
5. 1 枚処理するたびに以下を実行する
   - 解析成功時: `analysis_records` に INSERT IGNORE（重複スキップ）
   - 解析成否によらず: `sorting_state` に INSERT IGNORE（重複スキップ）
6. 全エントリの処理完了で終了（exit 0）

## 解析結果の書き込み

### analysis_records への INSERT

解析成功時のみ INSERT する。同一 `(actor, filename, shooting_date)` が既に存在する場合は INSERT IGNORE でスキップする。

### sorting_state への INSERT

解析成否によらず INSERT する。同一 `(actor_id, filename, shooting_date)` が既に存在する場合は INSERT IGNORE でスキップする。

**初期値:**

| カラム | 初期値 | 説明 |
| --- | --- | --- |
| `score` | `max(感情スコア) / 100.0`（4桁丸め）| 解析失敗時は `NULL` |
| `selection_state` | `pending` | |
| `selected_at` | `NULL` | |

## 初期スコアの計算

```python
score = round(max(angry, fear, happy, sad, surprise, disgust, neutral) / 100.0, 4)
```

DeepFace が返す感情スコア（0〜100）の最大値を 0〜1 に正規化した値を初期スコアとする。
解析失敗時は `NULL`。

## OOM Kill 対応

Raspberry Pi (QEMU 環境) ではメモリ不足でプロセスが強制終了される場合がある。`analyze.sh` を使って `ANALYZE_ROOT` が空になるまで自動再起動する。

```bash
bash analyze.sh [--workers N]
```

- `--workers N`: 並列処理ワーカー数（Raspberry Pi 4: 2、M4 MacBook Air: 4〜6）
- 再起動時は `sorting_state` に未登録のファイルのみ処理し、処理済みファイルはスキップされる
- `ANALYZE_ROOT` 内のファイルが 0 件になったら自動的に `src.finalize.main --publish` を実行して公開処理に移行する

## サブプロセス分離

各画像の DeepFace 解析はサブプロセス（`src.analysis.analyzer_subprocess`）で実行する。

- サブプロセスのタイムアウト: **300 秒**
- サブプロセスが OOM Kill（exit 137）や解析エラーで終了した場合は `None` を返し、次の画像に進む
- サブプロセスは JSON を標準出力に出力し、メインプロセスがパースする
