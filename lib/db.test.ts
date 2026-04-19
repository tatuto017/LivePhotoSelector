import { describe, it, expect, vi, beforeEach } from "vitest";

// mysql2/promise をモック化
vi.mock("mysql2/promise");
import mysql from "mysql2/promise";

// drizzle-orm/mysql2 をモック化
vi.mock("drizzle-orm/mysql2");
import { drizzle } from "drizzle-orm/mysql2";

import { createPool, createDb } from "./db";

describe("createPool", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.unstubAllEnvs();
  });

  it("環境変数から mysql.createPool を呼び出す", () => {
    // Arrange
    vi.stubEnv("MYSQL_HOST", "test-host");
    vi.stubEnv("MYSQL_PORT", "3307");
    vi.stubEnv("MYSQL_USER", "test-user");
    vi.stubEnv("MYSQL_PASSWORD", "test-pass");
    vi.stubEnv("MYSQL_DATABASE", "test-db");

    // Act
    createPool();

    // Assert
    expect(mysql.createPool).toHaveBeenCalledTimes(1);
    expect(mysql.createPool).toHaveBeenCalledWith({
      host: "test-host",
      port: 3307,
      user: "test-user",
      password: "test-pass",
      database: "test-db",
    });
  });

  it("環境変数が未設定の場合はデフォルト値を使用する", () => {
    // Act
    createPool();

    // Assert
    expect(mysql.createPool).toHaveBeenCalledWith({
      host: "localhost",
      port: 3306,
      user: "",
      password: "",
      database: "",
    });
  });

  it("MYSQL_PORT が未設定の場合はデフォルト 3306 を使用する", () => {
    // Arrange
    vi.stubEnv("MYSQL_HOST", "myhost");

    // Act
    createPool();

    // Assert
    expect(mysql.createPool).toHaveBeenCalledWith(
      expect.objectContaining({ port: 3306 })
    );
  });
});

describe("createDb", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("drizzle に pool を渡して Drizzle インスタンスを返す", () => {
    // Arrange
    const mockPool = {} as ReturnType<typeof mysql.createPool>;
    const mockDrizzle = { query: vi.fn() };
    vi.mocked(drizzle).mockReturnValue(mockDrizzle as unknown as ReturnType<typeof drizzle>);

    // Act
    const result = createDb(mockPool);

    // Assert
    expect(drizzle).toHaveBeenCalledTimes(1);
    expect(drizzle).toHaveBeenCalledWith(
      mockPool,
      expect.objectContaining({ mode: "default" })
    );
    expect(result).toBe(mockDrizzle);
  });
});
