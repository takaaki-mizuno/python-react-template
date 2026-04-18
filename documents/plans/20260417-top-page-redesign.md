# ボイラープレートトップページの改修

これは、Python( FastAPI ) + React のボイラープレートだが、トップページがTanstackのそのままである。これを、オリジナルのトップページに変更したい

@DESIGN.md を参考にデザインを調整しよう。コンテンツについては、このテンプレートの説明をするような内容をちょっと考えてほしい。

レスポンシブなデザインでお願いします。

---

## AI追記（2026-04-17）

### 合意済みの前提

- 想定読者は、**AI エージェント込みでこのテンプレートを開発基盤として採用するか検討している人**とする。
- トップページの主目的は、**このテンプレートの価値を短時間で伝えること**とする。
- 最優先で伝える価値は、**FastAPI + React をすぐ動かせる実用的なモノレポ構成**とする。
- 情報設計は、**構成ファースト + 後半に運用導線**の型を採用する。
- 主要 CTA は外部ページ遷移ではなく、**ページ内アンカーだけで完結**させる。
- `DESIGN.md` は、**ブランドカラーの流用元ではなく、余白・密度・タイポグラフィ・ミニマルさの参考資料**として扱う。
- 色・アイコン・OGP 画像は、このテンプレート向けに別途定義し、**MUJI 固有の赤やベージュをそのまま持ち込まない**。
- UI 文言は **日本語を基本**とし、`FastAPI`、`React`、`Docker`、ディレクトリ名、コマンド名などの固有名詞だけ英字を許容する。
- 改修対象には、トップページ本文だけでなく、**共通ヘッダー**、`frontend/index.html` の `title` / `description` / `lang` / `theme-color`、`frontend/public/manifest.json` の初期文言更新を含める。

### 背景

- 現在の `/` は `frontend/src/routes/index.tsx` の TanStack 初期サンプルのままであり、回転ロゴ、外部学習リンク、濃いダーク背景など、テンプレート紹介ページとして不要な表現が残っている。
- 共通レイアウトの `frontend/src/components/organisms/Header/index.tsx` も TanStack ロゴ前提のサイドメニュー構成であり、今回の目的である「テンプレートの価値を短時間で伝える紹介ページ」と噛み合っていない。
- `frontend/index.html` と `frontend/public/manifest.json` にも TanStack 初期文言が残っているため、本文だけ差し替えてもブラウザタブ名や PWA 名称との不整合が残る。
- `frontend/public/favicon.ico`、`logo192.png`、`logo512.png` も TanStack 初期資産のままであり、タブ・PWA・ホーム画面追加時に紹介ページ本文と視覚整合しない。
- `frontend/src/styles.css` はすでに Tailwind v4 の `@theme inline` と shadcn 用 OKLCH トークンを持っているため、landing page の見た目は **この既存トークン体系にどう接続するか** を先に決めないと実装者が迷う。
- `README.md`、`AGENTS.md`、`frontend/AGENTS.md`、`backend/AGENTS.md` を確認した結果、このテンプレートが実際に訴求できる事実は、少なくとも以下に整理できる。
  - FastAPI backend と React + Vite frontend を同居させたモノレポであること。
  - frontend build の出力先が `backend/static/` であり、backend から静的配信できること。
  - Docker Compose で起動できること。
  - `AGENTS.md` を正典とした計画駆動・品質ゲート付きの開発フローが定義されていること。
- 一方で、このリポジトリ固有のブランドカラーやロゴはまだ定義されていないため、紹介ページの見た目は **既存 UI トークンに整合する中立的な visual system** として設計する必要がある。
- 一方で、トップページ改修の主題はあくまで紹介ページ刷新であり、`README.md` 全面改稿や backend 機能追加まで含めるとスコープがぶれるため、今回の計画では対象外として扱う。

### 方針とその理由

1. **前半は「何が揃っていて、どう繋がるか」を最短で理解させる構成にする。**
   - 採用判断者は最初に「このテンプレートで何が手に入るのか」「frontend / backend / build がどう繋がるのか」を知りたいため。
   - 具体的には、ヒーローの直後に「このテンプレートで揃うもの」と「モノレポ構成の説明」を置く。

2. **後半に「開発の進め方」と「品質ゲート」を置き、導入後の運用イメージまで伝える。**
   - 価値提案だけでなく、実際にどう開発を進めるかが見えると、採用後の解像度が上がるため。
   - `AGENTS.md` にある PDCA と品質ゲートを短く再構成し、紹介ページの後半に配置する。
   - ただし、順番に依存しなくても読めるよう、ヘッダーから `進め方` と `品質` へ直接ジャンプできる導線を必ず持たせる。

3. **デザインは `DESIGN.md` の抽象原則だけ取り込み、色は既存トークンと整合する中立 palette へ再定義する。**
   - 今回の紹介対象は技術テンプレートであり、MUJI 固有のブランド色を持ち込む根拠がないため。
   - `DESIGN.md` からは「余白を広く取る」「影を抑える」「タイポグラフィで見せる」「line-height を高めに取る」といった抽象ルールだけを採用する。
   - 色は `frontend/src/styles.css` の既存 shadcn トークンを壊さず、`--landing-*` 名前空間の neutral / accent を追加して表現する。

4. **Tailwind v4 との統合方法を先に固定し、landing page 用 token は `@theme inline` 経由で utility として使える形にする。**
   - `styles.css` に生 CSS を書き散らすと既存 token と責務が混ざり、運用時にメンテナンスしにくくなるため。
   - `--primary` や既存 shadcn token は上書きせず、`--landing-bg`、`--landing-surface`、`--landing-ink`、`--landing-muted`、`--landing-line`、`--landing-accent` を追加し、必要なら `--color-landing-*` として `@theme inline` へ公開する。

5. **実装は route を薄くし、トップページ専用の UI と文言を分離する。**
   - `src/routes/index.tsx` に文言・レイアウト・断片的な UI を詰め込むと保守しづらいため。
   - 文言・アンカー・カード定義は `index.data.ts` に寄せ、画面構成は専用 organism に寄せる。

6. **LandingPage 固有の小部品は feature-local に同居させ、グローバルな molecules へは昇格させない。**
   - `SectionIntro`、`InfoCard`、`AnchorButton` は今回の landing page 専用であり、`components/molecules` に置くと抽象化だけが増えるため。
   - `frontend/src/components/organisms/LandingPage/` 配下に同居させ、再利用が明確になった時点で昇格を検討する。

7. **共通ヘッダーはトップページ向けに再設計するが、ページ内アンカー中心の単純な導線に留める。**
   - 現時点で存在する主要ルートは `/` だけであり、まずはトップページ完結の導線を優先した方が実装が明確で過剰設計を避けられるため。
   - ただし、PC / mobile の両方で使え、44px 以上のタッチターゲットを満たすアクセシブルな構成にする。

8. **メタ情報は title / description だけでなく、OGP・favicon・PWA icon まで含めて整える。**
   - 紹介ページは本文だけでなく、ブラウザタブ、SNS プレビュー、ホーム画面追加時の見え方まで含めて第一印象になるため。
   - 画像資産は複雑なイラストではなく、テンプレートの構造を連想できる単純な geometric mark とし、`favicon`、`logo192.png`、`logo512.png`、`og-image` に再利用する。

9. **ページ内で `Docker` を訴求するなら、実際に `docker compose up --build` が通ることを品質条件に入れる。**
   - README に書かれていても、紹介ページ本文で強く訴求するなら実動確認まで含めて担保した方がよいため。
   - もし実装時点で Docker フローを安定して確認できない場合は、ヒーローの主訴求から下げ、補足文へ格下げする。

### 想定セクション構成

1. **Header**
   - ブランド名とページ内アンカーナビゲーションを配置する。
   - リンク先は `#overview` / `#architecture` / `#workflow` / `#quality` に統一する。

2. **Hero**
   - テンプレートの価値を一文で伝える見出しと、短い説明文を置く。
   - CTA は `#architecture` と `#workflow` に飛ばす。

3. **このテンプレートで揃うもの**
   - Backend / Frontend / Build Flow / Agent Ready の 4 要素を短いカードで見せる。

4. **モノレポ構成の説明**
   - `frontend/`、`backend/`、`backend/static/` の関係を、文章だけでなく簡易ダイアグラムでも示す。

5. **このテンプレートでの開発の進め方**
   - Plan / Do / Check / Act を、現リポジトリの運用ルールに沿って説明する。

6. **品質ゲート**
   - Frontend / Backend それぞれで最低限通すべきコマンドと確認観点を示す。

7. **終端 CTA**
   - ページ内アンカーで再度 `#overview` または `#quality` に戻せるようにし、1 ページ内で理解が完結する構成にする。

### 暫定 visual token

- `--landing-bg: #f8fafc`
- `--landing-surface: #ffffff`
- `--landing-ink: #0f172a`
- `--landing-muted: #475569`
- `--landing-line: #dbe2ea`
- `--landing-accent: #2563eb`

補足:

- `--landing-accent` は、技術テンプレートとしての中立性と視認性を両立するため、**青系 1 色**に固定する。
- accent の用途は、**active link、focus ring、SVG ダイアグラムの接続線、site mark の強調部分、補助的な inline emphasis** に限定する。
- Hero の primary CTA は accent ベタ塗りではなく、`--landing-ink` 背景 + 白文字を基本とし、accent は小面積で使う。

### site mark ドラフト仕様

- source of truth は `frontend/public/site-mark.svg` とする。
- `viewBox` は `0 0 64 64` を基本にする。
- 形は、**左に上下 2 つの角丸矩形、右に 1 つの角丸矩形、その間を接続する 1 本の spine と 3 本の connector** で構成する。
  - 左上矩形 = `frontend`
  - 左下矩形 = `backend`
  - 右中央矩形 = `build/static output`
- 実装時の基準座標は以下とする。
  - 左上矩形: `x=8, y=10, w=18, h=12, rx=3`
  - 左下矩形: `x=8, y=42, w=18, h=12, rx=3`
  - 右中央矩形: `x=38, y=26, w=18, h=12, rx=3`
  - 縦 spine: `x=32`, `y=16 -> 48`
  - 接続線: 左上矩形右辺中心から spine、左下矩形右辺中心から spine、spine 中央から右矩形左辺中心へ接続
- 色の役割は以下とする。
  - 左側 2 矩形: `stroke/fill` は `--landing-ink` 系
  - 右側矩形と connector: `--landing-accent`
  - 背景: 透明または `--landing-surface`
- 16px 角まで縮小しても潰れないことを優先し、テキストや細かい装飾は入れない。

### 文言ドラフト（初版）

#### Hero

- 見出し案: `FastAPI と React を、すぐ動かせる実用的なモノレポ`
- 説明文案: `backend と frontend の責務を分けつつ、build と配信、計画駆動、品質ゲートまでひとつに揃えた開発基盤です。AI エージェント込みの開発でも、構成と手順がぶれにくいことを重視しています。`
- CTA 1: `構成を見る`
- CTA 2: `進め方を見る`

#### Overview カード

- カード 1 見出し: `バックエンド`
- カード 1 本文: `FastAPI を中心に、API と CLI を backend/ にまとめて育てられます。`
- カード 2 見出し: `フロントエンド`
- カード 2 本文: `React + Vite をベースに、型安全を保ちながら UI を素早く組み立てられます。`
- カード 3 見出し: `配信フロー`
- カード 3 本文: `frontend build を backend/static/ に出力し、そのまま backend から配信できます。`
- カード 4 見出し: `開発ルール`
- カード 4 本文: `AGENTS.md と documents/plans/ を起点に、計画駆動で進められる土台があります。`

#### Workflow セクション

- セクション見出し案: `このテンプレートでの進め方`
- ステップ 1: `Plan — まず documents/plans/ にやることと影響範囲を書く`
- ステップ 2: `Do — backend と frontend の責務を分けて小さく実装する`
- ステップ 3: `Check — test、lint、build を通してから完了を判断する`
- ステップ 4: `Act — 学びを計画書やガイドへ戻す`

#### Quality セクション

- セクション見出し案: `品質ゲートを最初から揃える`
- Frontend グループ見出し案: `フロントエンドの確認`
- Backend グループ見出し案: `バックエンドの確認`

### 想定変更ファイル

- `frontend/src/routes/index.tsx`
  - ルートを薄くし、トップページ専用 organism を描画するだけにする。
- `frontend/src/routes/index.data.ts`（新規）
  - ヒーロー文言、アンカー定義、カード文言、ワークフロー、品質ゲートの表示データを集約する。
- `frontend/src/routes/__root.tsx`
  - 共通ヘッダーの配置を維持しつつ、devtools を production bundle に含めない構成へ見直す。
- `frontend/src/components/organisms/Header/index.tsx`
  - TanStack ロゴ中心の既存ヘッダーを紹介ページ向けのアンカーナビに置き換える。
- `frontend/src/components/organisms/RouteDevtools/index.tsx`（新規）
  - TanStack devtools を dev 環境だけで lazy load するための分離コンポーネントを置く。
- `frontend/src/components/organisms/LandingPage/index.tsx`（新規）
  - ヒーロー、概要、構成説明、開発フロー、品質ゲート、終端 CTA を組み立てる。
- `frontend/src/components/organisms/LandingPage/SectionIntro.tsx`（新規）
  - LandingPage 専用のセクション見出し UI を同居させる。
- `frontend/src/components/organisms/LandingPage/InfoCard.tsx`（新規）
  - 概要カードや品質カードの最小 UI を同居させる。
- `frontend/src/components/organisms/LandingPage/AnchorButton.tsx`（新規）
  - ページ内アンカー用 CTA を同居させる。
- `frontend/src/components/organisms/LandingPage/ArchitectureDiagram.tsx`（新規）
  - モノレポ構成の図を inline SVG で描画する。
- `frontend/src/components/organisms/LandingPage/index.test.tsx`（新規）
  - データ駆動のアンカー整合、主要 section、CTA、品質ゲートの回帰テストを置く。
- `frontend/src/components/organisms/Header/index.test.tsx`（新規）
  - ヘッダーのアンカー表示、メニューの open / close、`aria-*`、`Esc` close を確認する。
- `frontend/src/styles.css`
  - landing page 用 token、`prefers-reduced-motion`、アンカー移動、レスポンシブの土台を追加する。
- `frontend/index.html`
  - `lang`、`title`、`meta description`、OGP、`theme-color` をトップページの内容に合わせて更新する。
- `frontend/public/manifest.json`
  - `name`、`short_name`、icon、`theme_color`、`background_color` を更新する。
- `frontend/public/favicon.ico`
  - TanStack 由来の favicon をテンプレート用の簡素な mark に差し替える。
- `frontend/public/logo192.png`
  - PWA / apple-touch-icon 用の 192px icon を差し替える。
- `frontend/public/logo512.png`
  - PWA 用の 512px icon を差し替える。
- `frontend/public/og-image.png`（新規）
  - OGP 用のソーシャルプレビュー画像を追加する。
- `frontend/public/og-card.svg`（新規）
  - `og-image.png` のソースになる OGP カード SVG を置く。
- `frontend/public/site-mark.svg`（新規）
  - favicon / PWA / OGP の元になる簡素なベクターマークを置く。
- `frontend/.env.production.example`（新規）
  - `VITE_SITE_URL` を定義し、`og:image` の絶対 URL 生成に使う。

### 具体的なタスク

#### 1. 事実確認と情報設計を固定する

- [x] `README.md`、`AGENTS.md`、`frontend/AGENTS.md`、`backend/AGENTS.md`、`DESIGN.md` から、トップページで言及してよい事実だけを抜き出す。
- [x] 訴求文言は「FastAPI + React モノレポ」「frontend build を backend/static に出力」「Docker 起動可能」「計画駆動と品質ゲートあり」の範囲に限定し、未実装機能や将来構想は書かない。
- [x] `Docker` をヒーローや主要カードで扱う場合は、後段の品質確認で `docker compose up --build` と `http://localhost:8000/api/healthz` の確認を必須にし、確認できない場合は補足文へ格下げする。
- [x] ページ内アンカー ID を `overview`、`architecture`、`workflow`、`quality` に固定し、ヘッダー、ヒーロー CTA、終端 CTA、各 section の `id` / `href` で必ず統一する。
- [x] UI 文言の言語ポリシーを固定する。見出し・説明・ボタンは日本語、技術名・ディレクトリ名・コマンドだけ英字を許容し、中途半端な英日混在を避ける。
- [x] セクション順を `Hero -> Overview -> Architecture -> Workflow -> Quality -> Final CTA` に固定し、実装中に順番がぶれないようにする。

#### 2. 文言データと画面骨格を分離する

- [x] `frontend/src/routes/index.data.ts` を新規作成し、以下を配列またはオブジェクトで定義する。
  - ナビゲーション項目
  - ヒーロー見出し / 説明文 / CTA
  - 「このテンプレートで揃うもの」の 4 カード
  - モノレポ構成説明の各ブロック
  - 開発フローの各ステップ
  - 品質ゲートの各項目
- [x] `frontend/src/routes/index.tsx` は `createFileRoute('/')` を維持しつつ、`LandingPage` organism を描画するだけの薄い実装に変更する。
- [x] `frontend/src/components/organisms/LandingPage/index.tsx` を新規作成し、トップページ固有のセクション構成をここへ集約する。
- [x] `LandingPage` では、文言そのものを JSX に散らさず `index.data.ts` の内容を読み込んで表示する形にそろえる。
- [x] 各 section に `id` と `aria-labelledby` を設定し、アンカー移動とアクセシビリティの両方を満たす。
- [x] `index.data.ts` のアンカー定義は `as const` で固定し、ヘッダー・CTA・section が同じソースを参照する形にする。

#### 3. LandingPage 専用の小部品を feature-local に作る

- [x] `frontend/src/components/organisms/LandingPage/SectionIntro.tsx` を作成し、セクションラベル・見出し・本文を LandingPage 内だけで再利用できるようにする。
- [x] `frontend/src/components/organisms/LandingPage/InfoCard.tsx` を作成し、概要カードと品質ゲートカードの最低限の見た目を表現する。
- [x] `frontend/src/components/organisms/LandingPage/AnchorButton.tsx` を作成し、ページ内アンカー専用 CTA を表現する。
- [x] `frontend/src/components/organisms/LandingPage/ArchitectureDiagram.tsx` を作成し、inline SVG でレスポンシブな構成図を描画する。
- [x] 既存の `frontend/src/components/atoms/button.tsx` は直接改変せず、landing page 固有の CTA は feature-local component と utility class で閉じる。

#### 4. ヘッダーを紹介ページ向けに再設計する

- [x] `frontend/src/components/organisms/Header/index.tsx` から、TanStack ロゴ画像、Home アイコン、ダークテーマ前提のサイドメニュー、空の Demo Links プレースホルダを削除する。
- [x] デスクトップ (`>= 1024px`) では、ブランド名 + 横並びアンカーナビだけを持つシンプルなヘッダーへ作り替える。ヘッダー内の追加 CTA は置かない。
- [x] タブレット / モバイル (`< 1024px`) では、横並びナビに切り替えず、メニューボタン + 開閉パネルの構成を維持する。
- [x] モバイルでは、現在の開閉状態管理を活かしつつ、ページ内アンカーだけを表示する軽量メニューへ変更する。
- [x] モバイルメニューのトリガー、各リンク、閉じるボタンはすべて 44px 以上のタッチターゲットを確保する。
- [x] 開閉ボタンには `aria-expanded`、`aria-controls`、`aria-label` を付与し、リンク押下時にメニューが閉じるようにする。
- [x] `Escape` キー押下でもメニューを閉じられるようにする。
- [x] ヘッダーは白背景 + 細いボーダー基調とし、重いシャドウや濃い背景は使わない。
- [x] ヘッダー高さの基準値を固定する。desktop は `72px`、tablet / mobile は `64px` を基本とし、`--header-height` に格納する。

#### 5. デザイン基盤とレスポンシブ土台を整える

- [x] `frontend/src/styles.css` に、landing page 用 token を `--landing-*` 名で追加し、既存の `--primary` など shadcn 用 token は上書きしない。
  - 追加対象: `--landing-bg`, `--landing-surface`, `--landing-ink`, `--landing-muted`, `--landing-line`, `--landing-accent`
  - `@theme inline` には `--color-landing-*` として公開し、Tailwind utility から使える状態にする。
- [x] landing token の実値は本計画の「暫定 visual token」を初期値とし、実装フェーズで無断変更しない。変更する場合は理由を計画に追記する。
- [x] `body` の font-family、文字色、背景色、line-height を `DESIGN.md` に合わせ、英数字と日本語が自然に見えるベースを作る。
- [x] フォントは `"Helvetica Neue", Arial, "Noto Sans JP", "Noto Sans JP Fallback", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif` を基準とし、見出しと本文で別フォントは増やさない。
- [x] CTA の基本サイズを固定する。本文内 CTA は `font-size: 14px`、`font-weight: 700`、`min-height: 44px`、`padding-inline: 16px〜20px` を下限にする。
- [x] 罫線は 1px、影は通常状態で 0、hover 時も背景色・文字色・枠色の変化だけに限定し、transition は `160ms ease` の color / background-color / border-color に絞る。
- [x] `prefers-reduced-motion: no-preference` のときだけ `scroll-behavior: smooth;` を有効化し、`prefers-reduced-motion: reduce` の場合は smooth scroll と長い transition を無効化する。
- [x] 各 section には `scroll-margin-top: calc(var(--header-height) + 24px)` を基本値として与える。
- [x] ブレークポイントは `DESIGN.md` の `Mobile <= 767px`、`Tablet <= 1024px`、`Desktop > 1024px` を基準にし、カード列数・余白・見出しサイズを切り替える。
- [x] section の縦余白は desktop / tablet / mobile で段階的に縮める。実装時の基準は `80px / 64px / 48px` とし、必要に応じてこの範囲で微調整する。
- [x] safe-area を考慮し、ヘッダーや画面端に接する余白には `env(safe-area-inset-*)` を必要な範囲で反映する。
- [x] レスポンシブ確認観点を固定する。少なくとも `375px`、`768px`、`1280px` の 3 幅で、横スクロールが出ない、CTA が 44px を下回らない、見出しが 3 行以上に暴れない、構成図が読めることを確認する。

#### 6. 各セクションを実装する

- [x] Hero セクションに、日本語の価値提案見出し、短い説明文、`#architecture` と `#workflow` へ飛ぶ 2 つの CTA を配置する。
- [x] Overview セクションに、`Backend` / `Frontend` / `Build Flow` / `Agent Ready` の 4 カードを配置する。
- [x] Overview の文言は、技術名の羅列だけで終わらせず「何が嬉しいか」が一目で伝わる短文に調整する。
- [x] Overview と Quality のカード見出しは日本語を基本にし、必要なら `FastAPI` や `React` を補足行へ逃がす。
- [x] Architecture セクションに、`frontend/`、`backend/`、`backend/static/` の関係がわかる inline SVG の簡易ダイアグラムを組む。
- [x] Architecture セクションには、「frontend build を backend から配信する」というリポジトリ固有の接続点を必ず明示する。
- [x] Workflow セクションに、Plan / Do / Check / Act を `AGENTS.md` の用語に合わせて並べる。
- [x] Workflow セクションでは、`documents/plans/` から着手することと、小さな単位で進めることを明記する。
- [x] Quality セクションに、Frontend / Backend それぞれの品質ゲートをカードまたは 2 カラムで並べる。
- [x] Frontend 側には `npm run check`、`npm test`、`npm run build` を、Backend 側には `uv run pytest`、`uv run isort . --check-only`、`uv run yapf -dr app/` を表示内容の基準として反映する。
- [x] 終端 CTA セクションでは、ページ外へ出さず `#overview` や `#quality` に戻れる導線だけを置き、1 ページ完結の要件を守る。
- [x] ヘッダーから `進め方` と `品質` に直接飛べる導線を必ず置き、順番に依存しない読み方にも対応する。

#### 7. ルートレイアウトとメタ情報を整える

- [x] `frontend/src/routes/__root.tsx` は `Header` + `<Outlet />` の構成を維持しつつ、TanStack devtools は `RouteDevtools` を `React.lazy` + dynamic import で読み込み、`import.meta.env.DEV` のときだけ描画する。静的 import + early return にはしない。
- [x] `frontend/index.html` の `<html lang="en">` を日本語前提の設定へ更新する。
- [x] `frontend/index.html` の `<title>` と `meta[name="description"]` を、トップページの訴求内容と一致する文言へ変更する。
- [x] `frontend/index.html` に `og:title`、`og:description`、`og:image`、`og:type`、必要なら `twitter:card` を追加する。
- [x] `og:image` は相対 URL にせず、`%VITE_SITE_URL%/og-image.png` を使った絶対 URL とする。`VITE_SITE_URL` は production build 時の必須値として扱う。
- [x] `frontend/index.html` の `theme-color` を、今回の配色と矛盾しない色へ更新する。
- [x] `frontend/public/manifest.json` の `name` と `short_name` をテンプレート名に合わせて更新する。
- [x] `frontend/public/manifest.json` の `theme_color` と `background_color` を、トップページの基調色に合わせて更新する。
- [x] `frontend/public/site-mark.svg` を作成し、テンプレートの「backend + frontend + build の接続」を抽象化した簡素な geometric mark を定義する。
- [x] `frontend/public/og-card.svg` を作成し、`og-image.png` のソースにする。
- [x] PNG 生成に新しい npm 依存は追加しない。`site-mark.svg` と `og-card.svg` からの raster export は、利用可能なローカルツール（優先: `rsvg-convert`、代替: `qlmanage` / Preview）で行う。
- [x] `frontend/public/favicon.ico`、`logo192.png`、`logo512.png` を `site-mark.svg` ベースの資産へ差し替える。
- [x] `frontend/public/og-image.png` を `og-card.svg` から出力し、`1200x630` 相当の OGP 画像として用意する。
- [x] `frontend/.env.production.example` に `VITE_SITE_URL=https://example.com` を記載し、OGP の絶対 URL 用の値であることを明記する。
- [x] `frontend/src/routes/index.tsx` の `logo.svg` import など、TanStack 初期トップページ由来の不要参照を削除する。

#### 8. テストと品質確認を行う

- [x] `frontend/src/components/organisms/LandingPage/index.test.tsx` を作成し、`index.data.ts` のアンカー定義を基準に、各 section の `id` と CTA / nav の `href` が一致することを確認する。
- [x] `LandingPage` テストでは、主要 section の存在だけでなく、header / hero / final CTA が同じアンカー定義を参照している不変条件を確認する。
- [x] `LandingPage` テストに、各 section の `aria-labelledby` が存在し、対応する見出し要素の `id` を指していることを追加する。
- [x] `LandingPage` のテストは `// @vitest-environment jsdom` を使い、追加の Vitest 設定を最小限に留める。
- [x] `frontend/src/components/organisms/Header/index.test.tsx` を作成し、アンカーナビの表示、メニュー open / close、リンク押下時の close、`Escape` close、`aria-expanded` / `aria-controls` の連動を確認する。
- [x] `frontend/index.html` と `frontend/public/manifest.json` の更新内容は、meta と asset path が噛み合っていることを目視で確認する。
- [x] `frontend/.env.production.example` と `index.html` の `%VITE_SITE_URL%` 展開前提が噛み合っていることを確認する。
- [x] ブラウザ確認として `375px`、`768px`、`1280px` の 3 幅でトップページを開き、横スクロール、文字潰れ、CTA のタップ領域、SVG ダイアグラムの可読性を確認する。
- [x] `cd frontend && npm test` を実行し、新規テストを含めて Vitest が通ることを確認する。
- [x] `cd frontend && npm run check` を実行し、Prettier / ESLint の整形後に差分が意図したものだけになっていることを確認する。
- [x] `cd frontend && npm run build` を実行し、ビルドが成功し `backend/static/` への出力まで通ることを確認する。
- [x] トップページ本文で Docker を訴求した場合は `docker compose up --build` を実行し、Frontend と `GET /api/healthz` が立ち上がることを確認する。
- [ ] `cd backend && uv run pytest` を実行し、frontend 改修のみでもリポジトリ全体の品質ゲートを満たしていることを確認する。現時点では `backend/pyproject.toml` の dev dependencies に `pytest` が含まれておらず、`uv run pytest` は `Failed to spawn: pytest` で未実行。
- [x] `cd backend && uv run isort . --check-only` と `cd backend && uv run yapf -dr app/` を実行し、backend 側の lint / format 状態にも問題がないことを確認する。

### 完了条件

- `/` を開いたときに、TanStack 初期トップページ由来の回転ロゴ、学習リンク、濃いダーク背景、サンプル文言が表示されない。
- ブラウザタブ、favicon、PWA icon、OGP 画像に TanStack 初期資産が残っていない。
- トップページの情報が、**概要 -> 構成 -> 進め方 -> 品質** の順に一貫して読め、かつヘッダーから `進め方` / `品質` に直接移動できる。
- ヘッダーと主要 CTA が、すべてページ内アンカーで正しく移動できる。
- `frontend/index.html`、`frontend/public/manifest.json`、OGP 設定、icon asset の文言と見た目がトップページの訴求と一致している。
- `og:image` が production で絶対 URL になる前提が、`VITE_SITE_URL` を通じて担保されている。
- landing page の色が既存 shadcn token と競合せず、`--primary` を上書きしていない。
- `DESIGN.md` の余白・密度・タイポグラフィ方針を参考にしつつ、外部ブランド色に依存しない見た目になっている。
- `375px`、`768px`、`1280px` で横スクロールが出ず、CTA の高さが 44px を下回らず、構成図が読める。
- `prefers-reduced-motion` 環境で smooth scroll や不要な transition が強制されない。
- Docker を本文で訴求した場合は、`docker compose up --build` による起動確認まで通っている。
- `npm test`、`npm run check`、`npm run build`、`uv run pytest`、`uv run isort . --check-only`、`uv run yapf -dr app/` がすべて通る。
