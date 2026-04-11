# Scikit-learnによる、学習とスコアリング

## 処理概要
選別結果のOK/NGから傾向をScikit-learnで学習して、写真データをスコアリングする。

## 処理フロー
1. `{actor}_analysis.json`から`選別結果`が`pending`以外の写真データをScikit-learnに学習させる。
   - ハイパーパラメータチューニング
   - ランダムフォレスト
   - 解析データは`analysis.pki`の`DeepFace`の項目を評価基準に使用する（感情 7 次元 + 顔角度 1 次元 + 遮蔽物 1 次元 + Facenet 埋め込み 128 次元 = 計 137 次元）
   - `{actor}_analysis.json`の`選別結果`を採用(ok)/不採用(ng)とする
2. `{actor}_analysis.json`の`選別結果`が`pending`の写真データをスコアリングして更新する。
