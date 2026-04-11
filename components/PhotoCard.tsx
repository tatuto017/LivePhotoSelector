"use client";

import { motion } from "framer-motion";
import { usePinchZoom } from "@/hooks/usePinchZoom";

/** スワイプ判定の移動量閾値（px） */
const SWIPE_OFFSET_THRESHOLD = 80;
/** スワイプ判定の速度閾値（px/s） */
const SWIPE_VELOCITY_THRESHOLD = 500;

/** PhotoCard のプロパティ */
export interface PhotoCardProps {
  /** 被写体ID */
  actor: string;
  /** 画像ファイル名 */
  filename: string;
  /** 撮影日（YYYY-MM-DD） */
  shootingDate: string;
  /** OK/NG 確定時のコールバック */
  onConfirm: (filename: string, shootingDate: string, state: "ok" | "ng") => void;
}

/**
 * 写真カードコンポーネント
 * - 右スワイプで OK、左スワイプで NG を確定
 * - ピンチズーム中はスワイプを無効化
 * - ズーム中は1本指でパン移動
 */
export function PhotoCard({
  actor,
  filename,
  shootingDate,
  onConfirm,
}: PhotoCardProps) {
  const { scale, panX, panY, isZoomed, zoomHandlers } = usePinchZoom();

  const handleDragEnd = (
    _: unknown,
    info: { offset: { x: number; y: number }; velocity: { x: number; y: number } }
  ): void => {
    const { offset, velocity } = info;
    if (
      offset.x > SWIPE_OFFSET_THRESHOLD ||
      velocity.x > SWIPE_VELOCITY_THRESHOLD
    ) {
      onConfirm(filename, shootingDate, "ok");
    } else if (
      offset.x < -SWIPE_OFFSET_THRESHOLD ||
      velocity.x < -SWIPE_VELOCITY_THRESHOLD
    ) {
      onConfirm(filename, shootingDate, "ng");
    }
  };

  return (
    <motion.div
      className="absolute inset-0 flex items-center justify-center cursor-grab active:cursor-grabbing"
      drag={isZoomed ? false : "x"}
      dragConstraints={{ left: 0, right: 0 }}
      dragElastic={0.7}
      onDragEnd={handleDragEnd}
    >
      {/* ズーム・パン対象のラッパー */}
      <div
        className="w-full h-full flex items-center justify-center overflow-hidden"
        style={{
          transform: `scale(${scale}) translate(${panX}px, ${panY}px)`,
          transformOrigin: "center center",
          touchAction: "none",
        }}
        {...zoomHandlers}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`/api/actors/${encodeURIComponent(actor)}/images/${encodeURIComponent(filename)}`}
          alt={filename}
          draggable={false}
          className="max-w-full max-h-full object-contain select-none"
        />
      </div>
    </motion.div>
  );
}
