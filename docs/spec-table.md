# テーブル設計

## DB

MariaDB

## analysis_records

DeepFace 解析結果を格納するテーブル。マイグレーション: `migrations/001_create_analysis_records.sql`

| 論理名 | 物理名 | 型 | Null | Key | 初期値 | 説明 |
| --- | --- | --- | --- | --- | --- | --- |
| 被写体ID | actor | varchar(255) | NO | PRI | | |
| ファイル名 | filename | varchar(255) | NO | PRI | | |
| 撮影日 | shooting_date | date | NO | PRI | | EXIF DateTimeOriginal |
| 怒り | angry | float | NO | | 0 | DeepFace 感情スコア (0〜100) |
| 恐怖 | fear | float | NO | | 0 | DeepFace 感情スコア (0〜100) |
| 喜び | happy | float | NO | | 0 | DeepFace 感情スコア (0〜100) |
| 悲しみ | sad | float | NO | | 0 | DeepFace 感情スコア (0〜100) |
| 驚き | surprise | float | NO | | 0 | DeepFace 感情スコア (0〜100) |
| 嫌悪 | disgust | float | NO | | 0 | DeepFace 感情スコア (0〜100) |
| 無表情 | neutral | float | NO | | 0 | DeepFace 感情スコア (0〜100) |
| 顔のロール角 | face_angle | float | NO | | 0 | 両目座標から計算（度数） |
| 遮蔽物フラグ | is_occluded | tinyint(1) | NO | | 0 | expressionScore < 0.4 で 1 |
| Facenet埋め込みベクトル | face_embedding | json | NO | | | 128次元 float 配列 |
| 作成日時 | created_at | datetime | NO | | CURRENT_TIMESTAMP | |

- Python 側フィールド名との対応: `shootingDate` → `shooting_date`、`faceAngle` → `face_angle`、`isOccluded` → `is_occluded`、`face_embedding` → `face_embedding`（JSON 文字列）。

## sorting_state

| 論理名 | 物理名 | 型 | Null | Key | 初期値 |
| --- | --- | --- | --- | --- | --- |
| 被写体ID | actor_id | varchar(255) | NO | PRI | |
| ファイル名 | filename | varchar(255) | NO | PRI | |
| 撮影日 | shooting_date | date | NO | PRI | |
| スコア | score | decimal(5,4) | YES | | NULL |
| 選択状態 | selection_state | varchar(10) | NO | | pending |
| 学習済み | learned | boolean | NO | | false |
| 選択日 | selected_at | datetime | YES | | NULL |
| 公開 | public | boolean | NO | | false |

## データの更新タイミング

### analysis_records
| 論理名 | 付与タイミング | 説明 |
| --- | --- | --- |
| 全フィールド | `src.analysis.main` 実行時 | DeepFace 解析完了後に INSERT IGNORE |

### sorting_state
| 論理名 | 付与タイミング | 説明 |
| --- | --- | --- |
| 被写体ID | Python 解析時 | 被写体ID |
| ファイル名 | Python 解析時 | 画像ファイル名 |
| 撮影日 | Python 解析時 | 撮影日（EXIF DateTimeOriginal） |
| スコア | `src.scoring.main` 実行時 | 主要表情の信頼スコア（0〜1） |
| 選択状態 | Next.js 保存時 | 選択結果 / `"ok"` / `"ng"` / `pending` |
| 学習済み | Python スコアリング時 | 未学習 `false` / 学習済み `true` |
| 選択日 | Next.js 保存時 | 選択確定日時 |
| 公開 | `src.finalize.main` 実行時 | `ANALYZE_ROOT` から `DATA_ROOT` への全ファイル移動完了後に `true` へ更新 |
