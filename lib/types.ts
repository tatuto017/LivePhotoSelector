/**
 * 選別状態の型
 * - "ok": 選別済み（OK）
 * - "ng": 選別済み（NG）
 * - "pending": 未選別
 */
export type SelectionState = "ok" | "ng" | "pending";

/**
 * 結果表示ページの1行データ
 * sorting_state を actor_id・日付・selection_state でグループ集計した結果
 */
export interface ResultViewRow {
  /** 件数 */
  count: number;
  /** 被写体ID */
  actorId: string;
  /** 選別日（YYYY/MM/DD） */
  date: string;
  /** 選別状態 */
  selectionState: string;
}

/**
 * 写真データの型
 * sorting_state テーブルの各レコードに対応する
 */
export interface Photo {
  /** 画像ファイル名 */
  filename: string;
  /** 撮影日（EXIF DateTimeOriginal）YYYY-MM-DD */
  shootingDate: string;
  /** スコア（0〜1、スコアリング前は null） */
  score: number | null;
  /** 選別状態 */
  selectionState: SelectionState;
  /** 選別確定日時（ISO 8601、未選別の場合は null） */
  selectedAt: string | null;
}
