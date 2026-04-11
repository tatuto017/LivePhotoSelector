"use client";

import { useRef, useState } from "react";

/** usePinchZoom の戻り値の型 */
export interface PinchZoomState {
  /** 現在のズームスケール（1.0 = 等倍） */
  scale: number;
  /** パン移動の X オフセット（px） */
  panX: number;
  /** パン移動の Y オフセット（px） */
  panY: number;
  /** ズーム中かどうか（scale > 1.05） */
  isZoomed: boolean;
  /** タッチイベントハンドラ群 */
  zoomHandlers: {
    onTouchStart: (e: React.TouchEvent) => void;
    onTouchMove: (e: React.TouchEvent) => void;
    onTouchEnd: (e: React.TouchEvent) => void;
  };
}

/**
 * ピンチズームとパン操作を管理するカスタムフック
 * - 2本指ピンチでズームイン/アウト
 * - ズーム中は1本指で上下左右パン
 * - ピンチ・パン操作時は stopPropagation でスワイプへのイベント伝播を防ぐ
 */
export function usePinchZoom(): PinchZoomState {
  const [scale, setScale] = useState(1);
  const [panX, setPanX] = useState(0);
  const [panY, setPanY] = useState(0);
  const lastDistanceRef = useRef<number | null>(null);
  const lastPanRef = useRef<{ x: number; y: number } | null>(null);
  // scale の最新値を ref で保持（クロージャ問題を回避）
  const scaleRef = useRef(1);

  /** 2点間のピンチ距離を計算する */
  const getDistance = (touches: React.TouchList): number => {
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  };

  const handleTouchStart = (e: React.TouchEvent): void => {
    if (e.touches.length === 2) {
      // 2本指：ピンチ開始
      lastDistanceRef.current = getDistance(e.touches);
      e.stopPropagation();
    } else if (e.touches.length === 1 && scaleRef.current > 1.05) {
      // 1本指 + ズーム中：パン開始
      lastPanRef.current = {
        x: e.touches[0].clientX,
        y: e.touches[0].clientY,
      };
      e.stopPropagation();
    }
  };

  const handleTouchMove = (e: React.TouchEvent): void => {
    if (e.touches.length === 2 && lastDistanceRef.current !== null) {
      // ピンチ移動でスケール更新
      const newDistance = getDistance(e.touches);
      const delta = newDistance / lastDistanceRef.current;
      const newScale = Math.max(1, Math.min(scaleRef.current * delta, 5));
      scaleRef.current = newScale;
      setScale(newScale);
      lastDistanceRef.current = newDistance;
      e.stopPropagation();
    } else if (
      e.touches.length === 1 &&
      scaleRef.current > 1.05 &&
      lastPanRef.current !== null
    ) {
      // パン移動
      const dx = e.touches[0].clientX - lastPanRef.current.x;
      const dy = e.touches[0].clientY - lastPanRef.current.y;
      setPanX((prev) => prev + dx);
      setPanY((prev) => prev + dy);
      lastPanRef.current = {
        x: e.touches[0].clientX,
        y: e.touches[0].clientY,
      };
      e.stopPropagation();
    }
  };

  const handleTouchEnd = (e: React.TouchEvent): void => {
    if (e.touches.length < 2) {
      lastDistanceRef.current = null;
    }
    if (e.touches.length === 0) {
      lastPanRef.current = null;
      // ズームが解除されたらパン位置もリセット
      if (scaleRef.current <= 1.05) {
        scaleRef.current = 1;
        setScale(1);
        setPanX(0);
        setPanY(0);
      }
    }
    // ズーム中またはまだ指が残っている場合は伝播を止める
    if (scaleRef.current > 1.05 || e.touches.length > 0) {
      e.stopPropagation();
    }
  };

  return {
    scale,
    panX,
    panY,
    isZoomed: scale > 1.05,
    zoomHandlers: {
      onTouchStart: handleTouchStart,
      onTouchMove: handleTouchMove,
      onTouchEnd: handleTouchEnd,
    },
  };
}
