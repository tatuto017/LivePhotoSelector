import path from "path";
import { notFound } from "next/navigation";

// ローカル FS を毎リクエスト読み込むため静的生成を無効化する
export const dynamic = "force-dynamic";
import { createPool, createDb } from "@/lib/db";
import { LocalAnalysisRepository } from "@/lib/repositories/LocalAnalysisRepository";
import { PhotoSelectionClient } from "@/components/PhotoSelectionClient";

/** 初期ロード枚数（表示1枚 + 先読み5枚） */
const INITIAL_LOAD_COUNT = 6;

/** 被写体ページのプロパティ */
interface ActorPageProps {
  params: Promise<{ actor: string }>;
}

/**
 * 被写体の写真選別ページ（Server Component）
 * - pending 状態の写真をスコア降順で取得して PhotoSelectionClient に渡す
 * - 被写体が存在しない場合は 404
 */
export default async function ActorPage({ params }: ActorPageProps) {
  const { actor } = await params;
  const pool = createPool();
  const db = createDb(pool);
  const repo = new LocalAnalysisRepository(
    db,
    path.join(process.env.PROJECT_ROOT ?? "", "images")
  );

  const actors = await repo.getActors();
  if (!actors.includes(actor)) {
    notFound();
  }

  // pending かつ public=true の写真をスコア降順で初期ロード分取得
  const { photos: initialPhotos } = await repo.getPendingPhotosPage(
    actor,
    0,
    INITIAL_LOAD_COUNT
  );

  return (
    <PhotoSelectionClient actor={actor} initialPhotos={initialPhotos} />
  );
}
