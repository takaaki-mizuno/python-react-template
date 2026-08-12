import { useTranslation } from 'react-i18next'

import { Card, CardContent } from '@/components/atoms/card'

const ArchitectureDiagram = () => {
  const { t } = useTranslation('landing')

  return (
    <Card role="img" aria-label={t('architecture.diagram.label')}>
      <CardContent>
        <svg
          className="h-auto w-full"
          viewBox="0 0 640 280"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <linearGradient id="card-glow" x1="0%" x2="100%" y1="0%" y2="100%">
              <stop offset="0%" stopColor="var(--card)" />
              <stop offset="100%" stopColor="var(--muted)" />
            </linearGradient>
          </defs>

          <rect fill="url(#card-glow)" height="280" rx="24" width="640" />

          <g fill="none" stroke="var(--border)" strokeDasharray="4 6">
            <line x1="276" x2="276" y1="54" y2="226" />
            <line x1="364" x2="364" y1="54" y2="226" />
          </g>

          <g fill="var(--card)" stroke="var(--foreground)" strokeWidth="2">
            <rect height="68" rx="18" width="174" x="58" y="44" />
            <rect height="68" rx="18" width="174" x="58" y="168" />
          </g>

          <g fill="var(--card)" stroke="var(--primary)" strokeWidth="2.5">
            <rect height="82" rx="20" width="182" x="398" y="99" />
          </g>

          <g
            fill="none"
            stroke="var(--primary)"
            strokeLinecap="round"
            strokeWidth="4"
          >
            <line x1="232" x2="320" y1="78" y2="78" />
            <line x1="232" x2="320" y1="202" y2="202" />
            <line x1="320" x2="320" y1="78" y2="202" />
            <line x1="320" x2="398" y1="140" y2="140" />
          </g>

          <g
            fill="var(--foreground)"
            fontFamily="Helvetica Neue, Arial, Noto Sans JP, sans-serif"
          >
            <text fontSize="13" letterSpacing="1.2" x="78" y="72">
              {t('architecture.diagram.frontendLabel')}
            </text>
            <text fontSize="26" fontWeight="700" x="78" y="102">
              React + Vite
            </text>
            <text fill="var(--muted-foreground)" fontSize="14" x="78" y="126">
              {t('architecture.diagram.frontendDescription')}
            </text>

            <text fontSize="13" letterSpacing="1.2" x="78" y="196">
              {t('architecture.diagram.backendLabel')}
            </text>
            <text fontSize="26" fontWeight="700" x="78" y="226">
              FastAPI
            </text>
            <text fill="var(--muted-foreground)" fontSize="14" x="78" y="250">
              {t('architecture.diagram.backendDescription')}
            </text>
          </g>

          <g
            fill="var(--primary)"
            fontFamily="Helvetica Neue, Arial, Noto Sans JP, sans-serif"
          >
            <text
              fontSize="13"
              fontWeight="700"
              letterSpacing="1.2"
              x="424"
              y="130"
            >
              {t('architecture.diagram.outputLabel')}
            </text>
            <text fontSize="26" fontWeight="700" x="424" y="162">
              backend/static/
            </text>
            <text fill="var(--muted-foreground)" fontSize="14" x="424" y="188">
              {t('architecture.diagram.outputDescription')}
            </text>
          </g>
        </svg>
      </CardContent>
    </Card>
  )
}

export default ArchitectureDiagram
