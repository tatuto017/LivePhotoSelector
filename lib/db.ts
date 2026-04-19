import mysql from "mysql2/promise";
import { drizzle } from "drizzle-orm/mysql2";
import * as schema from "./schema";

export type { Pool } from "mysql2/promise";

/**
 * 環境変数から MySQL 接続プールを生成する
 */
export function createPool(): mysql.Pool {
  return mysql.createPool({
    host: process.env.MYSQL_HOST ?? "localhost",
    port: parseInt(process.env.MYSQL_PORT ?? "3306", 10),
    user: process.env.MYSQL_USER ?? "",
    password: process.env.MYSQL_PASSWORD ?? "",
    database: process.env.MYSQL_DATABASE ?? "",
  });
}

/**
 * mysql2 プールから Drizzle ORM インスタンスを生成する
 */
export function createDb(pool: mysql.Pool) {
  return drizzle(pool, { schema, mode: "default" });
}

/** Drizzle ORM インスタンスの型 */
export type DrizzleDB = ReturnType<typeof createDb>;
