import path from "path";
import Link from "next/link";
import { createPool, createDb } from "@/lib/db";
import { LocalAnalysisRepository } from "@/lib/repositories/LocalAnalysisRepository";

// ローカル FS を毎リクエスト読み込むため静的生成を無効化する
export const dynamic = "force-dynamic";

/**
 * トップページ（Server Component）
 * MySQL の sorting_state テーブルを読み取り、被写体一覧を表示する
 */
export default async function Home() {
  const pool = createPool();
  const db = createDb(pool);
  const repo = new LocalAnalysisRepository(
    db,
    path.join(process.env.PROJECT_ROOT ?? "", "images")
  );
  const actors = await repo.getActors();

  return (
    <main className="min-h-screen bg-gray-950 text-white p-8">
      <h1 className="text-2xl font-bold mb-8">Live Photo Selector</h1>
      {actors.length === 0 ? (
        <p className="text-gray-400">被写体が見つかりません</p>
      ) : (
        <ul className="space-y-4">
          {actors.map((actor) => (
            <li key={actor}>
              <Link
                href={`/actors/${actor}`}
                className="block w-full rounded-xl bg-gray-800 hover:bg-gray-700 active:bg-gray-600 px-6 py-4 text-lg font-medium transition-colors"
              >
                {actor}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
