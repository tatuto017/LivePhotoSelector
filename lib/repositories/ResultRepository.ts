/**
 * クライアントサイドから選別結果を API 経由で保存するリポジトリ
 */
export class ResultRepository {
  /**
   * 写真の選別状態を API に保存する
   * @throws 保存に失敗した場合（HTTP ステータスが 2xx 以外）
   */
  async save(
    actor: string,
    filename: string,
    shootingDate: string,
    state: "ok" | "ng"
  ): Promise<void> {
    const url = `/api/actors/${encodeURIComponent(actor)}/photos/${encodeURIComponent(filename)}`;
    const response = await fetch(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shootingDate, selectionState: state }),
    });
    if (!response.ok) {
      throw new Error(`Failed to save: ${response.status}`);
    }
  }
}
