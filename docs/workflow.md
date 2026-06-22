# データフロー・ワークフロー

## データフロー

```text
[Mac] 撮影写真 → {ANALYZE_ROOT}/{actor}/ に配置（src.move.main で SORTING_ROOT から自動移動）
    → DeepFace 解析（main.py）
            → EXIF から撮影日取得
            → {ANALYZE_ROOT}/ → MariaDB の analysis_records テーブルに INSERT
            → MariaDB の sorting_state テーブルに INSERT
            ↓ 解析完了後、{ANALYZE_ROOT}/{actor}/ を手動で {DATA_ROOT}/images/{actor}/ に移動
            → analyze.sh 再実行で sorting_state.public を true に更新（公開処理）
            Raspberry Pi（MariaDB サーバー稼働）
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
   # 学習後、配置した写真は自動的に振り分け結果ディレクトリ（sorted_results/{actor}/）へ移動され member_features.pt が更新される
   python -m src.sorting.main --learn

   # 学習済みの被写体IDを確認したい場合
   python -m src.sorting.main --list

   # 誤った被写体IDで学習してしまった場合はリネーム
   python -m src.sorting.main --rename <OLD_ID> <NEW_ID>

3. 振り分け済み写真を解析作業ディレクトリへ移動
   python -m src.move.main
   ※ sorting_state に同名エントリ（learned=false）が存在する場合はリネームして移動

4. Mac で解析（{ANALYZE_ROOT} の写真を DeepFace で解析して MariaDB に登録）
   bash analyze.sh
   ※ OOM Kill 時は自動再起動（ANALYZE_ROOT のファイルがなくなるまでループ）
   ※ MariaDB に INSERT されるため Pi 側から即時参照可能

5. 解析済み写真を公開（{ANALYZE_ROOT}/{actor}/ のファイルを手動で {DATA_ROOT}/images/{actor}/ に移動後）
   python -m src.finalize.main --publish
   ※ sorting_state.public を true に更新し、Web アプリ上で写真が表示対象になる

6. iPhone で Pi にアクセスして OK/NG 選択
   （右スワイプ = OK、左スワイプ = NG）
   選択結果は MariaDB の sorting_state テーブルに即時書き込まれる

7. スコアリング（演者ごとの傾向を学習・スコア更新）
   python -m src.scoring.main

8. 写真整理（OK → confirmed/ へ移動、NG → 削除）
   python -m src.finalize.main

   # lychee のルートアルバムIDを指定する場合（未指定時は環境変数 LYCHEE_ROOT_ALBUM_ID を使用）
   python -m src.finalize.main --album_id=<ALBUM_ID>
```
