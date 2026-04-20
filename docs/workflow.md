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
1. 振り分け（CLIP の学習済み特徴量を使って全体写真を被写体別に振り分け）
   python -m src.sorting.main

2. 振り分けミスした写真を学習させる
   # 事前に SORTING_ROOT/master_photos/{actor}/ に学習させる写真を配置する
   # 学習後、配置した写真は自動的に削除され member_features.pt が更新される
   python -m src.sorting.main --learn

3. 振り分け済み写真を解析作業ディレクトリへ移動
   python -m src.move.main
   ※ sorting_state に同名エントリ（learned=false）が存在する場合はリネームして移動

4. 写真を {DATA_ROOT}/inbox/{actor}/ に配置する

5. Mac で解析（{DATA_ROOT}/inbox → {DATA_ROOT}/images へ移動 + MariaDB に登録）
   bash analyze.sh
   ※ OOM Kill 時は自動再起動。sorting_state の未処理件数が 0 になるまでループする
   ※ MariaDB に INSERT されるため Pi 側から即時参照可能

6. iPhone で Pi にアクセスして OK/NG 選択
   （右スワイプ = OK、左スワイプ = NG）
   選択結果は MariaDB の sorting_state テーブルに即時書き込まれる

7. スコアリング（演者ごとの傾向を学習・スコア更新）
   python -m src.scoring.main

8. 写真整理（OK → confirmed/ へ移動、NG → 削除）
   python -m src.finalize.main
```
