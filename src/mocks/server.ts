import { setupServer } from "msw/node";
import { handlers } from "./handlers";

/**
 * Vitest（Node.js 環境）用の MSW サーバーインスタンス
 * vitest.setup.ts で beforeAll/afterEach/afterAll に登録する
 */
export const server = setupServer(...handlers);
