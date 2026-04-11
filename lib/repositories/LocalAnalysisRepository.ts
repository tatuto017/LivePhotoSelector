import path from "path";
import * as fs from "fs/promises";
import { Photo, SelectionState } from "@/lib/types";

/**
 * OneDrive ローカルマウント先から解析データと画像ファイルを読み書きするリポジトリ
 */
export class LocalAnalysisRepository {
  private dataRoot: string;
  private imagesRoot: string;

  constructor(dataRoot: string, imagesRoot: string) {
    this.dataRoot = dataRoot;
    this.imagesRoot = imagesRoot;
  }

  /**
   * data ディレクトリ内の *_analysis.json ファイルから被写体IDリストを取得する
   */
  async getActors(): Promise<string[]> {
    const files = await fs.readdir(this.dataRoot);
    return files
      .filter((f) => f.endsWith("_analysis.json"))
      .map((f) => f.replace("_analysis.json", ""));
  }

  /**
   * 被写体の写真一覧をスコア降順で取得する
   * スコアが null の場合は 0 として扱う
   */
  async getPhotos(actor: string): Promise<Photo[]> {
    const filePath = path.join(this.dataRoot, `${actor}_analysis.json`);
    const content = await fs.readFile(filePath, "utf-8");
    const photos: Photo[] = JSON.parse(content);
    return [...photos].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  }

  /**
   * 被写体の写真の選別状態を更新して保存する
   * filename と shootingDate が一致するエントリのみ更新する
   */
  async saveSelectionState(
    actor: string,
    filename: string,
    shootingDate: string,
    state: SelectionState
  ): Promise<void> {
    const filePath = path.join(this.dataRoot, `${actor}_analysis.json`);
    const content = await fs.readFile(filePath, "utf-8");
    const photos: Photo[] = JSON.parse(content);
    const idx = photos.findIndex(
      (p) => p.filename === filename && p.shootingDate === shootingDate
    );
    if (idx >= 0) {
      photos[idx].selectionState = state;
      photos[idx].selectedAt = new Date().toISOString();
    }
    await fs.writeFile(filePath, JSON.stringify(photos, null, 2), "utf-8");
  }

  /**
   * パストラバーサル対策付きで画像ファイルを読み込む
   * 解決したパスが imagesRoot 配下であることを検証してから読み込む
   */
  async readImageFile(actor: string, filename: string): Promise<Buffer> {
    const imagesRootResolved = path.resolve(this.imagesRoot);
    const imagePath = path.resolve(this.imagesRoot, actor, filename);
    // パストラバーサル対策: 解決パスが imagesRoot 配下であることを確認
    if (!imagePath.startsWith(imagesRootResolved + path.sep)) {
      throw new Error("Invalid file path");
    }
    return fs.readFile(imagePath);
  }
}
