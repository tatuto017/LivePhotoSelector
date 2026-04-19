-- sorting_state テーブル作成マイグレーション
-- iPhone での OK/NG 選択状態・スコア・学習済みフラグを管理する

CREATE TABLE IF NOT EXISTS sorting_state (
    actor_id         VARCHAR(255)  NOT NULL COMMENT '被写体ID',
    filename         VARCHAR(255)  NOT NULL COMMENT 'ファイル名',
    shooting_date    DATE          NOT NULL COMMENT '撮影日',

    score            DECIMAL(5,4)  NULL     DEFAULT NULL    COMMENT 'スコア（0〜1）',
    selection_state  VARCHAR(10)   NOT NULL DEFAULT 'pending' COMMENT '選択状態: pending / ok / ng',
    learned          BOOLEAN       NOT NULL DEFAULT FALSE   COMMENT '学習済みフラグ',
    selected_at      DATETIME      NULL     DEFAULT NULL    COMMENT '選択確定日時',
    public           BOOLEAN       NOT NULL DEFAULT FALSE   COMMENT '公開フラグ（ANALYZE_ROOT から DATA_ROOT への移動完了後に true）',

    PRIMARY KEY (actor_id, filename, shooting_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='写真選択状態テーブル';
