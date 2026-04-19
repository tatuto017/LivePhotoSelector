import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// lib/db と LocalAnalysisRepository をモック化
vi.mock("@/lib/db", () => ({
  createPool: vi.fn().mockReturnValue({}),
  createDb: vi.fn().mockReturnValue({}),
}));
vi.mock("@/lib/repositories/LocalAnalysisRepository");
import { LocalAnalysisRepository } from "@/lib/repositories/LocalAnalysisRepository";

// next/link をモック化（Server Component テスト用）
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import Home from "./page";

describe("Home（被写体一覧ページ）", () => {
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
    vi.stubEnv("PROJECT_ROOT", "/test/project");
  });

  it("被写体リストが表示される", async () => {
    // Arrange
    mockGetActors.mockResolvedValue(["actor_a", "actor_b"]);

    // Act
    const Page = await Home();
    render(Page);

    // Assert
    expect(screen.getByText("actor_a")).toBeInTheDocument();
    expect(screen.getByText("actor_b")).toBeInTheDocument();
  });

  it("各被写体リンクが正しい href を持つ", async () => {
    // Arrange
    mockGetActors.mockResolvedValue(["actor_a"]);

    // Act
    const Page = await Home();
    render(Page);

    // Assert
    const link = screen.getByRole("link", { name: "actor_a" });
    expect(link).toHaveAttribute("href", "/actors/actor_a");
  });

  it("被写体が 0 件の場合は「被写体が見つかりません」を表示する", async () => {
    // Arrange
    mockGetActors.mockResolvedValue([]);

    // Act
    const Page = await Home();
    render(Page);

    // Assert
    expect(screen.getByText("被写体が見つかりません")).toBeInTheDocument();
  });

  it("LocalAnalysisRepository を正しいパスで初期化する", async () => {
    // Arrange
    mockGetActors.mockResolvedValue([]);

    // Act
    await Home();

    // Assert
    expect(LocalAnalysisRepository).toHaveBeenCalledWith(
      expect.anything(),
      "/test/project/images"
    );
    expect(mockGetActors).toHaveBeenCalledTimes(1);
  });
});
