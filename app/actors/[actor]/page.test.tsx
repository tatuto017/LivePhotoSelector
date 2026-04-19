import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { Photo } from "@/lib/types";

// lib/db と LocalAnalysisRepository をモック化
vi.mock("@/lib/db", () => ({
  createPool: vi.fn().mockReturnValue({}),
  createDb: vi.fn().mockReturnValue({}),
}));
vi.mock("@/lib/repositories/LocalAnalysisRepository");
import { LocalAnalysisRepository } from "@/lib/repositories/LocalAnalysisRepository";

// next/navigation をモック化
const mockNotFound = vi.fn();
vi.mock("next/navigation", () => ({
  notFound: () => mockNotFound(),
}));

// PhotoSelectionClient をモック化
vi.mock("@/components/PhotoSelectionClient", () => ({
  PhotoSelectionClient: ({
    actor,
    initialPhotos,
  }: {
    actor: string;
    initialPhotos: Photo[];
  }) => (
    <div data-testid="photo-selection-client">
      <span data-testid="actor">{actor}</span>
      <span data-testid="photo-count">{initialPhotos.length}</span>
    </div>
  ),
}));

import ActorPage from "./page";

/** テスト用の写真データ */
const makePhoto = (filename: string): Photo => ({
  filename,
  shootingDate: "2026-01-01",
  score: 0.5,
  selectionState: "pending",
  selectedAt: null,
});

describe("ActorPage（被写体写真選別ページ）", () => {
  let mockGetActors: ReturnType<typeof vi.fn>;
  let mockGetPendingPhotosPage: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockGetActors = vi.fn();
    mockGetPendingPhotosPage = vi.fn();
    vi.mocked(LocalAnalysisRepository).mockImplementation(
      () =>
        ({
          getActors: mockGetActors,
          getPendingPhotosPage: mockGetPendingPhotosPage,
          saveSelectionState: vi.fn(),
          readImageFile: vi.fn(),
        }) as unknown as LocalAnalysisRepository
    );
    vi.stubEnv("PROJECT_ROOT", "/test/project");
    mockNotFound.mockClear();
  });

  it("PhotoSelectionClient に actor と写真を渡す", async () => {
    // Arrange
    const photos = [makePhoto("a.jpg"), makePhoto("b.jpg")];
    mockGetActors.mockResolvedValue(["actor_a"]);
    mockGetPendingPhotosPage.mockResolvedValue({ photos, hasMore: false });

    // Act
    const Page = await ActorPage({ params: Promise.resolve({ actor: "actor_a" }) });
    render(Page);

    // Assert
    expect(screen.getByTestId("actor")).toHaveTextContent("actor_a");
    expect(screen.getByTestId("photo-count")).toHaveTextContent("2");
  });

  it("getPendingPhotosPage を offset=0, limit=6 で呼び出す", async () => {
    // Arrange
    mockGetActors.mockResolvedValue(["actor_a"]);
    mockGetPendingPhotosPage.mockResolvedValue({ photos: [], hasMore: false });

    // Act
    await ActorPage({ params: Promise.resolve({ actor: "actor_a" }) });

    // Assert
    expect(mockGetPendingPhotosPage).toHaveBeenCalledTimes(1);
    expect(mockGetPendingPhotosPage).toHaveBeenCalledWith("actor_a", 0, 6);
  });

  it("LocalAnalysisRepository を正しいパスで初期化する", async () => {
    // Arrange
    mockGetActors.mockResolvedValue(["actor_a"]);
    mockGetPendingPhotosPage.mockResolvedValue({ photos: [], hasMore: false });

    // Act
    await ActorPage({ params: Promise.resolve({ actor: "actor_a" }) });

    // Assert
    expect(LocalAnalysisRepository).toHaveBeenCalledWith(
      expect.anything(),
      "/test/project/images"
    );
    expect(mockGetActors).toHaveBeenCalledTimes(1);
  });

  it("存在しない actor の場合は notFound() を呼ぶ", async () => {
    // Arrange
    mockGetActors.mockResolvedValue(["actor_a"]);

    // Act
    try {
      await ActorPage({ params: Promise.resolve({ actor: "unknown_actor" }) });
    } catch {
      // notFound() が例外を投げた場合はキャッチ
    }

    // Assert
    expect(mockNotFound).toHaveBeenCalledTimes(1);
  });

  it("public=false の写真は含まれない（getPendingPhotosPage に委譲）", async () => {
    // Arrange: getPendingPhotosPage は DB 側で public=true かつ pending のみ返す
    const photos = [makePhoto("public_a.jpg")];
    mockGetActors.mockResolvedValue(["actor_a"]);
    mockGetPendingPhotosPage.mockResolvedValue({ photos, hasMore: false });

    // Act
    const Page = await ActorPage({ params: Promise.resolve({ actor: "actor_a" }) });
    render(Page);

    // Assert: getPendingPhotosPage の結果がそのまま渡される
    expect(screen.getByTestId("photo-count")).toHaveTextContent("1");
    expect(mockGetPendingPhotosPage).toHaveBeenCalledWith("actor_a", 0, 6);
  });
});
