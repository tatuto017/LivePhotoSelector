"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Photo } from "@/lib/types";
import { ResultRepository } from "@/lib/repositories/ResultRepository";
import { PhotoRepository } from "@/lib/repositories/PhotoRepository";

/** 最大リトライ回数 */
const MAX_RETRIES = 3;
/** デフォルトのリトライ遅延（ms） */
const DEFAULT_RETRY_DELAY_MS = 1000;
/** バッファがこの枚数以下になったら追加フェッチを行う */
const FETCH_THRESHOLD = 5;
/** 1回のフェッチで取得する枚数 */
const FETCH_LIMIT = 6;

/** usePhotoSelection の戻り値の型 */
export interface PhotoSelectionState {
  /** 表示中（未確定）の写真リスト */
  visiblePhotos: Photo[];
  /** エラーメッセージ（エラーなしの場合は null） */
  error: string | null;
  /** 写真の OK/NG を確定する */
  confirmPhoto: (
    filename: string,
    shootingDate: string,
    state: "ok" | "ng"
  ) => Promise<void>;
  /** エラーバナーを閉じる */
  dismissError: () => void;
}

/**
 * 写真の選別状態を管理するカスタムフック
 * - OK/NG 確定時に楽観的更新（即座に非表示）
 * - visiblePhotos が FETCH_THRESHOLD 以下になったら API から追加フェッチ
 * - 保存失敗時に最大 3 回（retryDelayMs 間隔）リトライ
 * - 全リトライ失敗時のみ写真を再表示してエラーバナーを表示
 *
 * @param actor 被写体ID
 * @param initialPhotos 初期写真リスト
 * @param repository 選別結果の保存リポジトリ
 * @param photoRepository 写真の動的取得リポジトリ
 * @param retryDelayMs リトライ間隔（ms）。テスト時は 0 を渡すことで即時リトライ可能
 */
export function usePhotoSelection(
  actor: string,
  initialPhotos: Photo[],
  repository: ResultRepository,
  photoRepository: PhotoRepository,
  retryDelayMs: number = DEFAULT_RETRY_DELAY_MS
): PhotoSelectionState {
  const [visiblePhotos, setVisiblePhotos] = useState<Photo[]>(initialPhotos);
  const [error, setError] = useState<string | null>(null);
  // サーバーから取得済みの枚数を追跡（次フェッチのオフセット）
  const offsetRef = useRef(initialPhotos.length);
  // 重複フェッチを防止するフラグ
  const isFetchingRef = useRef(false);
  // さらに取得できる写真が存在するか
  const hasMoreRef = useRef(true);

  // visiblePhotos が FETCH_THRESHOLD 以下になったら追加フェッチ
  useEffect(() => {
    if (
      visiblePhotos.length <= FETCH_THRESHOLD &&
      hasMoreRef.current &&
      !isFetchingRef.current
    ) {
      isFetchingRef.current = true;
      photoRepository
        .fetchPending(actor, offsetRef.current, FETCH_LIMIT)
        .then(({ photos, hasMore }) => {
          setVisiblePhotos((prev) => [...prev, ...photos]);
          offsetRef.current += photos.length;
          hasMoreRef.current = hasMore;
        })
        .catch(() => {
          // フェッチ失敗は silent（表示中の写真への影響なし）
        })
        .finally(() => {
          isFetchingRef.current = false;
        });
    }
  }, [visiblePhotos.length, actor, photoRepository]);

  const confirmPhoto = useCallback(
    async (
      filename: string,
      shootingDate: string,
      state: "ok" | "ng"
    ): Promise<void> => {
      // 楽観的更新：API 応答を待たずに即座に非表示にする
      setVisiblePhotos((prev) =>
        prev.filter(
          (p) => !(p.filename === filename && p.shootingDate === shootingDate)
        )
      );

      // 保存リトライ処理
      let lastError: unknown;
      for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
        try {
          await repository.save(actor, filename, shootingDate, state);
          return;
        } catch (err) {
          lastError = err;
          if (attempt < MAX_RETRIES - 1 && retryDelayMs > 0) {
            await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
          }
        }
      }

      // 全リトライ失敗：写真を再表示してエラーバナーを表示
      setVisiblePhotos((prev) => {
        const photo = initialPhotos.find(
          (p) => p.filename === filename && p.shootingDate === shootingDate
        );
        if (photo && !prev.some((p) => p.filename === filename && p.shootingDate === shootingDate)) {
          return [photo, ...prev];
        }
        return prev;
      });
      setError(
        lastError instanceof Error ? lastError.message : "保存に失敗しました。"
      );
    },
    [actor, initialPhotos, repository, retryDelayMs]
  );

  const dismissError = useCallback(() => {
    setError(null);
  }, []);

  return { visiblePhotos, error, confirmPhoto, dismissError };
}
