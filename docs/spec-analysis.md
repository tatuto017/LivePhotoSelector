# DeepFaceによる解析仕様

## 処理概要
DeepFaceで解析対象の写真を解析して`{actor}_analysis.json`を更新して、`analysis.pki`に解析結果を保存する。

## 処理フロー
1. DeepFaceでINBOX_ROOT/{actor}/ の写真を解析し、`analysis.pki`に解析結果を保存
2. 写真を、inbox → images へ移動 + `{actor}_analysis.json` を更新
   - 下記の初期値を使用する

## {actor}_analysis.jsonの初期値
| フィールド | 初期値 |
| --- | --- |
| `score` | 主要表情の信頼スコア (0〜1) |
| `selectionState` | pending |
| `selectedAt` | null |
