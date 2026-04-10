# データフロー・ワークフロー

## データフロー

```text
[Mac] 撮影写真 → inbox/{actor}/ に配置
    → DeepFace 解析（main.py）
            → EXIF から撮影日取得
            → inbox/ → images/ に移動 + analysis.json を更新
                ↕ OneDrive 自動同期
            Raspberry Pi 4（OneDrive マウント済み）
                → Next.js が images/ + analysis.json を直接読み書き
                    ↓ Cloudflare Tunnel（外出先）/ LAN（自宅）
                iPhone で OK/NG 選別・スワイプで即確定
                    ↓ OneDrive 同期で Mac に反映
[Mac] python -m src.analysis.main --scoring（学習とスコアリング）
        ※ 計算後に analysis.json を再読み込みし、Pi の書き込みと差分マージ
[Mac] python -m src.analysis.main --finalize（写真整理）
```

## 操作ワークフロー

```text
1. 写真を INBOX_ROOT/{actor}/ に配置する

2. Mac で解析（inbox → images へ移動 + analysis.json を更新）
   python -m src.analysis.main
   ※ OneDrive 同期により Pi 側に自動反映される

3. iPhone で Pi にアクセスして OK/NG 選別
   （右スワイプ = OK、左スワイプ = NG）
   選別結果は Pi 上の analysis.json に即書き込まれ、OneDrive で Mac に同期

4. スコアリング（演者ごとの傾向を学習・差分マージ対応）
   python -m src.analysis.main --scoring

5. 写真整理（OK → confirmed/ へ移動、NG → 削除）
   python -m src.analysis.main --finalize
```
