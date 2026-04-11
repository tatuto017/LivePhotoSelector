import path from "path";
import { notFound } from "next/navigation";

// ローカル FS を毎リクエスト読み込むため静的生成を無効化する
export const dynamic = "force-dynamic";
import { LocalAnalysisRepository } from "@/lib/repositories/LocalAnalysisRepository";
import { PhotoSelectionClient } from "@/components/PhotoSelectionClient";

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
  const oneDriveRoot = process.env.ONE_DRIVE_ROOT ?? "";
  const repo = new LocalAnalysisRepository(
    path.join(oneDriveRoot, "data"),
    path.join(oneDriveRoot, "images")
  );

  const actors = await repo.getActors();
  if (!actors.includes(actor)) {
    notFound();
  }

  const allPhotos = await repo.getPhotos(actor);
  // pending のみを選別対象とする
  const pendingPhotos = allPhotos.filter(
    (p) => p.selectionState === "pending"
  );

  return (
    <PhotoSelectionClient actor={actor} initialPhotos={pendingPhotos} />
  );
}
