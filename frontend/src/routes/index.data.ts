export const landingSectionIds = [
  'overview',
  'architecture',
  'workflow',
  'quality',
] as const

export type LandingSectionId = (typeof landingSectionIds)[number]

export const sectionHeadingIds: Record<LandingSectionId, string> = {
  overview: 'overview-heading',
  architecture: 'architecture-heading',
  workflow: 'workflow-heading',
  quality: 'quality-heading',
}

export const landingNavigation = landingSectionIds.map((id) => ({
  id,
  href: `#${id}` as const,
  label:
    id === 'overview'
      ? '概要'
      : id === 'architecture'
        ? '構成'
        : id === 'workflow'
          ? '進め方'
          : '品質',
}))

export const heroContent = {
  eyebrow: '実用的なモノレポ構成',
  title: 'FastAPI と React を、すぐ動かせる実用的なモノレポ',
  description:
    'backend と frontend の責務を分けつつ、build と配信、計画駆動、品質ゲートまでひとつに揃えた開発基盤です。AI エージェント込みの開発でも、構成と手順がぶれにくいことを重視しています。',
  actions: [
    {
      href: '#architecture',
      label: '構成を見る',
      variant: 'primary' as const,
    },
    {
      href: '#workflow',
      label: '進め方を見る',
      variant: 'secondary' as const,
    },
  ],
  signalLines: [
    'backend / frontend の責務を分離',
    'frontend build を backend/static/ へ出力',
    '計画駆動と品質ゲートを最初から定義',
  ],
}

export const overviewSection = {
  label: '概要',
  title: 'このテンプレートで最初から揃うもの',
  description:
    '採用判断に必要な要素だけを、実装の現実に沿って短く整理しています。単なる技術スタック紹介ではなく、開発基盤としてのつながりが見える構成にします。',
}

export const overviewCards = [
  {
    title: 'バックエンド',
    description:
      'FastAPI を中心に、API と CLI を backend/ にまとめて育てられます。',
  },
  {
    title: 'フロントエンド',
    description:
      'React + Vite をベースに、型安全を保ちながら UI を素早く組み立てられます。',
  },
  {
    title: '配信フロー',
    description:
      'frontend build を backend/static/ に出力し、そのまま backend から配信できます。',
  },
  {
    title: '開発ルール',
    description:
      'AGENTS.md と documents/plans/ を起点に、計画駆動で進められる土台があります。',
  },
] as const

export const architectureSection = {
  label: '構成',
  title: '役割分担と接続点がひと目でわかる構成',
  description:
    'frontend、backend、build output の関係を先に見せることで、導入後にどこを触るのかがすぐに想像できるようにします。',
  highlights: [
    'frontend/ は React + Vite の UI 実装を担当する',
    'backend/ は FastAPI の API と CLI を担当する',
    'build 時には frontend の成果物が backend/static/ に集約される',
  ],
}

export const workflowSection = {
  label: '進め方',
  title: 'このテンプレートでの進め方',
  description:
    'ページ後半では、導入後の開発フローまで短く見せます。AI エージェントが入っても判断基準がぶれにくいよう、Plan から Act までを明示します。',
  steps: [
    {
      key: 'Plan',
      description:
        'まず documents/plans/ にやることと影響範囲を書いてから着手する。',
    },
    {
      key: 'Do',
      description:
        'backend と frontend の責務を分け、小さな単位で実装を進める。',
    },
    {
      key: 'Check',
      description: 'test、lint、build を通してから完了を判断する。',
    },
    {
      key: 'Act',
      description: '学びを計画書やガイドへ戻し、次の開発に反映する。',
    },
  ],
}

export const qualitySection = {
  label: '品質',
  title: '品質ゲートを最初から揃える',
  description:
    '紹介ページとして終わらせず、実際に触るときの確認項目まで見せることで、採用時の不安を減らします。',
  groups: [
    {
      title: 'フロントエンドの確認',
      summary:
        '整形、Lint、テスト、build をひと通り通して UI 変更の破綻を防ぐ。',
      items: ['npm run check', 'npm test', 'npm run build'],
    },
    {
      title: 'バックエンドの確認',
      summary:
        'テストと formatter / import order まで確認し、frontend 改修後も全体の健全性を保つ。',
      items: [
        'uv run pytest',
        'uv run isort . --check-only',
        'uv run yapf -dr app/',
      ],
    },
  ],
} as const

export const finalSection = {
  title: '必要な情報へすぐ戻れるようにする',
  description:
    '主要 CTA はページ内アンカーに限定し、トップページだけで構成・進め方・品質を往復できるようにします。',
  eyebrow: 'ページ内ナビゲーション',
  actions: [
    {
      href: '#overview',
      label: '概要に戻る',
      variant: 'secondary' as const,
    },
    {
      href: '#quality',
      label: '品質を見る',
      variant: 'primary' as const,
    },
  ],
}
