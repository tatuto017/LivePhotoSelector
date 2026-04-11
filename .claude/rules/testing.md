# Next.js ユニットテスト・統合テストルール

このプロジェクトでテストを作成・修正する際は、以下のガイドラインを厳守してください。

## ユニットテスト方針
- **目標**: カバレッジ 100%
- **モック化**: テスト対象メソッドから呼び出している処理は全てモック化する
- **検証**: モック化した処理の **引数**・**呼び出し回数** のテストを必須とする
- **Python**: DeepFace・PIL.Image.open・ファイル操作（shutil.move 等）は全てモック化またはテスト用 `tmp_path` を使用する
- **タイマー**: リトライ遅延等のタイマーは DI（`retryDelayMs` 等）でテスト時に 0 を注入し、fake timer を使わない

## 使用スタック
- **フレームワーク**: Vitest
- **ライブラリ**: React Testing Library, MSW (API Mocking)
- **フック**: `@testing-library/react-hooks`

## ファイル構成と命名規則
- **コンポーネント**: `components/` 内の対象ファイルと同階層に `{ComponentName}.test.tsx` を作成。
- **Hooks/Utils**: 対象ファイルと同階層に `{name}.test.ts` を作成。
- **Pages (App Router)**: `app/` 内の各ディレクトリに `page.test.tsx` を作成。

## テスト記述の指針
- **Server Components**: 直接レンダリングせず、ロジックを分離してユニットテストするか、`render` 可能なら非同期コンポーネントとして扱う。
- **Client Components**: `user-event` を使用して、ユーザー操作（click, type等）をシミュレートする。
- **MSWの活用**: `app/api` へのリクエストや外部APIは、`src/mocks/handlers.ts` で定義されたMSWでハンドルする。

## Next.js 特有のモック
- `next/navigation`: `useRouter`, `usePathname`, `useSearchParams` は `vi.mock` でスタブ化する。
- `next/image`: `next/image` は自動でモックされる設定を確認するか、必要に応じて単純な `img` タグとして扱う。

## AAAパターンの徹底
```typescript
it('ログインボタンをクリックするとエラーメッセージが表示される', async () => {
  // Arrange (準備)
  render(<LoginForm />);
  const button = screen.getByRole('button', { name: /ログイン/i });

  // Act (実行)
  await userEvent.click(button);

  // Assert (検証)
  expect(screen.getByText(/メールアドレスが必要です/i)).toBeInTheDocument();
});
```

## バリデーションルール
- 空値、Nullチェック
- 境界値チェック
- 種別チェック(数値、文字型、日付型等)
- 必須/任意チェック

## 禁止事項
- data-testid の過剰な使用（可能な限り role や label で要素を取得する）。
- window.fetch の直接的なモック（MSWを優先する）。
