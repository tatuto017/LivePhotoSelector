import type { Metadata } from "next";
import "./globals.css";

/** アプリケーション全体のメタデータ */
export const metadata: Metadata = {
  title: "Live Photo Selector",
  description: "ライブ写真選別アプリ",
};

/**
 * ルートレイアウト
 * 全ページ共通のHTML構造を定義する
 */
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
