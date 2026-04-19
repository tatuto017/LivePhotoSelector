import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { Photo } from "@/lib/types";

// ResultRepository をモック化
vi.mock("@/lib/repositories/ResultRepository", () => ({
  ResultRepository: vi.fn(() => ({ save: vi.fn() })),
}));

// PhotoRepository をモック化
vi.mock("@/lib/repositories/PhotoRepository", () => ({
  PhotoRepository: vi.fn(() => ({
    fetchPending: vi.fn().mockResolvedValue({ photos: [], hasMore: false }),
  })),
}));

// usePhotoSelection をモック化
vi.mock("@/hooks/usePhotoSelection");
import { usePhotoSelection } from "@/hooks/usePhotoSelection";

// PhotoCard をモック化
vi.mock("@/components/PhotoCard", () => ({
  PhotoCard: ({
    filename,
    onConfirm,
  }: {
    filename: string;
    shootingDate: string;
    onConfirm: (f: string, d: string, s: "ok" | "ng") => void;
  }) => (
    <div data-testid={`photo-${filename}`}>
      <button onClick={() => onConfirm(filename, "2026-01-01", "ok")}>
        OK: {filename}
      </button>
    </div>
  ),
}));

import { PhotoSelectionClient } from "./PhotoSelectionClient";

/** テスト用の写真データ */
const makePhotos = (count: number): Photo[] =>
  Array.from({ length: count }, (_, i) => ({
    filename: `img${String(i).padStart(3, "0")}.jpg`,
    shootingDate: "2026-01-01",
    score: 1 - i * 0.1,
    selectionState: "pending" as const,
    selectedAt: null,
  }));

/** usePhotoSelection のデフォルトモック返り値を設定する */
const mockPhotoSelection = (photos: Photo[], error: string | null = null) => {
  const confirmPhoto = vi.fn();
  const dismissError = vi.fn();
  vi.mocked(usePhotoSelection).mockReturnValue({
    visiblePhotos: photos,
    error,
    confirmPhoto,
    dismissError,
  });
  return { confirmPhoto, dismissError };
};

describe("PhotoSelectionClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ─── 操作説明バー ────────────────────────────────────────────
  it("操作説明バー「← NG | ピンチで拡大 | OK →」が表示される", () => {
    // Arrange
    mockPhotoSelection(makePhotos(1));

    // Act
    render(<PhotoSelectionClient actor="actor_a" initialPhotos={makePhotos(1)} />);

    // Assert
    expect(screen.getByText("← NG | ピンチで拡大 | OK →")).toBeInTheDocument();
  });

  // ─── 写真の表示 ──────────────────────────────────────────────
  it("写真が 6 枚以上ある場合は先頭 6 枚のみ描画する（5枚先読み）", () => {
    // Arrange
    const photos = makePhotos(10);
    mockPhotoSelection(photos);

    // Act
    render(<PhotoSelectionClient actor="actor_a" initialPhotos={photos} />);

    // Assert
    // 先頭 6 枚（PRELOAD_COUNT + 1）のみ
    expect(screen.getByTestId("photo-img000.jpg")).toBeInTheDocument();
    expect(screen.getByTestId("photo-img005.jpg")).toBeInTheDocument();
    expect(screen.queryByTestId("photo-img006.jpg")).not.toBeInTheDocument();
  });

  it("写真が 0 枚の場合は「選別完了」を表示する", () => {
    // Arrange
    mockPhotoSelection([]);

    // Act
    render(<PhotoSelectionClient actor="actor_a" initialPhotos={[]} />);

    // Assert
    expect(screen.getByText("選別完了")).toBeInTheDocument();
  });

  // ─── 先読みカードの不可視化 ──────────────────────────────────
  it("先頭カード（idx=0）は opacity:1 で表示される", () => {
    // Arrange
    const photos = makePhotos(3);
    mockPhotoSelection(photos);

    // Act
    render(<PhotoSelectionClient actor="actor_a" initialPhotos={photos} />);

    // Assert
    const firstCard = screen.getByTestId("photo-img000.jpg").closest("[style]");
    expect(firstCard).toHaveStyle({ opacity: "1" });
  });

  it("2枚目以降のカード（idx>0）は opacity:0 で不可視になる", () => {
    // Arrange
    const photos = makePhotos(3);
    mockPhotoSelection(photos);

    // Act
    render(<PhotoSelectionClient actor="actor_a" initialPhotos={photos} />);

    // Assert
    const secondCard = screen.getByTestId("photo-img001.jpg").closest("[style]");
    expect(secondCard).toHaveStyle({ opacity: "0" });
  });

  // ─── エラーバナー ────────────────────────────────────────────
  it("error がある場合はエラーバナーを表示する", () => {
    // Arrange
    mockPhotoSelection(makePhotos(1), "保存に失敗しました。");

    // Act
    render(<PhotoSelectionClient actor="actor_a" initialPhotos={makePhotos(1)} />);

    // Assert
    const banner = screen.getByRole("alert");
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent("保存に失敗しました。");
  });

  it("error が null の場合はエラーバナーを表示しない", () => {
    // Arrange
    mockPhotoSelection(makePhotos(1), null);

    // Act
    render(<PhotoSelectionClient actor="actor_a" initialPhotos={makePhotos(1)} />);

    // Assert
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("エラーバナーをクリックすると dismissError が呼ばれる", async () => {
    // Arrange
    const { dismissError } = mockPhotoSelection(makePhotos(1), "エラー");
    render(<PhotoSelectionClient actor="actor_a" initialPhotos={makePhotos(1)} />);
    const banner = screen.getByRole("alert");

    // Act
    await userEvent.click(banner);

    // Assert
    expect(dismissError).toHaveBeenCalledTimes(1);
  });

  // ─── usePhotoSelection の呼び出し ────────────────────────────
  it("usePhotoSelection に正しい引数を渡す", () => {
    // Arrange
    const photos = makePhotos(2);
    mockPhotoSelection(photos);

    // Act
    render(
      <PhotoSelectionClient
        actor="actor_a"
        initialPhotos={photos}
        retryDelayMs={0}
      />
    );

    // Assert
    expect(usePhotoSelection).toHaveBeenCalledWith(
      "actor_a",
      photos,
      expect.any(Object), // ResultRepository インスタンス
      expect.any(Object), // PhotoRepository インスタンス
      0
    );
  });
});
