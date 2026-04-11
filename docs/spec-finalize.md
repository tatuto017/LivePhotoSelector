# データ整理

## 処理概要
スコアリング後にデータ整理を行う

## 処理フロー

1. `{actor}_analysis.json`の`選別結果`が`ok`の写真を`OK確定写真フォルダ`に移動する。
2. `{actor}_analysis.json`の`選別結果`が`ng`の写真を削除する。
2. 選別結果が`ok`と`ng`の写真の選別データを`{actor}_analysis.json`から`analysis.json`に移動する。
 