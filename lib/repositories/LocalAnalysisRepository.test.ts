import { describe, it, expect, vi, beforeEach } from "vitest";
import path from "path";
import { LocalAnalysisRepository } from "./LocalAnalysisRepository";

// fs/promises をモック化
vi.mock("fs/promises");
import * as fs from "fs/promises";

const DATA_ROOT = "/test/data";
const IMAGES_ROOT = "/test/images";

describe("LocalAnalysisRepository", () => {
  let repo: LocalAnalysisRepository;

  beforeEach(() => {
    repo = new LocalAnalysisRepository(DATA_ROOT, IMAGES_ROOT);
    vi.clearAllMocks();
  });

  // ─── getActors ───────────────────────────────────────────────
  describe("getActors", () => {
    it("*_analysis.json ファイルから被写体IDリストを返す", async () => {
      // Arrange
      vi.mocked(fs.readdir).mockResolvedValue([
        "actor_a_analysis.json",
        "actor_b_analysis.json",
        "other.txt",
      ] as unknown as Awaited<ReturnType<typeof fs.readdir>>);

      // Act
      const result = await repo.getActors();

      // Assert
      expect(fs.readdir).toHaveBeenCalledTimes(1);
      expect(fs.readdir).toHaveBeenCalledWith(DATA_ROOT);
      expect(result).toEqual(["actor_a", "actor_b"]);
    });

    it("analysis.json ファイルが存在しない場合は空配列を返す", async () => {
      // Arrange
      vi.mocked(fs.readdir).mockResolvedValue(
        [] as unknown as Awaited<ReturnType<typeof fs.readdir>>
      );

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
      const photos = [
        { filename: "a.jpg", score: 0.3, shootingDate: "2026-01-01", selectionState: "pending", selectedAt: null },
        { filename: "b.jpg", score: 0.8, shootingDate: "2026-01-01", selectionState: "pending", selectedAt: null },
        { filename: "c.jpg", score: 0.5, shootingDate: "2026-01-01", selectionState: "pending", selectedAt: null },
      ];
      vi.mocked(fs.readFile).mockResolvedValue(
        JSON.stringify(photos) as unknown as Buffer
      );

      // Act
      const result = await repo.getPhotos("actor_a");

      // Assert
      expect(fs.readFile).toHaveBeenCalledTimes(1);
      expect(fs.readFile).toHaveBeenCalledWith(
        path.join(DATA_ROOT, "actor_a_analysis.json"),
        "utf-8"
      );
      expect(result[0].filename).toBe("b.jpg");
      expect(result[1].filename).toBe("c.jpg");
      expect(result[2].filename).toBe("a.jpg");
    });

    it("score が null の写真は 0 として扱いソートする", async () => {
      // Arrange
      const photos = [
        { filename: "a.jpg", score: null, shootingDate: "2026-01-01", selectionState: "pending", selectedAt: null },
        { filename: "b.jpg", score: 0.5, shootingDate: "2026-01-01", selectionState: "pending", selectedAt: null },
      ];
      vi.mocked(fs.readFile).mockResolvedValue(
        JSON.stringify(photos) as unknown as Buffer
      );

      // Act
      const result = await repo.getPhotos("actor_a");

      // Assert
      expect(result[0].filename).toBe("b.jpg");
      expect(result[1].filename).toBe("a.jpg");
    });
  });

  // ─── saveSelectionState ──────────────────────────────────────
  describe("saveSelectionState", () => {
    it("一致する写真の selectionState と selectedAt を更新して保存する", async () => {
      // Arrange
      const photos = [
        { filename: "a.jpg", score: 0.5, shootingDate: "2026-01-01", selectionState: "pending", selectedAt: null },
        { filename: "b.jpg", score: 0.3, shootingDate: "2026-01-01", selectionState: "pending", selectedAt: null },
      ];
      vi.mocked(fs.readFile).mockResolvedValue(
        JSON.stringify(photos) as unknown as Buffer
      );
      vi.mocked(fs.writeFile).mockResolvedValue(undefined);

      // Act
      await repo.saveSelectionState("actor_a", "a.jpg", "2026-01-01", "ok");

      // Assert
      expect(fs.readFile).toHaveBeenCalledTimes(1);
      expect(fs.readFile).toHaveBeenCalledWith(
        path.join(DATA_ROOT, "actor_a_analysis.json"),
        "utf-8"
      );
      expect(fs.writeFile).toHaveBeenCalledTimes(1);
      expect(fs.writeFile).toHaveBeenCalledWith(
        path.join(DATA_ROOT, "actor_a_analysis.json"),
        expect.any(String),
        "utf-8"
      );

      const written = JSON.parse(
        vi.mocked(fs.writeFile).mock.calls[0][1] as string
      );
      expect(written[0].selectionState).toBe("ok");
      expect(written[0].selectedAt).toBeTruthy();
      // 対象外の写真は変更されない
      expect(written[1].selectionState).toBe("pending");
    });

    it("filename が一致しても shootingDate が異なる場合は更新しない", async () => {
      // Arrange
      const photos = [
        { filename: "a.jpg", score: 0.5, shootingDate: "2026-01-01", selectionState: "pending", selectedAt: null },
      ];
      vi.mocked(fs.readFile).mockResolvedValue(
        JSON.stringify(photos) as unknown as Buffer
      );
      vi.mocked(fs.writeFile).mockResolvedValue(undefined);

      // Act
      await repo.saveSelectionState("actor_a", "a.jpg", "2026-12-31", "ng");

      // Assert
      const written = JSON.parse(
        vi.mocked(fs.writeFile).mock.calls[0][1] as string
      );
      expect(written[0].selectionState).toBe("pending");
    });

    it("一致する写真が存在しない場合でも writeFile を呼ぶ（変更なし）", async () => {
      // Arrange
      vi.mocked(fs.readFile).mockResolvedValue(
        "[]" as unknown as Buffer
      );
      vi.mocked(fs.writeFile).mockResolvedValue(undefined);

      // Act
      await repo.saveSelectionState("actor_a", "notexist.jpg", "2026-01-01", "ok");

      // Assert
      expect(fs.writeFile).toHaveBeenCalledTimes(1);
    });
  });

  // ─── readImageFile ───────────────────────────────────────────
  describe("readImageFile", () => {
    it("imagesRoot 配下のファイルを正常に読み込む", async () => {
      // Arrange
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
      // Arrange & Act & Assert
      await expect(
        repo.readImageFile("actor_a", "../../etc/passwd")
      ).rejects.toThrow("Invalid file path");
      expect(fs.readFile).not.toHaveBeenCalled();
    });

    it("パストラバーサル（actor に ../）を検出してエラーを投げる", async () => {
      // Arrange & Act & Assert
      await expect(
        repo.readImageFile("../../evil", "file.jpg")
      ).rejects.toThrow("Invalid file path");
      expect(fs.readFile).not.toHaveBeenCalled();
    });
  });
});
