# データ整理

## 処理概要
スコアリング後にデータ整理を行う
lycheeのアルバムから、`NG` の写真の削除を行う

## 実行コマンド

```bash
# 基本実行（lychee ルートアルバムID は環境変数 LYCHEE_ROOT_ALBUM_ID を使用）
python -m src.finalize.main

# lychee ルートアルバムIDを直接指定する場合（環境変数より優先）
python -m src.finalize.main --album_id=<ALBUM_ID>
```

## 処理フロー

### フェーズ1: 解析ファイルの公開（解析完了後）

**事前作業（手動）**: `{ANALYZE_ROOT}/{actor}/` 内の全ファイルを `{DATA_ROOT}/images/{actor}/` へ移動する。
- 被写体（actor）ごとにまとめて移動し、全ファイルの移動が完了してから次のステップへ進む。

**スクリプト実行** (`python -m src.finalize.main --publish`):
1. `sorting_state` テーブルの全 actor の `public` を `true` に更新する。
   - これにより Web アプリ上で写真が表示対象になる。

### フェーズ2: 選択後の整理（選択完了後）
`sorting_state` のレコードの削除はしないで、下記のファイル処理のみ行う。
1. `sorting_state` テーブルから `finalize` が `false` のレコードを取得する。
2. 取得したレコードの `selectionState` が `ok` の写真を `OK確定写真フォルダ` に移動する。
3. 取得したレコードの `selectionState` が `ng` の写真を削除する。
4. 取得したレコードの `finalize` を `true` に更新して `sorting_state` に反映する。
5. `lychee` のアルバムの写真を削除する。
   - 取得したレコードの `selectionState` が `ng`
   - 取得したレコードの `remove` が `false`
6. `lychee` のアルバムの写真を削除したレコードの `remove` を `true` に更新して `sorting_state` に反映する。

### lycheeのアルバムの写真の削除フロー
1. ルートアルバム配下の撮影日別のアルバムを取得する。
   - `LycheeRepository.getAlbumsByParentId()` に `ルートアルバムID` を指定
2. 撮影日別のアルバム配下の被写体別のアルバムを取得する。
   - `LycheeRepository.getAlbumsByParentId()` に `撮影日別のアルバムID` を指定
3. 被写体別のアルバムから写真のIDを取得する。
   - `LycheeRepository.getPhotoIdsByAlbumId()` に `被写体別のアルバムID` を指定
   - `sorting_state` の `shooting_date` が `撮影日` と一致
   - `sorting_state` の `actor_id` が `被写体ID` と一致
4. 取得した写真IDを pychee API を使用して削除する。
   - `LycheeApiClient.deletePhoto()` メソッド（`pychee` ライブラリの `LycheeClient.delete_photo` をラップ）
   - https://chostakovitch.github.io/pychee/pychee.html

#### アルバムを取得するクエリ（SQLAlchemy ORM）
`src/lychee_schema.py` に定義された `lychee_albums`・`lychee_base_albums` テーブルを使用する。

```python
select(lychee_albums.c.id, lychee_base_albums.c.title)
    .select_from(
        lychee_albums.join(
            lychee_base_albums,
            lychee_albums.c.id == lychee_base_albums.c.id,
            isouter=True,
        )
    )
    .where(lychee_albums.c.parent_id == parentId)
```

#### 写真のIDを取得するクエリ（SQLAlchemy ORM）
`src/lychee_schema.py` に定義された `lychee_photo_album` テーブルを使用する。

```python
select(lychee_photo_album.c.photo_id)
    .where(lychee_photo_album.c.album_id == albumId)
```

### lycheeのアルバムのDB接続
下記の環境変数を使用して、lycheeのDBに SQLAlchemy エンジン（`mysql+pymysql`）で接続する。

| 変数名 | 説明 |
| --- | --- |
| `LYCHEE_DATABASE` | lychee データベース名 |
| `LYCHEE_DB_USER` | lychee DB ユーザー名（`LYCHEE_USER` とは別。DB 直接接続専用） |
| `LYCHEE_DB_PASSWORD` | lychee DB パスワード（`LYCHEE_PASSWORD` とは別。DB 直接接続専用） |

### lychee Web API 接続
下記の環境変数を使用して、pychee の `LycheeClient` で lychee Web API に接続する。

| 変数名 | 説明 |
| --- | --- |
| `LYCHEE_URL` | lychee の URL |
| `LYCHEE_USER` | lychee ユーザー名（Web API ログイン専用） |
| `LYCHEE_PASSWORD` | lychee パスワード（Web API ログイン専用） |


### lycheeのアルバム階層構造
```text
{PROJECT_ROOT}/
└── YYYY.MM.DD/       # 撮影日毎のアルバム
    ├── actor_a/      # 被写体別のアルバム
    │   ├── xxxx.jpg　# 写真
    │   └── xxxx.jpg　# 写真
    └── actor_b/      # 被写体別のアルバム
        ├── xxxx.jpg　# 写真
        └── xxxx.jpg　# 写真
```
