import { describe, it, expect, vi, beforeEach } from "vitest";
import path from "path";
import type { DrizzleDB } from "@/lib/db";
import { LocalAnalysisRepository } from "./LocalAnalysisRepository";

// fs/promises をモック化
vi.mock("fs/promises");
import * as fs from "fs/promises";

const IMAGES_ROOT = "/test/images";

/** Drizzle クエリチェーンのモックを生成するヘルパー */
function makeSelectChain(rows: unknown[]) {
  const chain = {
    from: vi.fn(),
    where: vi.fn(),
    orderBy: vi.fn(),
    limit: vi.fn(),
    offset: vi.fn(),
  };
  // 各メソッドがチェーンを返し、最後の await でデータを解決する
  const resolveWith = (data: unknown[]) =>
    Object.assign(Promise.resolve(data), chain);

  chain.offset.mockImplementation(() => resolveWith(rows));
  chain.limit.mockImplementation(() => ({ ...chain, offset: chain.offset }));
  chain.orderBy.mockImplementation(() => ({
    ...chain,
    limit: chain.limit,
    // limit なしで await された場合（getPhotos / getActors）
    then: (resolve: (v: unknown[]) => void) =>
      Promise.resolve(rows).then(resolve),
    catch: (fn: (e: unknown) => void) => Promise.resolve(rows).catch(fn),
    finally: (fn: () => void) => Promise.resolve(rows).finally(fn),
  }));
  chain.where.mockImplementation(() => ({
    ...chain,
    orderBy: chain.orderBy,
    then: (resolve: (v: unknown[]) => void) =>
      Promise.resolve(rows).then(resolve),
    catch: (fn: (e: unknown) => void) => Promise.resolve(rows).catch(fn),
    finally: (fn: () => void) => Promise.resolve(rows).finally(fn),
  }));
  chain.from.mockImplementation(() => ({
    ...chain,
    where: chain.where,
    orderBy: chain.orderBy,
  }));
  return chain;
}

/** Drizzle update チェーンのモックを生成するヘルパー */
function makeUpdateChain() {
  const whereResult = Promise.resolve(undefined);
  const where = vi.fn().mockReturnValue(whereResult);
  const set = vi.fn().mockReturnValue({ where });
  const update = vi.fn().mockReturnValue({ set });
  return { update, set, where };
}

/** テスト用 mock DrizzleDB を生成する */
function makeMockDb(
  selectRows: unknown[] = [],
  updateChain = makeUpdateChain()
) {
  const chain = makeSelectChain(selectRows);
  const mockDb = {
    select: vi.fn().mockReturnValue(chain),
    selectDistinct: vi.fn().mockReturnValue(chain),
    update: updateChain.update,
  } as unknown as DrizzleDB;
  return { mockDb, selectChain: chain, updateChain };
}

describe("LocalAnalysisRepository", () => {
  let repo: LocalAnalysisRepository;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ─── getActors ───────────────────────────────────────────────
  describe("getActors", () => {
    it("被写体IDリストを返す", async () => {
      // Arrange
      const { mockDb } = makeMockDb([
        { actor_id: "actor_a" },
        { actor_id: "actor_b" },
      ]);
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      const result = await repo.getActors();

      // Assert
      expect(mockDb.selectDistinct).toHaveBeenCalledTimes(1);
      expect(result).toEqual(["actor_a", "actor_b"]);
    });

    it("レコードが存在しない場合は空配列を返す", async () => {
      // Arrange
      const { mockDb } = makeMockDb([]);
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      const result = await repo.getActors();

      // Assert
      expect(result).toEqual([]);
    });
  });

  // ─── getPhotos ───────────────────────────────────────────────
  describe("getPhotos", () => {
    it("写真リストをスコア降順で返す", async () => {
      // Arrange
      const { mockDb } = makeMockDb([
        {
          filename: "a.jpg",
          shooting_date: "2026-01-01",
          score: "0.3000",
          selection_state: "pending",
          selected_at: null,
        },
        {
          filename: "b.jpg",
          shooting_date: "2026-01-01",
          score: "0.8000",
          selection_state: "pending",
          selected_at: null,
        },
      ]);
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      const result = await repo.getPhotos("actor_a");

      // Assert
      expect(mockDb.select).toHaveBeenCalledTimes(1);
      expect(result[0].filename).toBe("a.jpg");
      expect(result[1].filename).toBe("b.jpg");
    });

    it("shooting_date が Date オブジェクトの場合 YYYY-MM-DD 文字列に変換する", async () => {
      // Arrange
      const date = new Date("2026-01-15T00:00:00.000Z");
      const { mockDb } = makeMockDb([
        {
          filename: "a.jpg",
          shooting_date: date,
          score: "0.5000",
          selection_state: "pending",
          selected_at: null,
        },
      ]);
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      const result = await repo.getPhotos("actor_a");

      // Assert
      expect(result[0].shootingDate).toBe("2026-01-15");
    });

    it("selected_at が Date オブジェクトの場合 ISO 文字列に変換する", async () => {
      // Arrange
      const date = new Date("2026-01-15T12:30:00.000Z");
      const { mockDb } = makeMockDb([
        {
          filename: "a.jpg",
          shooting_date: "2026-01-15",
          score: "0.5000",
          selection_state: "ok",
          selected_at: date,
        },
      ]);
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      const result = await repo.getPhotos("actor_a");

      // Assert
      expect(result[0].selectedAt).toBe("2026-01-15T12:30:00.000Z");
    });

    it("selected_at が文字列の場合そのまま返す", async () => {
      // Arrange
      const { mockDb } = makeMockDb([
        {
          filename: "a.jpg",
          shooting_date: "2026-01-15",
          score: "0.5000",
          selection_state: "ok",
          selected_at: "2026-01-15T12:00:00.000Z",
        },
      ]);
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      const result = await repo.getPhotos("actor_a");

      // Assert
      expect(result[0].selectedAt).toBe("2026-01-15T12:00:00.000Z");
    });

    it("selected_at が null の場合 null を返す", async () => {
      // Arrange
      const { mockDb } = makeMockDb([
        {
          filename: "a.jpg",
          shooting_date: "2026-01-01",
          score: null,
          selection_state: "pending",
          selected_at: null,
        },
      ]);
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      const result = await repo.getPhotos("actor_a");

      // Assert
      expect(result[0].selectedAt).toBeNull();
      expect(result[0].score).toBeNull();
    });
  });

  // ─── saveSelectionState ──────────────────────────────────────
  describe("saveSelectionState", () => {
    it("update を 1 回呼び出す", async () => {
      // Arrange
      const { mockDb, updateChain } = makeMockDb();
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      await repo.saveSelectionState("actor_a", "a.jpg", "2026-01-01", "ok");

      // Assert
      expect(updateChain.update).toHaveBeenCalledTimes(1);
      expect(updateChain.set).toHaveBeenCalledTimes(1);
      expect(updateChain.where).toHaveBeenCalledTimes(1);
    });

    it("ng 状態でも update を呼び出す", async () => {
      // Arrange
      const { mockDb, updateChain } = makeMockDb();
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      await repo.saveSelectionState("actor_b", "b.jpg", "2026-02-01", "ng");

      // Assert
      expect(updateChain.update).toHaveBeenCalledTimes(1);
    });

    it("一致するレコードが存在しない場合も update を呼び出す（影響行数 0）", async () => {
      // Arrange
      const { mockDb, updateChain } = makeMockDb();
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      await repo.saveSelectionState(
        "actor_a",
        "notexist.jpg",
        "2026-01-01",
        "ok"
      );

      // Assert
      expect(updateChain.update).toHaveBeenCalledTimes(1);
    });
  });

  // ─── getPendingPhotosPage ────────────────────────────────────
  describe("getPendingPhotosPage", () => {
    it("pending 写真をスコア降順でページネーション取得する", async () => {
      // Arrange（limit=2 なので limit+1=3 件要求、3件返ってきたら hasMore=true）
      const { mockDb } = makeMockDb([
        {
          filename: "b.jpg",
          shooting_date: "2026-01-01",
          score: "0.8000",
          selection_state: "pending",
          selected_at: null,
        },
        {
          filename: "d.jpg",
          shooting_date: "2026-01-01",
          score: "0.6000",
          selection_state: "pending",
          selected_at: null,
        },
        {
          filename: "c.jpg",
          shooting_date: "2026-01-01",
          score: "0.5000",
          selection_state: "pending",
          selected_at: null,
        },
      ]);
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      const result = await repo.getPendingPhotosPage("actor_a", 0, 2);

      // Assert
      expect(mockDb.select).toHaveBeenCalledTimes(1);
      expect(result.photos).toHaveLength(2);
      expect(result.photos[0].filename).toBe("b.jpg");
      expect(result.photos[1].filename).toBe("d.jpg");
      expect(result.hasMore).toBe(true);
    });

    it("最終ページで hasMore が false になる", async () => {
      // Arrange（limit=2 なので limit+1=3 件要求、2件しか返らない → hasMore=false）
      const { mockDb } = makeMockDb([
        {
          filename: "a.jpg",
          shooting_date: "2026-01-01",
          score: "0.8000",
          selection_state: "pending",
          selected_at: null,
        },
        {
          filename: "b.jpg",
          shooting_date: "2026-01-01",
          score: "0.5000",
          selection_state: "pending",
          selected_at: null,
        },
      ]);
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      const result = await repo.getPendingPhotosPage("actor_a", 0, 2);

      // Assert
      expect(result.photos).toHaveLength(2);
      expect(result.hasMore).toBe(false);
    });

    it("offset を適用して limit と offset で呼び出す", async () => {
      // Arrange
      const { mockDb, selectChain } = makeMockDb([]);
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      await repo.getPendingPhotosPage("actor_a", 6, 3);

      // Assert
      expect(selectChain.limit).toHaveBeenCalledWith(4); // limit+1
      expect(selectChain.offset).toHaveBeenCalledWith(6);
    });

    it("pending 写真が 0 枚の場合は空配列と hasMore: false を返す", async () => {
      // Arrange
      const { mockDb } = makeMockDb([]);
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act
      const result = await repo.getPendingPhotosPage("actor_a", 0, 6);

      // Assert
      expect(result.photos).toHaveLength(0);
      expect(result.hasMore).toBe(false);
    });
  });

  // ─── readImageFile ───────────────────────────────────────────
  describe("readImageFile", () => {
    it("imagesRoot 配下のファイルを正常に読み込む", async () => {
      // Arrange
      const { mockDb } = makeMockDb();
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);
      const fakeBuffer = Buffer.from("fake image");
      vi.mocked(fs.readFile).mockResolvedValue(
        fakeBuffer as unknown as Buffer
      );

      // Act
      const result = await repo.readImageFile("actor_a", "test.jpg");

      // Assert
      const expectedPath = path.resolve(IMAGES_ROOT, "actor_a", "test.jpg");
      expect(fs.readFile).toHaveBeenCalledTimes(1);
      expect(fs.readFile).toHaveBeenCalledWith(expectedPath);
      expect(result).toBe(fakeBuffer);
    });

    it("パストラバーサル（filename に ../）を検出してエラーを投げる", async () => {
      // Arrange
      const { mockDb } = makeMockDb();
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act & Assert
      await expect(
        repo.readImageFile("actor_a", "../../etc/passwd")
      ).rejects.toThrow("Invalid file path");
      expect(fs.readFile).not.toHaveBeenCalled();
    });

    it("パストラバーサル（actor に ../）を検出してエラーを投げる", async () => {
      // Arrange
      const { mockDb } = makeMockDb();
      repo = new LocalAnalysisRepository(mockDb, IMAGES_ROOT);

      // Act & Assert
      await expect(
        repo.readImageFile("../../evil", "file.jpg")
      ).rejects.toThrow("Invalid file path");
      expect(fs.readFile).not.toHaveBeenCalled();
    });
  });
});
