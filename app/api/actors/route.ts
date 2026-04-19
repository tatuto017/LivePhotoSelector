import path from "path";
import { NextResponse } from "next/server";
import { createPool, createDb } from "@/lib/db";
import { LocalAnalysisRepository } from "@/lib/repositories/LocalAnalysisRepository";

/**
 * GET /api/actors
 * sorting_state テーブルから被写体IDリストを返す
 */
export async function GET(): Promise<NextResponse> {
  const pool = createPool();
  const db = createDb(pool);
  const repo = new LocalAnalysisRepository(
    db,
    path.join(process.env.PROJECT_ROOT ?? "", "data", "images")
  );
  const actors = await repo.getActors();
  return NextResponse.json(actors);
}
