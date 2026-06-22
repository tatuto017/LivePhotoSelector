import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { ResultViewRow } from "@/lib/types";

// lib/db をモック化
vi.mock("@/lib/db", () => ({
  createPool: vi.fn().mockReturnValue({}),
  createDb: vi.fn().mockReturnValue({}),
}));

// ResultViewRepository をモック化
vi.mock("@/lib/repositories/ResultViewRepository");
import { ResultViewRepository } from "@/lib/repositories/ResultViewRepository";

import ResultViewPage from "./page";

/** テスト用の ResultViewRow データ */
const makeRow = (overrides: Partial<ResultViewRow> = {}): ResultViewRow => ({
  count: 5,
  actorId: "actor_a",
  date: "2026/06/22",
  selectionState: "ok",
  ...overrides,
});

describe("ResultViewPage（選別結果表示ページ）", () => {
  let mockGetResults: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockGetResults = vi.fn();
    vi.mocked(ResultViewRepository).mockImplementation(
      () =>
        ({
          getResults: mockGetResults,
        }) as unknown as ResultViewRepository
    );
  });

  it("テーブルヘッダーを表示する", async () => {
    // Arrange — ヘッダーはデータがある場合のみ表示される
    mockGetResults.mockResolvedValue([makeRow()]);

    // Act
    const Page = await ResultViewPage();
    render(Page);

    // Assert
    expect(screen.getByText("件数")).toBeInTheDocument();
    expect(screen.getByText("被写体")).toBeInTheDocument();
    expect(screen.getByText("日付")).toBeInTheDocument();
    expect(screen.getByText("選別状態")).toBeInTheDocument();
  });

  it("取得した行データをテーブルに表示する", async () => {
    // Arrange
    const rows = [
      makeRow({ count: 10, actorId: "actor_a", date: "2026/06/22", selectionState: "ok" }),
      makeRow({ count: 3,  actorId: "actor_b", date: "2026/06/21", selectionState: "ng" }),
    ];
    mockGetResults.mockResolvedValue(rows);

    // Act
    const Page = await ResultViewPage();
    render(Page);

    // Assert
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("actor_a")).toBeInTheDocument();
    expect(screen.getByText("2026/06/22")).toBeInTheDocument();
    expect(screen.getByText("ok")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("actor_b")).toBeInTheDocument();
    expect(screen.getByText("2026/06/21")).toBeInTheDocument();
    expect(screen.getByText("ng")).toBeInTheDocument();
  });

  it("結果が0件の場合は「結果がありません」を表示する", async () => {
    // Arrange
    mockGetResults.mockResolvedValue([]);

    // Act
    const Page = await ResultViewPage();
    render(Page);

    // Assert
    expect(screen.getByText("結果がありません")).toBeInTheDocument();
  });

  it("ResultViewRepository.getResults を1回呼び出す", async () => {
    // Arrange
    mockGetResults.mockResolvedValue([]);

    // Act
    await ResultViewPage();

    // Assert
    expect(mockGetResults).toHaveBeenCalledTimes(1);
  });

  it("ページタイトル「選別結果」を表示する", async () => {
    // Arrange
    mockGetResults.mockResolvedValue([]);

    // Act
    const Page = await ResultViewPage();
    render(Page);

    // Assert
    expect(screen.getByRole("heading", { name: "選別結果" })).toBeInTheDocument();
  });
});
