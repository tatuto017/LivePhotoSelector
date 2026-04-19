import path from "path";
import { NextRequest, NextResponse } from "next/server";
import { createPool, createDb } from "@/lib/db";
import { LocalAnalysisRepository } from "@/lib/repositories/LocalAnalysisRepository";

/** 拡張子から Content-Type を決定するマッピング */
const CONTENT_TYPE_MAP: Record<string, string> = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".gif": "image/gif",
  ".webp": "image/webp",
};

/**
 * GET /api/actors/[actor]/images/[filename]
 * 画像ファイルをパストラバーサル対策付きで配信する
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ actor: string; filename: string }> }
): Promise<NextResponse> {
  const { actor, filename } = await params;
  const decodedFilename = decodeURIComponent(filename);

  const pool = createPool();
  const db = createDb(pool);
  const repo = new LocalAnalysisRepository(
    db,
    path.join(process.env.PROJECT_ROOT ?? "", "data", "images")
  );

  const buffer = await repo.readImageFile(actor, decodedFilename);
  const ext = path.extname(decodedFilename).toLowerCase();
  const contentType = CONTENT_TYPE_MAP[ext] ?? "application/octet-stream";

  // Buffer を Uint8Array に変換して NextResponse に渡す（BodyInit 互換）
  return new NextResponse(new Uint8Array(buffer), {
    headers: { "Content-Type": contentType },
  });
}
