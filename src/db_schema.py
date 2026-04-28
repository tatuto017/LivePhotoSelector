"""SQLAlchemy Core テーブル定義。

analysis_records と sorting_state テーブルのスキーマを定義する。
各リポジトリはこのモジュールのテーブル定義を使用して型安全なクエリを構築する。
"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    JSON,
    MetaData,
    Numeric,
    String,
    Table,
    text,
)

metadata = MetaData()

#: DeepFace 解析結果テーブル
analysis_records = Table(
    "analysis_records",
    metadata,
    Column("actor", String(255), nullable=False),
    Column("filename", String(255), nullable=False),
    Column("shooting_date", Date, nullable=False),
    Column("angry", Float, nullable=False, default=0),
    Column("fear", Float, nullable=False, default=0),
    Column("happy", Float, nullable=False, default=0),
    Column("sad", Float, nullable=False, default=0),
    Column("surprise", Float, nullable=False, default=0),
    Column("disgust", Float, nullable=False, default=0),
    Column("neutral", Float, nullable=False, default=0),
    Column("face_angle", Float, nullable=False, default=0),
    Column("is_occluded", Boolean, nullable=False, default=False),
    Column("face_embedding", JSON, nullable=False),
    Column(
        "created_at",
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

#: 写真選別状態テーブル
sorting_state = Table(
    "sorting_state",
    metadata,
    Column("actor_id", String(255), nullable=False),
    Column("filename", String(255), nullable=False),
    Column("shooting_date", Date, nullable=False),
    Column("score", Numeric(5, 4), nullable=True),
    Column("selection_state", String(10), nullable=False, server_default="pending"),
    Column("learned", Boolean, nullable=False, server_default=text("FALSE")),
    Column("selected_at", DateTime, nullable=True),
    Column("public", Boolean, nullable=False, server_default=text("FALSE")),
    Column("finalize", Boolean, nullable=False, server_default=text("FALSE")),
)
