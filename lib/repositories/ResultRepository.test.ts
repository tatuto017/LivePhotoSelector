import { describe, it, expect } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/src/mocks/server";
import { ResultRepository } from "./ResultRepository";

describe("ResultRepository", () => {
  const repo = new ResultRepository();

  // ─── save ────────────────────────────────────────────────────
  describe("save", () => {
    it("正しい URL に PATCH リクエストを送信する", async () => {
      // Arrange
      let capturedUrl: string | undefined;
      let capturedBody: unknown;
      server.use(
        http.patch(
          "/api/actors/actor_a/photos/img001.jpg",
          async ({ request }) => {
            capturedUrl = request.url;
            capturedBody = await request.json();
            return HttpResponse.json({ ok: true });
          }
        )
      );

      // Act
      await repo.save("actor_a", "img001.jpg", "2026-01-01", "ok");

      // Assert
      expect(capturedUrl).toContain(
        "/api/actors/actor_a/photos/img001.jpg"
      );
      expect(capturedBody).toEqual({
        shootingDate: "2026-01-01",
        selectionState: "ok",
      });
    });

    it("ファイル名に特殊文字が含まれる場合は URL エンコードする", async () => {
      // Arrange
      let capturedUrl: string | undefined;
      server.use(
        http.patch(
          "/api/actors/actor_a/photos/img%2001.jpg",
          async ({ request }) => {
            capturedUrl = request.url;
            return HttpResponse.json({ ok: true });
          }
        )
      );

      // Act
      await repo.save("actor_a", "img 01.jpg", "2026-01-01", "ng");

      // Assert
      expect(capturedUrl).toContain("img%2001.jpg");
    });

    it("API が非 2xx を返した場合はエラーを投げる", async () => {
      // Arrange
      server.use(
        http.patch("/api/actors/actor_a/photos/img001.jpg", () =>
          HttpResponse.json({ error: "server error" }, { status: 500 })
        )
      );

      // Act & Assert
      await expect(
        repo.save("actor_a", "img001.jpg", "2026-01-01", "ok")
      ).rejects.toThrow("Failed to save: 500");
    });

    it("ng 状態を正しく送信する", async () => {
      // Arrange
      let capturedBody: unknown;
      server.use(
        http.patch("/api/actors/actor_a/photos/img002.jpg", async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ ok: true });
        })
      );

      // Act
      await repo.save("actor_a", "img002.jpg", "2026-02-01", "ng");

      // Assert
      expect(capturedBody).toEqual({
        shootingDate: "2026-02-01",
        selectionState: "ng",
      });
    });
  });
});
