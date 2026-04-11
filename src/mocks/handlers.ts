import { http, HttpResponse } from "msw";

/**
 * MSW のデフォルトハンドラ定義
 * テスト個別の上書きは server.use() で行う
 */
export const handlers = [
  // デフォルトハンドラは空（各テストで個別に定義する）
  http.patch("/api/actors/:actor/photos/:filename", () =>
    HttpResponse.json({ ok: true })
  ),
];
