"use client";

import { useMemo } from "react";
import { Photo } from "@/lib/types";
import { ResultRepository } from "@/lib/repositories/ResultRepository";
import { usePhotoSelection } from "@/hooks/usePhotoSelection";
import { PhotoCard } from "@/components/PhotoCard";

/** 画面外に先読みする枚数 */
const PRELOAD_COUNT = 5;

/** PhotoSelectionClient のプロパティ */
export interface PhotoSelectionClientProps {
  /** 被写体ID */
  actor: string;
  /** 初期表示写真リスト（pending のみ、スコア降順） */
  initialPhotos: Photo[];
  /**
   * リトライ間隔（ms）
   * テスト時は 0 を DI することで即時リトライ可能
   */
  retryDelayMs?: number;
}

/**
 * 写真選別画面のクライアントコンポーネント
 * - ResultRepository は Server Component から渡せないため useMemo でクライアント側でインスタンス化
 * - 説明バー「← NG | ピンチで拡大 | OK →」を先頭に表示
 * - カードスタック形式で表示し、先頭 + PRELOAD_COUNT 枚を描画（画像先読み）
 * - 全リトライ失敗時はエラーバナーを表示
 */
export function PhotoSelectionClient({
  actor,
  initialPhotos,
  retryDelayMs,
}: PhotoSelectionClientProps) {
  // ResultRepository はクラスインスタンスのため Server Component から props として渡せない
  const repository = useMemo(() => new ResultRepository(), []);
  const { visiblePhotos, error, confirmPhoto, dismissError } =
    usePhotoSelection(actor, initialPhotos, repository, retryDelayMs);

  // 現在の写真 + 先読み分のみ描画
  const displayPhotos = visiblePhotos.slice(0, PRELOAD_COUNT + 1);

  return (
    <div className="flex flex-col h-screen bg-black text-white overflow-hidden">
      {/* 操作説明バー */}
      <div className="flex-none flex items-center justify-center py-2 px-4 bg-black/70 text-sm text-gray-300 select-none">
        ← NG | ピンチで拡大 | OK →
      </div>

      {/* エラーバナー */}
      {error && (
        <div
          role="alert"
          className="flex-none flex items-center justify-between px-4 py-2 bg-red-600 text-white text-sm cursor-pointer"
          onClick={dismissError}
        >
          <span>{error}</span>
          <span className="ml-4 font-bold">✕</span>
        </div>
      )}

      {/* 写真カードスタック */}
      <div className="relative flex-1">
        {displayPhotos.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center text-gray-400 text-lg select-none">
            選別完了
          </div>
        ) : (
          displayPhotos.map((photo: Photo, idx: number) => (
            <div
              key={`${photo.filename}-${photo.shootingDate}`}
              className="absolute inset-0"
              style={{
                zIndex: PRELOAD_COUNT - idx,
                // 先読み分は視覚的に後ろに重なる
                pointerEvents: idx === 0 ? "auto" : "none",
              }}
            >
              <PhotoCard
                actor={actor}
                filename={photo.filename}
                shootingDate={photo.shootingDate}
                onConfirm={confirmPhoto}
              />
            </div>
          ))
        )}
      </div>
    </div>
  );
}
