# データフロー・ワークフロー

## データフロー

```text
[Mac] 撮影写真 → {DATA_ROOT}/inbox/{actor}/ に配置
    → DeepFace 解析（main.py）
            → EXIF から撮影日取得
            → {DATA_ROOT}/inbox/ → {DATA_ROOT}/images/ に移動
            → MariaDB の analysis_records テーブルに INSERT
            → MariaDB の sorting_state テーブルに INSERT
            Raspberry Pi 4（MariaDB サーバー稼働）
                → Next.js が images/ を配信 + MariaDB を直接読み書き
                    ↓ Cloudflare Tunnel（外出先）/ LAN（自宅）
                iPhone で OK/NG 選択・スワイプで即確定
                    ↓ MariaDB の sorting_state テーブルに即時反映
[Mac] python -m src.scoring.main（学習とスコアリング）
        ※ MariaDB の analysis_records / sorting_state テーブルからデータ取得・スコア更新
[Mac] python -m src.finalize.main（写真整理）
        ※ MariaDB の sorting_state テーブルから選択結果取得
```

## 操作ワークフロー

```text
1. 写真を {DATA_ROOT}/inbox/{actor}/ に配置する

2. Mac で解析（{DATA_ROOT}/inbox → {DATA_ROOT}/images へ移動 + MariaDB に登録）
   bash analyze.sh
   ※ OOM Kill 時は自動再起動。file_list.txt が空になるまでループする
   ※ 1 枚処理するたびに file_list.txt からエントリを削除（再起動時の続きから再開対応）
   ※ MariaDB に INSERT されるため Pi 側から即時参照可能

3. iPhone で Pi にアクセスして OK/NG 選択
   （右スワイプ = OK、左スワイプ = NG）
   選択結果は MariaDB の sorting_state テーブルに即時書き込まれる

4. スコアリング（演者ごとの傾向を学習・スコア更新）
   python -m src.scoring.main

5. 写真整理（OK → confirmed/ へ移動、NG → 削除）
   python -m src.finalize.main
```
