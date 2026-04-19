import path from "path";
import * as fs from "fs/promises";
import { eq, and, desc, sql } from "drizzle-orm";
import type { DrizzleDB } from "@/lib/db";
import { sortingState } from "@/lib/schema";
import { Photo, SelectionState } from "@/lib/types";

/**
 * Drizzle ORM を使用して sorting_state テーブルから選別データを読み書きし、
 * ローカル FS から画像ファイルを配信するリポジトリ
 */
export class LocalAnalysisRepository {
  private db: DrizzleDB;
  private imagesRoot: string;

  /**
   * @param db Drizzle ORM インスタンス
   * @param imagesRoot 画像ファイルのルートディレクトリ
   */
  constructor(db: DrizzleDB, imagesRoot: string) {
    this.db = db;
    this.imagesRoot = imagesRoot;
  }

  /**
   * sorting_state テーブルから被写体IDリストを取得する
   * public = TRUE の写真が 1 枚以上ある被写体のみを返す
   */
  async getActors(): Promise<string[]> {
    const rows = await this.db
      .selectDistinct({ actor_id: sortingState.actor_id })
      .from(sortingState)
      .where(eq(sortingState.public, true))
      .orderBy(sortingState.actor_id);
    return rows.map((r) => r.actor_id);
  }

  /**
   * 被写体の写真一覧をスコア降順で取得する
   * スコアが NULL の場合は 0 として扱う
   */
  async getPhotos(actor: string): Promise<Photo[]> {
    const rows = await this.db
      .select({
        filename: sortingState.filename,
        shooting_date: sortingState.shooting_date,
        score: sortingState.score,
        selection_state: sortingState.selection_state,
        selected_at: sortingState.selected_at,
      })
      .from(sortingState)
      .where(eq(sortingState.actor_id, actor))
      .orderBy(desc(sql`COALESCE(${sortingState.score}, 0)`));
    return rows.map((row) => this._mapRowToPhoto(row));
  }

  /**
   * 被写体の写真の選別状態を更新する
   * filename・shooting_date・actor_id が一致するレコードのみ更新する
   */
  async saveSelectionState(
    actor: string,
    filename: string,
    shootingDate: string,
    state: SelectionState
  ): Promise<void> {
    await this.db
      .update(sortingState)
      .set({ selection_state: state, selected_at: sql`NOW()` })
      .where(
        and(
          eq(sortingState.actor_id, actor),
          eq(sortingState.filename, filename),
          sql`${sortingState.shooting_date} = ${shootingDate}`
        )
      );
  }

  /**
   * pending 写真をスコア降順でページネーション取得する
   * @param actor 被写体ID
   * @param offset 開始インデックス
   * @param limit 取得枚数
   */
  async getPendingPhotosPage(
    actor: string,
    offset: number,
    limit: number
  ): Promise<{ photos: Photo[]; hasMore: boolean }> {
    // hasMore 判定のために limit+1 件取得する
    const rows = await this.db
      .select({
        filename: sortingState.filename,
        shooting_date: sortingState.shooting_date,
        score: sortingState.score,
        selection_state: sortingState.selection_state,
        selected_at: sortingState.selected_at,
      })
      .from(sortingState)
      .where(
        and(
          eq(sortingState.actor_id, actor),
          eq(sortingState.selection_state, "pending"),
          eq(sortingState.public, true)
        )
      )
      .orderBy(desc(sql`COALESCE(${sortingState.score}, 0)`))
      .limit(limit + 1)
      .offset(offset);

    const hasMore = rows.length > limit;
    const photos = rows.slice(0, limit).map((row) => this._mapRowToPhoto(row));
    return { photos, hasMore };
  }

  /**
   * パストラバーサル対策付きで画像ファイルを読み込む
   * 解決したパスが imagesRoot 配下であることを検証してから読み込む
   */
  async readImageFile(actor: string, filename: string): Promise<Buffer> {
    const imagesRootResolved = path.resolve(this.imagesRoot);
    const imagePath = path.resolve(this.imagesRoot, actor, filename);
    // パストラバーサル対策: 解決パスが imagesRoot 配下であることを確認
    if (!imagePath.startsWith(imagesRootResolved + path.sep)) {
      throw new Error("Invalid file path");
    }
    return fs.readFile(imagePath);
  }

  /**
   * DB の行データを Photo 型にマッピングする
   * shooting_date・selected_at は Date オブジェクトの場合も文字列に変換する
   */
  private _mapRowToPhoto(row: {
    filename: string;
    shooting_date: string | Date | null;
    score: string | null;
    selection_state: string;
    selected_at: Date | string | null;
  }): Photo {
    const shootingDate =
      row.shooting_date instanceof Date
        ? row.shooting_date.toISOString().split("T")[0]
        : String(row.shooting_date);

    const selectedAt =
      row.selected_at instanceof Date
        ? row.selected_at.toISOString()
        : row.selected_at != null
        ? String(row.selected_at)
        : null;

    return {
      filename: row.filename,
      shootingDate,
      score: row.score != null ? Number(row.score) : null,
      selectionState: row.selection_state as SelectionState,
      selectedAt,
    };
  }
}
