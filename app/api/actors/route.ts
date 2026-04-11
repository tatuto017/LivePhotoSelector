import path from "path";
import { NextResponse } from "next/server";
import { LocalAnalysisRepository } from "@/lib/repositories/LocalAnalysisRepository";

/**
 * GET /api/actors
 * OneDrive の data ディレクトリから被写体IDリストを返す
 */
export async function GET(): Promise<NextResponse> {
  const oneDriveRoot = process.env.ONE_DRIVE_ROOT ?? "";
  const repo = new LocalAnalysisRepository(
    path.join(oneDriveRoot, "data"),
    path.join(oneDriveRoot, "images")
  );
  const actors = await repo.getActors();
  return NextResponse.json(actors);
}
