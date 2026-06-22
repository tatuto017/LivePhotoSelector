# 結果表示仕様

## エンドポイント
```
GET /result_view
```

## 表示仕様
20行分のみ。テーブルで表示する。

## 結果取得仕様

Drizzle ORM（`lib/repositories/ResultViewRepository.ts`）で実装する。

```typescript
import { sql } from "drizzle-orm";
import { ne, desc } from "drizzle-orm";
import { sortingState } from "@/lib/schema";

const results = await db
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
```
