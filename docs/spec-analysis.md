# DeepFaceによる解析仕様

## 処理概要
DeepFaceで解析対象の写真を解析して`{actor}_analysis.json`を更新して、`analysis.pki`に解析結果を保存する。

## 処理フロー
1. DeepFace で `INBOX_ROOT/{actor}/` の写真を 1 枚ずつ解析し、感情スコア・顔角度・遮蔽物フラグを取得する
   - 解析は **サブプロセス**（`src.analysis.analyzer_subprocess`）で実行し、OOM Kill がメインプロセスに波及しないよう分離する
   - サブプロセスが OOM Kill された場合は `score=None` で記録し、次の画像に進む
2. 1 枚処理するたびに以下を実行する（OOM Kill 後の再起動対応）
   a. `analysis.pki` にレコードを追記して保存（アトミック書き込み）
   b. `{actor}_analysis.json` にエントリを追記して保存（アトミック書き込み）
   c. 写真を `inbox → images` へ移動
3. 全枚数の処理完了で終了（exit 0）

## OOM Kill 対応

Raspberry Pi (QEMU 環境) ではメモリ不足でプロセスが強制終了される場合がある。`analyze.sh` を使って `inbox` が空になるまで自動再起動する。

```bash
bash analyze.sh
```

再起動時は `inbox` に残っているファイルのみ処理し、`images` 移動済みのファイルはスキップされる。

## {actor}_analysis.jsonの初期値
| フィールド | 初期値 |
| --- | --- |
| `score` | 主要表情の信頼スコア (0〜1) |
| `selectionState` | pending |
| `selectedAt` | null |
