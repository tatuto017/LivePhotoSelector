import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

// LocalAnalysisRepository をモック化
vi.mock("@/lib/repositories/LocalAnalysisRepository");
import { LocalAnalysisRepository } from "@/lib/repositories/LocalAnalysisRepository";

import { PATCH } from "./route";

describe("PATCH /api/actors/[actor]/photos/[filename]", () => {
  let mockSaveSelectionState: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockSaveSelectionState = vi.fn().mockResolvedValue(undefined);
    vi.mocked(LocalAnalysisRepository).mockImplementation(
      () =>
        ({
          getActors: vi.fn(),
          getPhotos: vi.fn(),
          saveSelectionState: mockSaveSelectionState,
          readImageFile: vi.fn(),
        }) as unknown as LocalAnalysisRepository
    );
    vi.stubEnv("ONE_DRIVE_ROOT", "/test/onedrive");
  });

  it("選別状態を保存して { ok: true } を返す", async () => {
    // Arrange
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/photos/img001.jpg",
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shootingDate: "2026-01-01",
          selectionState: "ok",
        }),
      }
    );

    // Act
    const response = await PATCH(request, {
      params: Promise.resolve({ actor: "actor_a", filename: "img001.jpg" }),
    });
    const body = await response.json();

    // Assert
    expect(response.status).toBe(200);
    expect(body).toEqual({ ok: true });
    expect(mockSaveSelectionState).toHaveBeenCalledTimes(1);
    expect(mockSaveSelectionState).toHaveBeenCalledWith(
      "actor_a",
      "img001.jpg",
      "2026-01-01",
      "ok"
    );
  });

  it("ng 状態を正しく保存する", async () => {
    // Arrange
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/photos/img002.jpg",
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shootingDate: "2026-02-01",
          selectionState: "ng",
        }),
      }
    );

    // Act
    await PATCH(request, {
      params: Promise.resolve({ actor: "actor_a", filename: "img002.jpg" }),
    });

    // Assert
    expect(mockSaveSelectionState).toHaveBeenCalledWith(
      "actor_a",
      "img002.jpg",
      "2026-02-01",
      "ng"
    );
  });

  it("URL エンコードされたファイル名をデコードして保存する", async () => {
    // Arrange
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/photos/my%20photo.jpg",
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shootingDate: "2026-01-01",
          selectionState: "ok",
        }),
      }
    );

    // Act
    await PATCH(request, {
      params: Promise.resolve({ actor: "actor_a", filename: "my%20photo.jpg" }),
    });

    // Assert
    expect(mockSaveSelectionState).toHaveBeenCalledWith(
      "actor_a",
      "my photo.jpg", // デコード済み
      "2026-01-01",
      "ok"
    );
  });

  it("LocalAnalysisRepository を正しいパスで初期化する", async () => {
    // Arrange
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/photos/img001.jpg",
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shootingDate: "2026-01-01", selectionState: "ok" }),
      }
    );

    // Act
    await PATCH(request, {
      params: Promise.resolve({ actor: "actor_a", filename: "img001.jpg" }),
    });

    // Assert
    expect(LocalAnalysisRepository).toHaveBeenCalledWith(
      "/test/onedrive/data",
      "/test/onedrive/images"
    );
  });
});
