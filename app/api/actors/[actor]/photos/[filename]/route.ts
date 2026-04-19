import path from "path";
import { NextRequest, NextResponse } from "next/server";
import { createPool, createDb } from "@/lib/db";
import { LocalAnalysisRepository } from "@/lib/repositories/LocalAnalysisRepository";
import { SelectionState } from "@/lib/types";

/** PATCH リクエストボディの型 */
interface PatchBody {
  shootingDate: string;
  selectionState: SelectionState;
}

/**
 * PATCH /api/actors/[actor]/photos/[filename]
 * 写真の選別状態（OK/NG）を更新する
 */
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ actor: string; filename: string }> }
): Promise<NextResponse> {
  const { actor, filename } = await params;
  const body: PatchBody = await request.json();
  const { shootingDate, selectionState } = body;

  const pool = createPool();
  const db = createDb(pool);
  const repo = new LocalAnalysisRepository(
    db,
    path.join(process.env.PROJECT_ROOT ?? "", "data", "images")
  );

  await repo.saveSelectionState(
    actor,
    decodeURIComponent(filename),
    shootingDate,
    selectionState
  );

  return NextResponse.json({ ok: true });
}
