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

describe("GET /api/actors/[actor]/images/[filename]", () => {
  let mockReadImageFile: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockReadImageFile = vi.fn();
    vi.mocked(LocalAnalysisRepository).mockImplementation(
      () =>
        ({
          getActors: vi.fn(),
          getPhotos: vi.fn(),
          saveSelectionState: vi.fn(),
          readImageFile: mockReadImageFile,
        }) as unknown as LocalAnalysisRepository
    );
    vi.stubEnv("PROJECT_ROOT", "/test/project");
  });

  it("JPEG 画像を image/jpeg Content-Type で返す", async () => {
    // Arrange
    const fakeBuffer = Buffer.from("fake jpeg data");
    mockReadImageFile.mockResolvedValue(fakeBuffer);
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/images/test.jpg"
    );

    // Act
    const response = await GET(request, {
      params: Promise.resolve({ actor: "actor_a", filename: "test.jpg" }),
    });

    // Assert
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe("image/jpeg");
    expect(mockReadImageFile).toHaveBeenCalledTimes(1);
    expect(mockReadImageFile).toHaveBeenCalledWith("actor_a", "test.jpg");
  });

  it(".jpeg 拡張子も image/jpeg で返す", async () => {
    // Arrange
    mockReadImageFile.mockResolvedValue(Buffer.from("data"));
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/images/photo.jpeg"
    );

    // Act
    const response = await GET(request, {
      params: Promise.resolve({ actor: "actor_a", filename: "photo.jpeg" }),
    });

    // Assert
    expect(response.headers.get("Content-Type")).toBe("image/jpeg");
  });

  it("PNG 画像を image/png Content-Type で返す", async () => {
    // Arrange
    mockReadImageFile.mockResolvedValue(Buffer.from("fake png"));
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/images/icon.png"
    );

    // Act
    const response = await GET(request, {
      params: Promise.resolve({ actor: "actor_a", filename: "icon.png" }),
    });

    // Assert
    expect(response.headers.get("Content-Type")).toBe("image/png");
  });

  it("URL エンコードされたファイル名をデコードして readImageFile を呼ぶ", async () => {
    // Arrange
    mockReadImageFile.mockResolvedValue(Buffer.from("data"));
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/images/my%20photo.jpg"
    );

    // Act
    await GET(request, {
      params: Promise.resolve({ actor: "actor_a", filename: "my%20photo.jpg" }),
    });

    // Assert
    expect(mockReadImageFile).toHaveBeenCalledWith("actor_a", "my photo.jpg");
  });

  it("未知の拡張子は application/octet-stream で返す", async () => {
    // Arrange
    mockReadImageFile.mockResolvedValue(Buffer.from("data"));
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/images/file.raw"
    );

    // Act
    const response = await GET(request, {
      params: Promise.resolve({ actor: "actor_a", filename: "file.raw" }),
    });

    // Assert
    expect(response.headers.get("Content-Type")).toBe("application/octet-stream");
  });

  it("LocalAnalysisRepository を正しいパスで初期化する", async () => {
    // Arrange
    mockReadImageFile.mockResolvedValue(Buffer.from("data"));
    const request = new NextRequest(
      "http://localhost/api/actors/actor_a/images/test.jpg"
    );

    // Act
    await GET(request, {
      params: Promise.resolve({ actor: "actor_a", filename: "test.jpg" }),
    });

    // Assert
    expect(LocalAnalysisRepository).toHaveBeenCalledWith(
      expect.anything(),
      "/test/project/data/images"
    );
  });
});
