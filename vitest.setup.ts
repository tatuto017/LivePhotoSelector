import "@testing-library/jest-dom";
import { server } from "./src/mocks/server";

/** MSW サーバーのライフサイクル管理 */
beforeAll(() => server.listen({ onUnhandledRequest: "warn" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
