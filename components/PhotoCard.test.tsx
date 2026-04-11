import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import React from "react";

// framer-motion をモック化してドラッグコールバックをキャプチャする
let capturedOnDragEnd:
  | ((
      _: unknown,
      info: {
        offset: { x: number; y: number };
        velocity: { x: number; y: number };
      }
    ) => void)
  | undefined;
let capturedDragProp: string | boolean | undefined;

vi.mock("framer-motion", () => ({
  motion: {
    div: ({
      children,
      onDragEnd,
      drag,
      dragConstraints: _dc,
      dragElastic: _de,
      ...props
    }: React.PropsWithChildren<{
      onDragEnd?: typeof capturedOnDragEnd;
      drag?: string | boolean;
      dragConstraints?: unknown;
      dragElastic?: unknown;
    }>) => {
      capturedOnDragEnd = onDragEnd;
      capturedDragProp = drag;
      return (
        <div data-testid="motion-div" {...props}>
          {children}
        </div>
      );
    },
  },
}));

// usePinchZoom をモック化
vi.mock("@/hooks/usePinchZoom");
import { usePinchZoom } from "@/hooks/usePinchZoom";

import { PhotoCard } from "./PhotoCard";

/** usePinchZoom のデフォルトモック値 */
const defaultZoomState = {
  scale: 1,
  panX: 0,
  panY: 0,
  isZoomed: false,
  zoomHandlers: {
    onTouchStart: vi.fn(),
    onTouchMove: vi.fn(),
    onTouchEnd: vi.fn(),
  },
};

describe("PhotoCard", () => {
  beforeEach(() => {
    vi.mocked(usePinchZoom).mockReturnValue(defaultZoomState);
    capturedOnDragEnd = undefined;
    capturedDragProp = undefined;
  });

  // ─── レンダリング ────────────────────────────────────────────
  it("正しい src で画像を表示する", () => {
    // Arrange & Act
    render(
      <PhotoCard
        actor="actor_a"
        filename="test.jpg"
        shootingDate="2026-01-01"
        onConfirm={vi.fn()}
      />
    );

    // Assert
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute(
      "src",
      "/api/actors/actor_a/images/test.jpg"
    );
    expect(img).toHaveAttribute("alt", "test.jpg");
  });

  it("ファイル名に特殊文字が含まれる場合は URL エンコードする", () => {
    // Arrange & Act
    render(
      <PhotoCard
        actor="actor_a"
        filename="my photo.jpg"
        shootingDate="2026-01-01"
        onConfirm={vi.fn()}
      />
    );

    // Assert
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute(
      "src",
      "/api/actors/actor_a/images/my%20photo.jpg"
    );
  });

  // ─── ドラッグ設定 ────────────────────────────────────────────
  it("ズームしていない場合は drag='x' になる", () => {
    // Arrange
    vi.mocked(usePinchZoom).mockReturnValue({
      ...defaultZoomState,
      isZoomed: false,
    });

    // Act
    render(
      <PhotoCard
        actor="actor_a"
        filename="test.jpg"
        shootingDate="2026-01-01"
        onConfirm={vi.fn()}
      />
    );

    // Assert
    expect(capturedDragProp).toBe("x");
  });

  it("ズーム中は drag=false になる", () => {
    // Arrange
    vi.mocked(usePinchZoom).mockReturnValue({
      ...defaultZoomState,
      isZoomed: true,
      scale: 2,
    });

    // Act
    render(
      <PhotoCard
        actor="actor_a"
        filename="test.jpg"
        shootingDate="2026-01-01"
        onConfirm={vi.fn()}
      />
    );

    // Assert
    expect(capturedDragProp).toBe(false);
  });

  // ─── スワイプ判定 ────────────────────────────────────────────
  it("右スワイプ（offset.x > 閾値）で onConfirm('ok') が呼ばれる", () => {
    // Arrange
    const onConfirm = vi.fn();
    render(
      <PhotoCard
        actor="actor_a"
        filename="test.jpg"
        shootingDate="2026-01-01"
        onConfirm={onConfirm}
      />
    );

    // Act
    act(() => {
      capturedOnDragEnd?.({}, { offset: { x: 150, y: 0 }, velocity: { x: 0, y: 0 } });
    });

    // Assert
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith("test.jpg", "2026-01-01", "ok");
  });

  it("左スワイプ（offset.x < -閾値）で onConfirm('ng') が呼ばれる", () => {
    // Arrange
    const onConfirm = vi.fn();
    render(
      <PhotoCard
        actor="actor_a"
        filename="test.jpg"
        shootingDate="2026-01-01"
        onConfirm={onConfirm}
      />
    );

    // Act
    act(() => {
      capturedOnDragEnd?.({}, { offset: { x: -150, y: 0 }, velocity: { x: 0, y: 0 } });
    });

    // Assert
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith("test.jpg", "2026-01-01", "ng");
  });

  it("速度が高い右スワイプで onConfirm('ok') が呼ばれる", () => {
    // Arrange
    const onConfirm = vi.fn();
    render(
      <PhotoCard
        actor="actor_a"
        filename="test.jpg"
        shootingDate="2026-01-01"
        onConfirm={onConfirm}
      />
    );

    // Act
    act(() => {
      capturedOnDragEnd?.({}, { offset: { x: 0, y: 0 }, velocity: { x: 600, y: 0 } });
    });

    // Assert
    expect(onConfirm).toHaveBeenCalledWith("test.jpg", "2026-01-01", "ok");
  });

  it("速度が高い左スワイプで onConfirm('ng') が呼ばれる", () => {
    // Arrange
    const onConfirm = vi.fn();
    render(
      <PhotoCard
        actor="actor_a"
        filename="test.jpg"
        shootingDate="2026-01-01"
        onConfirm={onConfirm}
      />
    );

    // Act
    act(() => {
      capturedOnDragEnd?.({}, { offset: { x: 0, y: 0 }, velocity: { x: -600, y: 0 } });
    });

    // Assert
    expect(onConfirm).toHaveBeenCalledWith("test.jpg", "2026-01-01", "ng");
  });

  it("ドラッグ量が不十分の場合は onConfirm が呼ばれない", () => {
    // Arrange
    const onConfirm = vi.fn();
    render(
      <PhotoCard
        actor="actor_a"
        filename="test.jpg"
        shootingDate="2026-01-01"
        onConfirm={onConfirm}
      />
    );

    // Act
    act(() => {
      capturedOnDragEnd?.({}, { offset: { x: 10, y: 0 }, velocity: { x: 0, y: 0 } });
    });

    // Assert
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
