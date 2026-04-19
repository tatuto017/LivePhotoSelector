-- analysis_records テーブル作成マイグレーション
-- DeepFace 解析結果を MySQL に永続化する

CREATE TABLE IF NOT EXISTS analysis_records (
    actor         VARCHAR(255)     NOT NULL COMMENT '被写体ID',
    filename      VARCHAR(255)     NOT NULL COMMENT 'ファイル名',
    shooting_date DATE             NOT NULL COMMENT '撮影日（EXIF DateTimeOriginal）',

    -- 感情スコア (DeepFace が返す 0〜100 の float)
    angry         FLOAT            NOT NULL DEFAULT 0 COMMENT '怒り',
    fear          FLOAT            NOT NULL DEFAULT 0 COMMENT '恐怖',
    happy         FLOAT            NOT NULL DEFAULT 0 COMMENT '喜び',
    sad           FLOAT            NOT NULL DEFAULT 0 COMMENT '悲しみ',
    surprise      FLOAT            NOT NULL DEFAULT 0 COMMENT '驚き',
    disgust       FLOAT            NOT NULL DEFAULT 0 COMMENT '嫌悪',
    neutral       FLOAT            NOT NULL DEFAULT 0 COMMENT '無表情',

    -- 顔の品質
    face_angle    FLOAT            NOT NULL DEFAULT 0  COMMENT '顔のロール角（度数）',
    is_occluded   TINYINT(1)       NOT NULL DEFAULT 0  COMMENT '遮蔽物フラグ（0=なし, 1=あり）',

    -- Facenet 埋め込みベクトル（128次元 float 配列）を JSON で格納
    face_embedding JSON             NOT NULL COMMENT 'Facenet 埋め込みベクトル',

    created_at    DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '作成日時',

    PRIMARY KEY (actor, filename, shooting_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DeepFace 解析結果テーブル';
