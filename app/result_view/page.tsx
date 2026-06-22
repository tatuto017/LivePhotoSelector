import { createPool, createDb } from "@/lib/db";
import { ResultViewRepository } from "@/lib/repositories/ResultViewRepository";

// 毎リクエストごとにDBを参照するため静的生成を無効化する
export const dynamic = "force-dynamic";

/**
 * 選別結果表示ページ（Server Component）
 * sorting_state を集計し、最新 20 件をテーブルで表示する
 */
export default async function ResultViewPage() {
  const pool = createPool();
  const db = createDb(pool);
  const repo = new ResultViewRepository(db);
  const rows = await repo.getResults();

  return (
    <main className="min-h-screen bg-gray-950 text-white p-8">
      <h1 className="text-2xl font-bold mb-8">選別結果</h1>
      {rows.length === 0 ? (
        <p className="text-gray-400">結果がありません</p>
      ) : (
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-gray-700">
              <th className="py-2 px-4">件数</th>
              <th className="py-2 px-4">被写体</th>
              <th className="py-2 px-4">日付</th>
              <th className="py-2 px-4">選別状態</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-gray-800 hover:bg-gray-800">
                <td className="py-2 px-4">{row.count}</td>
                <td className="py-2 px-4">{row.actorId}</td>
                <td className="py-2 px-4">{row.date}</td>
                <td className="py-2 px-4">{row.selectionState}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
