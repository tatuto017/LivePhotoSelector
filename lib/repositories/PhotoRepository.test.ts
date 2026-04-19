import { describe, it, expect } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/src/mocks/server";
import { PhotoRepository } from "./PhotoRepository";
import { Photo } from "@/lib/types";

/** テスト用の写真データ */
const makePhoto = (filename: string): Photo => ({
  filename,
  shootingDate: "2026-01-01",
  score: 0.8,
  selectionState: "pending",
  selectedAt: null,
});

describe("PhotoRepository", () => {
  const repo = new PhotoRepository();

  // ─── fetchPending ────────────────────────────────────────────
  describe("fetchPending", () => {
    it("正しい URL に GET リクエストを送信する", async () => {
      // Arrange
      let capturedUrl: string | undefined;
      server.use(
        http.get("/api/actors/actor_a/photos", ({ request }) => {
          capturedUrl = request.url;
          return HttpResponse.json({ photos: [], hasMore: false });
        })
      );

      // Act
      await repo.fetchPending("actor_a", 0, 6);

      // Assert
      expect(capturedUrl).toContain("/api/actors/actor_a/photos");
      expect(capturedUrl).toContain("offset=0");
      expect(capturedUrl).toContain("limit=6");
    });

    it("offset と limit を正しくクエリパラメータに付与する", async () => {
      // Arrange
      let capturedUrl: string | undefined;
      server.use(
        http.get("/api/actors/actor_a/photos", ({ request }) => {
          capturedUrl = request.url;
          return HttpResponse.json({ photos: [], hasMore: false });
        })
      );

      // Act
      await repo.fetchPending("actor_a", 12, 6);

      // Assert
      expect(capturedUrl).toContain("offset=12");
      expect(capturedUrl).toContain("limit=6");
    });

    it("レスポンスの photos と hasMore を返す", async () => {
      // Arrange
      const photos = [makePhoto("a.jpg"), makePhoto("b.jpg")];
      server.use(
        http.get("/api/actors/actor_a/photos", () =>
          HttpResponse.json({ photos, hasMore: true })
        )
      );

      // Act
      const result = await repo.fetchPending("actor_a", 0, 6);

      // Assert
      expect(result.photos).toEqual(photos);
      expect(result.hasMore).toBe(true);
    });

    it("actor 名を URL エンコードする", async () => {
      // Arrange
      let capturedUrl: string | undefined;
      server.use(
        http.get("/api/actors/actor%20a/photos", ({ request }) => {
          capturedUrl = request.url;
          return HttpResponse.json({ photos: [], hasMore: false });
        })
      );

      // Act
      await repo.fetchPending("actor a", 0, 6);

      // Assert
      expect(capturedUrl).toContain("actor%20a");
    });

    it("API が非 2xx を返した場合はエラーを投げる", async () => {
      // Arrange
      server.use(
        http.get("/api/actors/actor_a/photos", () =>
          HttpResponse.json({ error: "server error" }, { status: 500 })
        )
      );

      // Act & Assert
      await expect(repo.fetchPending("actor_a", 0, 6)).rejects.toThrow(
        "Failed to fetch photos: 500"
      );
    });
  });
});
