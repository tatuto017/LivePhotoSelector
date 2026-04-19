# データ整理

## 処理概要
スコアリング後にデータ整理を行う

## 処理フロー

### フェーズ1: 解析ファイルの公開（解析完了後）

1. `{ANALYZE_ROOT}/{actor}` 内の全ファイルを `{DATA_ROOT}/images/{actor}` へ一括移動する。
   - 被写体（actor）ごとに移動するが、**ファイル単位での移動は行わない**。
   - 全ファイルの移動が完了してから次のステップへ進む。
2. `sorting_state` テーブルの対象 actor の `public` を `true` に更新する。
   - これにより Web アプリ上で写真が表示対象になる。

### フェーズ2: 選択後の整理（選択完了後）

1. `sorting_state` テーブルの `selectionState` が `ok` の写真を `OK確定写真フォルダ` に移動する。
2. `sorting_state` テーブルの `selectionState` が `ng` の写真を削除する。
