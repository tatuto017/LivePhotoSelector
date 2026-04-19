import path from "path";
import { NextRequest, NextResponse } from "next/server";
import { createPool, createDb } from "@/lib/db";
import { LocalAnalysisRepository } from "@/lib/repositories/LocalAnalysisRepository";

/**
 * GET /api/actors/[actor]/photos?offset=0&limit=6
 * pending 写真をスコア降順でページネーション取得する
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ actor: string }> }
): Promise<NextResponse> {
  const { actor } = await params;
  const url = new URL(request.url);
  const offset = parseInt(url.searchParams.get("offset") ?? "0", 10);
  const limit = parseInt(url.searchParams.get("limit") ?? "6", 10);

  const pool = createPool();
  const db = createDb(pool);
  const repo = new LocalAnalysisRepository(
    db,
    path.join(process.env.PROJECT_ROOT ?? "", "data", "images")
  );

  const result = await repo.getPendingPhotosPage(actor, offset, limit);
  return NextResponse.json(result);
}
