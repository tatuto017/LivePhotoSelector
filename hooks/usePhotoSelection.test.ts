import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePhotoSelection } from "./usePhotoSelection";
import { ResultRepository } from "@/lib/repositories/ResultRepository";
import { Photo } from "@/lib/types";

/** テスト用の写真データ */
const makePhotos = (): Photo[] => [
  {
    filename: "a.jpg",
    shootingDate: "2026-01-01",
    score: 0.8,
    selectionState: "pending",
    selectedAt: null,
  },
  {
    filename: "b.jpg",
    shootingDate: "2026-01-01",
    score: 0.5,
    selectionState: "pending",
    selectedAt: null,
  },
];

describe("usePhotoSelection", () => {
  let mockRepo: ResultRepository;

  beforeEach(() => {
    mockRepo = { save: vi.fn() } as unknown as ResultRepository;
  });

  // ─── 初期状態 ────────────────────────────────────────────────
  it("initialPhotos と error: null で初期化される", () => {
    // Arrange & Act
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, 0)
    );

    // Assert
    expect(result.current.visiblePhotos).toEqual(makePhotos());
    expect(result.current.error).toBeNull();
  });

  // ─── 楽観的更新 ──────────────────────────────────────────────
  it("confirmPhoto 呼び出し直後に写真が非表示になる（楽観的更新）", async () => {
    // Arrange
    vi.mocked(mockRepo.save).mockResolvedValue(undefined);
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, 0)
    );

    // Act
    await act(async () => {
      await result.current.confirmPhoto("a.jpg", "2026-01-01", "ok");
    });

    // Assert
    expect(
      result.current.visiblePhotos.some((p) => p.filename === "a.jpg")
    ).toBe(false);
    expect(result.current.visiblePhotos).toHaveLength(1);
  });

  it("repository.save を正しい引数で呼び出す", async () => {
    // Arrange
    vi.mocked(mockRepo.save).mockResolvedValue(undefined);
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, 0)
    );

    // Act
    await act(async () => {
      await result.current.confirmPhoto("a.jpg", "2026-01-01", "ok");
    });

    // Assert
    expect(mockRepo.save).toHaveBeenCalledTimes(1);
    expect(mockRepo.save).toHaveBeenCalledWith(
      "actor_a",
      "a.jpg",
      "2026-01-01",
      "ok"
    );
  });

  // ─── リトライ ─────────────────────────────────────────────────
  it("保存失敗時に最大 3 回リトライする", async () => {
    // Arrange
    vi.mocked(mockRepo.save)
      .mockRejectedValueOnce(new Error("fail 1"))
      .mockRejectedValueOnce(new Error("fail 2"))
      .mockResolvedValue(undefined);
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, 0)
    );

    // Act
    await act(async () => {
      await result.current.confirmPhoto("a.jpg", "2026-01-01", "ok");
    });

    // Assert
    expect(mockRepo.save).toHaveBeenCalledTimes(3);
    // 3回目で成功したのでエラーはない
    expect(result.current.error).toBeNull();
    expect(
      result.current.visiblePhotos.some((p) => p.filename === "a.jpg")
    ).toBe(false);
  });

  it("3回全て失敗した場合は写真を復元してエラーを表示する", async () => {
    // Arrange
    vi.mocked(mockRepo.save).mockRejectedValue(new Error("always fail"));
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, 0)
    );

    // Act
    await act(async () => {
      await result.current.confirmPhoto("a.jpg", "2026-01-01", "ok");
    });

    // Assert
    expect(mockRepo.save).toHaveBeenCalledTimes(3);
    expect(result.current.error).toBe("always fail");
    expect(
      result.current.visiblePhotos.some((p) => p.filename === "a.jpg")
    ).toBe(true);
  });

  it("3回全て失敗（非 Error オブジェクト）はデフォルトメッセージを表示する", async () => {
    // Arrange
    vi.mocked(mockRepo.save).mockRejectedValue("string error");
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, 0)
    );

    // Act
    await act(async () => {
      await result.current.confirmPhoto("a.jpg", "2026-01-01", "ok");
    });

    // Assert
    expect(result.current.error).toBe("保存に失敗しました。");
  });

  // ─── ng 選別 ─────────────────────────────────────────────────
  it("ng で confirmPhoto を呼んだ場合も正しく送信される", async () => {
    // Arrange
    vi.mocked(mockRepo.save).mockResolvedValue(undefined);
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, 0)
    );

    // Act
    await act(async () => {
      await result.current.confirmPhoto("b.jpg", "2026-01-01", "ng");
    });

    // Assert
    expect(mockRepo.save).toHaveBeenCalledWith(
      "actor_a",
      "b.jpg",
      "2026-01-01",
      "ng"
    );
  });

  // ─── エラーを閉じる ─────────────────────────────────────────
  it("dismissError でエラーが null になる", async () => {
    // Arrange
    vi.mocked(mockRepo.save).mockRejectedValue(new Error("fail"));
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, 0)
    );

    await act(async () => {
      await result.current.confirmPhoto("a.jpg", "2026-01-01", "ok");
    });
    expect(result.current.error).not.toBeNull();

    // Act
    act(() => { result.current.dismissError(); });

    // Assert
    expect(result.current.error).toBeNull();
  });
});
