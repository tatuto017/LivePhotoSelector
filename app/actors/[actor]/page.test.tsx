import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { Photo } from "@/lib/types";

// LocalAnalysisRepository をモック化
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
const makePhoto = (
  filename: string,
  selectionState: Photo["selectionState"]
): Photo => ({
  filename,
  shootingDate: "2026-01-01",
  score: 0.5,
  selectionState,
  selectedAt: null,
});

describe("ActorPage（被写体写真選別ページ）", () => {
  let mockGetActors: ReturnType<typeof vi.fn>;
  let mockGetPhotos: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockGetActors = vi.fn();
    mockGetPhotos = vi.fn();
    vi.mocked(LocalAnalysisRepository).mockImplementation(
      () =>
        ({
          getActors: mockGetActors,
          getPhotos: mockGetPhotos,
          saveSelectionState: vi.fn(),
          readImageFile: vi.fn(),
        }) as unknown as LocalAnalysisRepository
    );
    vi.stubEnv("ONE_DRIVE_ROOT", "/test/onedrive");
    mockNotFound.mockClear();
  });

  it("PhotoSelectionClient に actor と pending 写真を渡す", async () => {
    // Arrange
    mockGetActors.mockResolvedValue(["actor_a"]);
    mockGetPhotos.mockResolvedValue([
      makePhoto("a.jpg", "pending"),
      makePhoto("b.jpg", "ok"),
      makePhoto("c.jpg", "pending"),
    ]);

    // Act
    const Page = await ActorPage({ params: Promise.resolve({ actor: "actor_a" }) });
    render(Page);

    // Assert
    expect(screen.getByTestId("actor")).toHaveTextContent("actor_a");
    // pending のみ渡る（2枚）
    expect(screen.getByTestId("photo-count")).toHaveTextContent("2");
  });

  it("LocalAnalysisRepository を正しいパスで初期化する", async () => {
    // Arrange
    mockGetActors.mockResolvedValue(["actor_a"]);
    mockGetPhotos.mockResolvedValue([makePhoto("a.jpg", "pending")]);

    // Act
    await ActorPage({ params: Promise.resolve({ actor: "actor_a" }) });

    // Assert
    expect(LocalAnalysisRepository).toHaveBeenCalledWith(
      "/test/onedrive/data",
      "/test/onedrive/images"
    );
    expect(mockGetActors).toHaveBeenCalledTimes(1);
    expect(mockGetPhotos).toHaveBeenCalledWith("actor_a");
  });

  it("存在しない actor の場合は notFound() を呼ぶ", async () => {
    // Arrange
    mockGetActors.mockResolvedValue(["actor_a"]);
    // notFound() は実際には例外を投げるので、ここではモックが呼ばれたか確認するだけ

    // Act
    try {
      await ActorPage({ params: Promise.resolve({ actor: "unknown_actor" }) });
    } catch {
      // notFound() が例外を投げた場合はキャッチ
    }

    // Assert
    expect(mockNotFound).toHaveBeenCalledTimes(1);
  });
});
