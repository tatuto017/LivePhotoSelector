# 振り分け済み写真の移動機能

## 処理概要
振り分け済みの写真を解析作業ディレクトリに移動する
並列実行を行う (デフォルトのworker数は`4`)

## 処理フロー
1. `sorting_state` から `learned` が `false` のレコード一覧を取得する。
2. `{SORTING_ROOT}/sorted_results/{actor}` の写真を `{ANALYZE_ROOT}/{actor}` に指導する。
   - `sorting_state` の `actor_id` と `filename` が移動対象のファイル名を一致している場合は、移動対象のファイル名を変更する。
     - 例 `0001.jpg` を `0001_{num}.jpg` `{num}` は 2桁で `1` から開始する

## ドキュメント
- [spec-directory.md](spec-directory.md)
