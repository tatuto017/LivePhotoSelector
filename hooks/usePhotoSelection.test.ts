import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { usePhotoSelection } from "./usePhotoSelection";
import { ResultRepository } from "@/lib/repositories/ResultRepository";
import { PhotoRepository } from "@/lib/repositories/PhotoRepository";
import { Photo } from "@/lib/types";

/** テスト用の写真データ（2枚） */
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

/** テスト用の追加フェッチ写真データ */
const makeExtraPhotos = (): Photo[] => [
  {
    filename: "c.jpg",
    shootingDate: "2026-01-02",
    score: 0.4,
    selectionState: "pending",
    selectedAt: null,
  },
];

describe("usePhotoSelection", () => {
  let mockRepo: ResultRepository;
  let mockPhotoRepo: PhotoRepository;

  beforeEach(() => {
    mockRepo = { save: vi.fn() } as unknown as ResultRepository;
    // デフォルトは hasMore: false（追加なし）で返す
    mockPhotoRepo = {
      fetchPending: vi.fn().mockResolvedValue({ photos: [], hasMore: false }),
    } as unknown as PhotoRepository;
  });

  // ─── 初期状態 ────────────────────────────────────────────────
  it("initialPhotos と error: null で初期化される", () => {
    // Arrange & Act
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
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
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
    );

    // Act
    await act(async () => {
      await result.current.confirmPhoto("a.jpg", "2026-01-01", "ok");
    });

    // Assert
    expect(
      result.current.visiblePhotos.some((p) => p.filename === "a.jpg")
    ).toBe(false);
  });

  it("repository.save を正しい引数で呼び出す", async () => {
    // Arrange
    vi.mocked(mockRepo.save).mockResolvedValue(undefined);
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
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
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
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
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
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
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
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
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
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
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
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

  // ─── 動的フェッチ ─────────────────────────────────────────────
  it("初期写真数が FETCH_THRESHOLD(5) 以下の場合は初期マウント時に fetchPending を呼ぶ", async () => {
    // Arrange
    vi.mocked(mockPhotoRepo.fetchPending).mockResolvedValue({
      photos: makeExtraPhotos(),
      hasMore: false,
    });

    // Act
    renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
    );

    // Assert
    await waitFor(() => {
      expect(mockPhotoRepo.fetchPending).toHaveBeenCalledTimes(1);
    });
    expect(mockPhotoRepo.fetchPending).toHaveBeenCalledWith("actor_a", 2, 6);
  });

  it("fetchPending の結果が visiblePhotos に追加される", async () => {
    // Arrange
    vi.mocked(mockPhotoRepo.fetchPending).mockResolvedValue({
      photos: makeExtraPhotos(),
      hasMore: false,
    });

    // Act
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
    );

    // Assert
    await waitFor(() => {
      expect(result.current.visiblePhotos).toHaveLength(3);
    });
    expect(result.current.visiblePhotos[2].filename).toBe("c.jpg");
  });

  it("fetchPending が失敗しても visiblePhotos は変更されない（silent 失敗）", async () => {
    // Arrange
    vi.mocked(mockPhotoRepo.fetchPending).mockRejectedValue(
      new Error("network error")
    );

    // Act
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
    );

    // 少し待ってエラー伝播しないことを確認
    await waitFor(() => {
      expect(mockPhotoRepo.fetchPending).toHaveBeenCalledTimes(1);
    });

    // Assert
    expect(result.current.visiblePhotos).toHaveLength(2);
    expect(result.current.error).toBeNull();
  });

  it("retryDelayMs > 0 のとき遅延後にリトライする", async () => {
    // Arrange
    vi.mocked(mockRepo.save)
      .mockRejectedValueOnce(new Error("fail 1"))
      .mockResolvedValue(undefined);
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 1)
    );

    // Act
    await act(async () => {
      await result.current.confirmPhoto("a.jpg", "2026-01-01", "ok");
    });

    // Assert: 1回失敗して遅延後に2回目で成功
    expect(mockRepo.save).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBeNull();
  });

  it("全リトライ失敗かつ initialPhotos に存在しないファイルは visiblePhotos を変更しない", async () => {
    // Arrange: unknown.jpg は makePhotos() に含まれない
    vi.mocked(mockRepo.save).mockRejectedValue(new Error("fail"));
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
    );
    const initialVisible = result.current.visiblePhotos;

    // Act
    await act(async () => {
      await result.current.confirmPhoto("unknown.jpg", "2026-01-01", "ok");
    });

    // Assert: 写真リストは変化なし
    expect(result.current.visiblePhotos).toEqual(initialVisible);
    expect(result.current.error).toBe("fail");
  });

  it("同一写真への並行リトライ失敗時は写真を重複追加しない（photo が既に prev に存在する分岐）", async () => {
    // Arrange: 同じ写真を 2 回同時に confirmPhoto → どちらも全リトライ失敗
    vi.mocked(mockRepo.save).mockRejectedValue(new Error("fail"));
    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
    );

    // Act: 並行呼び出し（await せずに同時実行）
    await act(async () => {
      const p1 = result.current.confirmPhoto("a.jpg", "2026-01-01", "ok");
      const p2 = result.current.confirmPhoto("a.jpg", "2026-01-01", "ok");
      await Promise.all([p1, p2]);
    });

    // Assert: a.jpg は 1 枚だけ復元される（重複なし）
    const count = result.current.visiblePhotos.filter(
      (p) => p.filename === "a.jpg"
    ).length;
    expect(count).toBe(1);
  });

  it("hasMore が false の場合は追加フェッチを行わない", async () => {
    // Arrange
    vi.mocked(mockPhotoRepo.fetchPending).mockResolvedValue({
      photos: makeExtraPhotos(),
      hasMore: false,
    });
    vi.mocked(mockRepo.save).mockResolvedValue(undefined);

    const { result } = renderHook(() =>
      usePhotoSelection("actor_a", makePhotos(), mockRepo, mockPhotoRepo, 0)
    );
    // 初回フェッチ待機
    await waitFor(() => {
      expect(result.current.visiblePhotos).toHaveLength(3);
    });
    const callCountAfterFirst = vi.mocked(mockPhotoRepo.fetchPending).mock.calls.length;

    // Act: 写真を確定してもフェッチしない
    await act(async () => {
      await result.current.confirmPhoto("a.jpg", "2026-01-01", "ok");
    });

    // Assert
    expect(mockPhotoRepo.fetchPending).toHaveBeenCalledTimes(callCountAfterFirst);
  });
});
