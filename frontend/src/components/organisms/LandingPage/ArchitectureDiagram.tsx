const ArchitectureDiagram = () => {
  return (
    <div
      className="landing-diagram-frame"
      role="img"
      aria-label="frontend と backend と build 出力の関係図"
    >
      <svg
        className="h-auto w-full"
        viewBox="0 0 640 280"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient
            id="landing-card-glow"
            x1="0%"
            x2="100%"
            y1="0%"
            y2="100%"
          >
            <stop offset="0%" stopColor="var(--landing-surface)" />
            <stop offset="100%" stopColor="#eef4ff" />
          </linearGradient>
        </defs>

        <rect fill="url(#landing-card-glow)" height="280" rx="24" width="640" />

        <g fill="none" stroke="var(--landing-line)" strokeDasharray="4 6">
          <line x1="276" x2="276" y1="54" y2="226" />
          <line x1="364" x2="364" y1="54" y2="226" />
        </g>

        <g
          fill="var(--landing-surface)"
          stroke="var(--landing-ink)"
          strokeWidth="2"
        >
          <rect height="68" rx="18" width="174" x="58" y="44" />
          <rect height="68" rx="18" width="174" x="58" y="168" />
        </g>

        <g
          fill="var(--landing-surface)"
          stroke="var(--landing-accent)"
          strokeWidth="2.5"
        >
          <rect height="82" rx="20" width="182" x="398" y="99" />
        </g>

        <g
          fill="none"
          stroke="var(--landing-accent)"
          strokeLinecap="round"
          strokeWidth="4"
        >
          <line x1="232" x2="320" y1="78" y2="78" />
          <line x1="232" x2="320" y1="202" y2="202" />
          <line x1="320" x2="320" y1="78" y2="202" />
          <line x1="320" x2="398" y1="140" y2="140" />
        </g>

        <g
          fill="var(--landing-ink)"
          fontFamily="Helvetica Neue, Arial, Noto Sans JP, sans-serif"
        >
          <text fontSize="13" letterSpacing="1.2" x="78" y="72">
            フロントエンド
          </text>
          <text fontSize="26" fontWeight="700" x="78" y="102">
            React + Vite
          </text>
          <text fill="var(--landing-muted)" fontSize="14" x="78" y="126">
            UI 実装と build を担当
          </text>

          <text fontSize="13" letterSpacing="1.2" x="78" y="196">
            バックエンド
          </text>
          <text fontSize="26" fontWeight="700" x="78" y="226">
            FastAPI
          </text>
          <text fill="var(--landing-muted)" fontSize="14" x="78" y="250">
            API と CLI を担当
          </text>
        </g>

        <g
          fill="var(--landing-accent)"
          fontFamily="Helvetica Neue, Arial, Noto Sans JP, sans-serif"
        >
          <text
            fontSize="13"
            fontWeight="700"
            letterSpacing="1.2"
            x="424"
            y="130"
          >
            ビルド出力
          </text>
          <text fontSize="26" fontWeight="700" x="424" y="162">
            backend/static/
          </text>
          <text fill="var(--landing-muted)" fontSize="14" x="424" y="188">
            frontend の成果物を集約し、そのまま配信
          </text>
        </g>
      </svg>
    </div>
  )
}

export default ArchitectureDiagram
