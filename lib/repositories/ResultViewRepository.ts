import { sql, ne, desc } from "drizzle-orm";
import type { DrizzleDB } from "@/lib/db";
import { sortingState } from "@/lib/schema";
import { ResultViewRow } from "@/lib/types";

/**
 * sorting_state テーブルの集計結果を取得するリポジトリ
 * actor_id・日付・selection_state でグループ化し、上位 20 件を返す
 */
export class ResultViewRepository {
  private db: DrizzleDB;

  /**
   * @param db Drizzle ORM インスタンス
   */
  constructor(db: DrizzleDB) {
    this.db = db;
  }

  /**
   * pending 以外の選別結果を集計して取得する
   * 選別日の降順で最大 20 件返す
   */
  async getResults(): Promise<ResultViewRow[]> {
    const rows = await this.db
      .select({
        count: sql<number>`count(*)`,
        actorId: sortingState.actor_id,
        date: sql<string>`DATE_FORMAT(${sortingState.selected_at}, '%Y/%m/%d')`,
        selectionState: sortingState.selection_state,
      })
      .from(sortingState)
      .where(ne(sortingState.selection_state, "pending"))
      .groupBy(
        sortingState.actor_id,
        sql`DATE_FORMAT(${sortingState.selected_at}, '%Y/%m/%d')`,
        sortingState.selection_state
      )
      .orderBy(desc(sql`DATE_FORMAT(${sortingState.selected_at}, '%Y/%m/%d')`))
      .limit(20);

    return rows as ResultViewRow[];
  }
}
