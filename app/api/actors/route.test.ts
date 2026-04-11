import { describe, it, expect, vi, beforeEach } from "vitest";

// LocalAnalysisRepository をモック化
vi.mock("@/lib/repositories/LocalAnalysisRepository");
import { LocalAnalysisRepository } from "@/lib/repositories/LocalAnalysisRepository";

import { GET } from "./route";

describe("GET /api/actors", () => {
  let mockGetActors: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockGetActors = vi.fn();
    vi.mocked(LocalAnalysisRepository).mockImplementation(
      () =>
        ({
          getActors: mockGetActors,
          getPhotos: vi.fn(),
          saveSelectionState: vi.fn(),
          readImageFile: vi.fn(),
        }) as unknown as LocalAnalysisRepository
    );
    vi.stubEnv("ONE_DRIVE_ROOT", "/test/onedrive");
  });

  it("被写体リストを JSON で返す", async () => {
    // Arrange
    mockGetActors.mockResolvedValue(["actor_a", "actor_b"]);

    // Act
    const response = await GET();
    const body = await response.json();

    // Assert
    expect(response.status).toBe(200);
    expect(body).toEqual(["actor_a", "actor_b"]);
  });

  it("LocalAnalysisRepository を正しいパスで初期化する", async () => {
    // Arrange
    mockGetActors.mockResolvedValue([]);

    // Act
    await GET();

    // Assert
    expect(LocalAnalysisRepository).toHaveBeenCalledWith(
      "/test/onedrive/data",
      "/test/onedrive/images"
    );
    expect(mockGetActors).toHaveBeenCalledTimes(1);
  });
});
