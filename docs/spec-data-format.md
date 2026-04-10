# データ形式

##　被写体別の選別データファイル

`{actor}_analysis.json`

DeepFace による選別状態を格納したファイル、被写体IDでファイルを分ける。
フィールドは`analysis.json`と同じ


```json
[
  {
    "filename": "img001.jpg",
    "shootingDate": "2026-04-01",
    "score": 0.5,
    "selectionState": "ok",
    "selectedAt": "2026-04-06T12:00:00.000Z"
  }
]
```
## 選別データファイル

`analysis.json`

DeepFace による選別状態を格納したファイル、被写体ID をキーとしたオブジェクト。

```json
{
  "actor_a": [
    {
      "filename": "img001.jpg",
      "shootingDate": "2026-04-01",
      "score": 0.5,
      "selectionState": "ok",
      "selectedAt": "2026-04-06T12:00:00.000Z"
    }
  ]
}
```

| フィールド | 型 | 付与タイミング | 初期値 | 説明 |
| --- | --- | --- | --- | --- |
| `filename` | string | Python 解析時 | | 画像ファイル名 |
| `shootingDate` | string | Python 解析時 | | 撮影日（EXIF DateTimeOriginal）`YYYY-MM-DD` |
| `score` | number? | `--scoring` 実行時 | 主要表情の信頼スコア（0〜1） | スコアリング（Pi 差分マージ対応） |
| `selectionState` | string? | Next.js 保存時 | pending | 選別結果 / `"ok"` / `"ng"` / `pending`|
| `selectedAt` | string? | Next.js 保存時 | null | / 選別確定日時（ISO 8601） |

## 解析データファイル

`analysis.pki`

DeepFace による解析データを格納したファイル

| フィールド | 説明 |
| --- | --- |
| `actor` | 被写体ID |
| `filename` | 画像ファイル名 |
| `shootingDate` | 撮影日（EXIF DateTimeOriginal）`YYYY-MM-DD` |
| `angry` | 怒り (DeepFace) |
| `fear` | 恐怖 (DeepFace) |
| `happy` | 幸福 (DeepFace) |
| `sad` | 悲しみ (DeepFace) |
| `surprise` | 驚き (DeepFace) |
| `disgust` | 嫌悪 (DeepFace) |
| `neutral` | 自然 (DeepFace) |
| `faceAngle` | 顔のロール角 (両目座標から計算、度数) (DeepFace) |
| `isOccluded` | 遮蔽物検出フラグ (expressionScore < 0.4 で true) (DeepFace) |
| `face_embedding` | 特徴量ベクトル (DeepFace) |
