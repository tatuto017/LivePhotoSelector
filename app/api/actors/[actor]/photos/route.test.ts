import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

// lib/db と LocalAnalysisRepository をモック化
vi.mock("@/lib/db", () => ({
  createPool: vi.fn().mockReturnValue({}),
  createDb: vi.fn().mockReturnValue({}),
}));
vi.mock("@/lib/repositories/LocalAnalysisRepository");
import { LocalAnalysisRepository } from "@/lib/repositories/LocalAnalysisRepository";

import { GET } from "./route";

describe("GET /api/actors/[actor]/photos", () => {
  let mockGetPendingPhotosPage: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockGetPendingPhotosPage = vi.fn().mockResolvedValue({
      photos: [],
      hasMore: false,
    });
    vi.mocked(LocalAnalysisRepository).mockImplementation(
      () =>
        ({
          getActors: vi.fn(),
          getPhotos: vi.fn(),
          getPendingPhotosPage: mockGetPendingPhotosPage,
          saveSelectionState: vi.fn(),
          readImageFile: vi.fn(),
        }) as unknown as LocalAnalysisRepository
    );
    vi.stubEnv("PROJECT_ROOT", "/test/project");
  });

  it("offset=0 &limit=6 で getPendingPhotosPage を呼び出す", async () => {
    // Arrange
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/photos?offset=0&limit=6"
    );

    // Act
    await GET(request, {
      params: Promise.resolve({ actor: "actor_a" }),
    });

    // Assert
    expect(mockGetPendingPhotosPage).toHaveBeenCalledTimes(1);
    expect(mockGetPendingPhotosPage).toHaveBeenCalledWith("actor_a", 0, 6);
  });

  it("offset と limit をクエリパラメータから正しく取得する", async () => {
    // Arrange
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/photos?offset=12&limit=3"
    );

    // Act
    await GET(request, {
      params: Promise.resolve({ actor: "actor_a" }),
    });

    // Assert
    expect(mockGetPendingPhotosPage).toHaveBeenCalledWith("actor_a", 12, 3);
  });

  it("クエリパラメータ省略時は offset=0, limit=6 をデフォルトとする", async () => {
    // Arrange
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/photos"
    );

    // Act
    await GET(request, {
      params: Promise.resolve({ actor: "actor_a" }),
    });

    // Assert
    expect(mockGetPendingPhotosPage).toHaveBeenCalledWith("actor_a", 0, 6);
  });

  it("photos と hasMore を JSON で返す", async () => {
    // Arrange
    const photos = [
      { filename: "a.jpg", score: 0.8, shootingDate: "2026-01-01", selectionState: "pending", selectedAt: null },
    ];
    mockGetPendingPhotosPage.mockResolvedValue({ photos, hasMore: true });
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/photos?offset=0&limit=6"
    );

    // Act
    const response = await GET(request, {
      params: Promise.resolve({ actor: "actor_a" }),
    });
    const body = await response.json();

    // Assert
    expect(response.status).toBe(200);
    expect(body).toEqual({ photos, hasMore: true });
  });

  it("LocalAnalysisRepository を正しいパスで初期化する", async () => {
    // Arrange
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/photos?offset=0&limit=6"
    );

    // Act
    await GET(request, {
      params: Promise.resolve({ actor: "actor_a" }),
    });

    // Assert
    expect(LocalAnalysisRepository).toHaveBeenCalledWith(
      expect.anything(),
      "/test/project/data/images"
    );
  });
});
