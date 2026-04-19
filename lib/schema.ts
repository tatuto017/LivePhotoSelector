import {
  mysqlTable,
  varchar,
  date,
  float,
  tinyint,
  json,
  datetime,
  decimal,
  boolean,
} from "drizzle-orm/mysql-core";

/**
 * analysis_records テーブル定義
 * DeepFace 解析結果を格納する
 */
export const analysisRecords = mysqlTable("analysis_records", {
  actor: varchar("actor", { length: 255 }).notNull(),
  filename: varchar("filename", { length: 255 }).notNull(),
  shooting_date: date("shooting_date").notNull(),
  angry: float("angry").notNull().default(0),
  fear: float("fear").notNull().default(0),
  happy: float("happy").notNull().default(0),
  sad: float("sad").notNull().default(0),
  surprise: float("surprise").notNull().default(0),
  disgust: float("disgust").notNull().default(0),
  neutral: float("neutral").notNull().default(0),
  face_angle: float("face_angle").notNull().default(0),
  is_occluded: tinyint("is_occluded").notNull().default(0),
  face_embedding: json("face_embedding").notNull(),
  created_at: datetime("created_at").notNull(),
});

/**
 * sorting_state テーブル定義
 * 写真の選別状態を管理する
 */
export const sortingState = mysqlTable("sorting_state", {
  actor_id: varchar("actor_id", { length: 255 }).notNull(),
  filename: varchar("filename", { length: 255 }).notNull(),
  shooting_date: date("shooting_date").notNull(),
  score: decimal("score", { precision: 5, scale: 4 }),
  selection_state: varchar("selection_state", { length: 10 })
    .notNull()
    .default("pending"),
  learned: boolean("learned").notNull().default(false),
  selected_at: datetime("selected_at"),
  public: boolean("public").notNull().default(false),
});
