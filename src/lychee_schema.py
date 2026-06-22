"""lychee データベースのテーブル定義。

lychee は外部サービスのため、参照に必要なカラムのみを定義する。
"""

from sqlalchemy import Column, MetaData, String, Table

lychee_metadata = MetaData()

#: アルバム階層テーブル（parent_id による親子関係）
lychee_albums = Table(
    "albums",
    lychee_metadata,
    Column("id", String(255), nullable=False),
    Column("parent_id", String(255), nullable=True),
)

#: アルバム基本情報テーブル（title 等）
lychee_base_albums = Table(
    "base_albums",
    lychee_metadata,
    Column("id", String(255), nullable=False),
    Column("title", String(255), nullable=True),
)

#: 写真・アルバム中間テーブル
lychee_photo_album = Table(
    "photo_album",
    lychee_metadata,
    Column("album_id", String(255), nullable=False),
    Column("photo_id", String(255), nullable=False),
)
