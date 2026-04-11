import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePinchZoom } from "./usePinchZoom";

/** テスト用タッチオブジェクトを生成する */
const makeTouch = (clientX: number, clientY: number): Touch =>
  ({ clientX, clientY } as Touch);

/** テスト用 TouchEvent を生成する */
const makeTouchEvent = (touches: Touch[]): React.TouchEvent => ({
  touches: { length: touches.length, ...touches } as unknown as React.TouchList,
  stopPropagation: vi.fn(),
} as unknown as React.TouchEvent);

describe("usePinchZoom", () => {
  // ─── 初期状態 ────────────────────────────────────────────────
  it("初期値が正しい", () => {
    const { result } = renderHook(() => usePinchZoom());
    expect(result.current.scale).toBe(1);
    expect(result.current.panX).toBe(0);
    expect(result.current.panY).toBe(0);
    expect(result.current.isZoomed).toBe(false);
  });

  // ─── ピンチズーム ────────────────────────────────────────────
  it("2本指ピンチでスケールが増加する", () => {
    const { result } = renderHook(() => usePinchZoom());

    // Arrange: 初期距離 100px → 移動後 200px（2倍ズーム）
    const startEvent = makeTouchEvent([makeTouch(0, 0), makeTouch(100, 0)]);
    const moveEvent = makeTouchEvent([makeTouch(0, 0), makeTouch(200, 0)]);

    // Act
    act(() => { result.current.zoomHandlers.onTouchStart(startEvent); });
    act(() => { result.current.zoomHandlers.onTouchMove(moveEvent); });

    // Assert
    expect(result.current.scale).toBeCloseTo(2, 1);
    expect(result.current.isZoomed).toBe(true);
  });

  it("ズームアウトで scale が 1 以下にならない", () => {
    const { result } = renderHook(() => usePinchZoom());

    // Arrange: 初期距離 200px → 移動後 10px（大幅ズームアウト）
    const startEvent = makeTouchEvent([makeTouch(0, 0), makeTouch(200, 0)]);
    const moveEvent = makeTouchEvent([makeTouch(0, 0), makeTouch(10, 0)]);

    act(() => { result.current.zoomHandlers.onTouchStart(startEvent); });
    act(() => { result.current.zoomHandlers.onTouchMove(moveEvent); });

    expect(result.current.scale).toBeGreaterThanOrEqual(1);
  });

  it("ピンチ開始時に stopPropagation が呼ばれる", () => {
    const { result } = renderHook(() => usePinchZoom());
    const event = makeTouchEvent([makeTouch(0, 0), makeTouch(100, 0)]);

    act(() => { result.current.zoomHandlers.onTouchStart(event); });

    expect(event.stopPropagation).toHaveBeenCalledTimes(1);
  });

  it("ピンチ移動時に stopPropagation が呼ばれる", () => {
    const { result } = renderHook(() => usePinchZoom());
    const startEvent = makeTouchEvent([makeTouch(0, 0), makeTouch(100, 0)]);
    const moveEvent = makeTouchEvent([makeTouch(0, 0), makeTouch(150, 0)]);

    act(() => { result.current.zoomHandlers.onTouchStart(startEvent); });
    act(() => { result.current.zoomHandlers.onTouchMove(moveEvent); });

    expect(moveEvent.stopPropagation).toHaveBeenCalledTimes(1);
  });

  // ─── パン操作 ─────────────────────────────────────────────────
  it("ズーム中に1本指でパン操作できる", () => {
    const { result } = renderHook(() => usePinchZoom());

    // まずズームイン
    const startPinch = makeTouchEvent([makeTouch(0, 0), makeTouch(100, 0)]);
    const movePinch = makeTouchEvent([makeTouch(0, 0), makeTouch(300, 0)]);
    act(() => { result.current.zoomHandlers.onTouchStart(startPinch); });
    act(() => { result.current.zoomHandlers.onTouchMove(movePinch); });

    // 1本指パン開始
    const panStart = makeTouchEvent([makeTouch(100, 100)]);
    const panMove = makeTouchEvent([makeTouch(130, 120)]);
    act(() => { result.current.zoomHandlers.onTouchStart(panStart); });
    act(() => { result.current.zoomHandlers.onTouchMove(panMove); });

    expect(result.current.panX).toBe(30);
    expect(result.current.panY).toBe(20);
  });

  it("ズームしていない状態では1本指パンが無効", () => {
    const { result } = renderHook(() => usePinchZoom());

    const panStart = makeTouchEvent([makeTouch(100, 100)]);
    const panMove = makeTouchEvent([makeTouch(130, 120)]);
    act(() => { result.current.zoomHandlers.onTouchStart(panStart); });
    act(() => { result.current.zoomHandlers.onTouchMove(panMove); });

    expect(result.current.panX).toBe(0);
    expect(result.current.panY).toBe(0);
  });

  // ─── タッチ終了 ──────────────────────────────────────────────
  it("全指離した後にズームが解除されると scale/pan がリセットされる", () => {
    const { result } = renderHook(() => usePinchZoom());

    // ズームが 1.05 以下になるように少しだけピンチ
    const startEvent = makeTouchEvent([makeTouch(0, 0), makeTouch(100, 0)]);
    const moveEvent = makeTouchEvent([makeTouch(0, 0), makeTouch(102, 0)]);
    const endEvent = makeTouchEvent([]);

    act(() => { result.current.zoomHandlers.onTouchStart(startEvent); });
    act(() => { result.current.zoomHandlers.onTouchMove(moveEvent); });
    act(() => { result.current.zoomHandlers.onTouchEnd(endEvent); });

    // scale が 1.05 以下なのでリセットされる
    expect(result.current.scale).toBe(1);
    expect(result.current.panX).toBe(0);
    expect(result.current.panY).toBe(0);
  });

  it("ズーム中にタッチ終了すると stopPropagation が呼ばれる", () => {
    const { result } = renderHook(() => usePinchZoom());

    // 大きくズーム
    const startPinch = makeTouchEvent([makeTouch(0, 0), makeTouch(100, 0)]);
    const movePinch = makeTouchEvent([makeTouch(0, 0), makeTouch(300, 0)]);
    act(() => { result.current.zoomHandlers.onTouchStart(startPinch); });
    act(() => { result.current.zoomHandlers.onTouchMove(movePinch); });

    const endEvent = makeTouchEvent([]);
    act(() => { result.current.zoomHandlers.onTouchEnd(endEvent); });

    expect(endEvent.stopPropagation).toHaveBeenCalledTimes(1);
  });
});
