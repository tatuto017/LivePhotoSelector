import { Photo } from "@/lib/types";

/** GET /api/actors/[actor]/photos のレスポンス型 */
export interface FetchPendingResponse {
  /** 取得した pending 写真リスト */
  photos: Photo[];
  /** さらに取得可能な写真が存在するか */
  hasMore: boolean;
}

/**
 * クライアントサイドから pending 写真を API 経由で取得するリポジトリ
 */
export class PhotoRepository {
  /**
   * pending 写真をページネーションで取得する
   * @param actor 被写体ID
   * @param offset 開始インデックス
   * @param limit 取得枚数
   * @throws 取得に失敗した場合（HTTP ステータスが 2xx 以外）
   */
  async fetchPending(
    actor: string,
    offset: number,
    limit: number
  ): Promise<FetchPendingResponse> {
    const url = `/api/actors/${encodeURIComponent(actor)}/photos?offset=${offset}&limit=${limit}`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch photos: ${response.status}`);
    }
    return response.json() as Promise<FetchPendingResponse>;
  }
}
