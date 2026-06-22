import { describe, it, expect, vi, beforeEach } from "vitest";
import type { DrizzleDB } from "@/lib/db";

// drizzle-orm の ne をスパイ化して引数検証できるようにする
vi.mock("drizzle-orm", async (importOriginal) => {
  const original = await importOriginal<typeof import("drizzle-orm")>();
  return { ...original, ne: vi.fn(original.ne) };
});
import { ne } from "drizzle-orm";

import { ResultViewRepository } from "./ResultViewRepository";

/** Drizzle select チェーン（select→from→where→groupBy→orderBy→limit）のモック */
function makeSelectChain(rows: unknown[]) {
  const resolved = Promise.resolve(rows);
  const limit = vi.fn().mockReturnValue(resolved);
  const orderBy = vi.fn().mockReturnValue({ limit });
  const groupBy = vi.fn().mockReturnValue({ orderBy });
  const where = vi.fn().mockReturnValue({ groupBy });
  const from = vi.fn().mockReturnValue({ where });
  const select = vi.fn().mockReturnValue({ from });
  return { select, from, where, groupBy, orderBy, limit };
}

/** テスト用 mock DrizzleDB を生成する */
function makeMockDb(rows: unknown[] = []) {
  const chain = makeSelectChain(rows);
  const mockDb = {
    select: chain.select,
  } as unknown as DrizzleDB;
  return { mockDb, chain };
}

describe("ResultViewRepository", () => {
  let repo: ResultViewRepository;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("getResults", () => {
    it("db.select を1回呼び出す", async () => {
      // Arrange
      const { mockDb, chain } = makeMockDb([]);
      repo = new ResultViewRepository(mockDb);

      // Act
      await repo.getResults();

      // Assert
      expect(chain.select).toHaveBeenCalledTimes(1);
    });

    it("selection_state が pending 以外のレコードを取得する", async () => {
      // Arrange
      const { mockDb, chain } = makeMockDb([]);
      repo = new ResultViewRepository(mockDb);

      // Act
      await repo.getResults();

      // Assert — ne() が selection_state と "pending" で呼ばれること
      expect(chain.where).toHaveBeenCalledTimes(1);
      expect(ne).toHaveBeenCalledWith(
        expect.objectContaining({ name: "selection_state" }),
        "pending"
      );
    });

    it("limit(20) を呼び出す", async () => {
      // Arrange
      const { mockDb, chain } = makeMockDb([]);
      repo = new ResultViewRepository(mockDb);

      // Act
      await repo.getResults();

      // Assert
      expect(chain.limit).toHaveBeenCalledTimes(1);
      expect(chain.limit).toHaveBeenCalledWith(20);
    });

    it("結果を ResultViewRow 配列にマッピングして返す", async () => {
      // Arrange
      const rawRows = [
        { count: 5, actorId: "actor_a", date: "2026/06/22", selectionState: "ok" },
        { count: 3, actorId: "actor_b", date: "2026/06/21", selectionState: "ng" },
      ];
      const { mockDb } = makeMockDb(rawRows);
      repo = new ResultViewRepository(mockDb);

      // Act
      const results = await repo.getResults();

      // Assert
      expect(results).toHaveLength(2);
      expect(results[0]).toEqual({
        count: 5,
        actorId: "actor_a",
        date: "2026/06/22",
        selectionState: "ok",
      });
      expect(results[1]).toEqual({
        count: 3,
        actorId: "actor_b",
        date: "2026/06/21",
        selectionState: "ng",
      });
    });

    it("結果が0件の場合は空配列を返す", async () => {
      // Arrange
      const { mockDb } = makeMockDb([]);
      repo = new ResultViewRepository(mockDb);

      // Act
      const results = await repo.getResults();

      // Assert
      expect(results).toEqual([]);
    });

    it("groupBy を呼び出す", async () => {
      // Arrange
      const { mockDb, chain } = makeMockDb([]);
      repo = new ResultViewRepository(mockDb);

      // Act
      await repo.getResults();

      // Assert
      expect(chain.groupBy).toHaveBeenCalledTimes(1);
    });

    it("orderBy を呼び出す", async () => {
      // Arrange
      const { mockDb, chain } = makeMockDb([]);
      repo = new ResultViewRepository(mockDb);

      // Act
      await repo.getResults();

      // Assert
      expect(chain.orderBy).toHaveBeenCalledTimes(1);
    });
  });
});
