import { ArrowRight, CheckCircle2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import ArchitectureDiagram from './ArchitectureDiagram'
import InfoCard from './InfoCard'
import SectionIntro from './SectionIntro'
import { sectionHeadingIds } from './data'
import { Badge } from '@/components/atoms/badge'
import { Button } from '@/components/atoms/button'
import { Card, CardContent, CardHeader } from '@/components/atoms/card'
import { Separator } from '@/components/atoms/separator'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/atoms/tabs'

const pageShell = 'mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8'
const sectionClass =
  'scroll-mt-[calc(var(--app-header-height)+1rem)] border-b py-12 md:py-16 lg:py-20'
const heroFeatureHeadingId = 'hero-feature-heading'

type LandingAction = {
  href: string
  label: string
  variant: 'primary' | 'secondary'
}

type InfoCardCopy = {
  description: string
  items?: Array<string>
  summary?: string
  title: string
}

type WorkflowStep = {
  description: string
  key: string
}

const LandingPage = () => {
  const { t } = useTranslation('landing')
  const heroActions = t('hero.actions', {
    returnObjects: true,
  }) as Array<LandingAction>
  const heroSignalLines = t('hero.signalLines', {
    returnObjects: true,
  })
  const overviewCards = t('overview.cards', {
    returnObjects: true,
  }) as Array<InfoCardCopy>
  const architectureHighlights = t('architecture.highlights', {
    returnObjects: true,
  })
  const workflowSteps = t('workflow.steps', {
    returnObjects: true,
  }) as Array<WorkflowStep>
  const qualityGroups = t('quality.groups', {
    returnObjects: true,
  }) as Array<InfoCardCopy>
  const finalActions = t('final.actions', {
    returnObjects: true,
  }) as Array<LandingAction>

  return (
    <main id="top">
      <section className="border-b py-12 md:py-16 lg:py-20">
        <div className={pageShell}>
          <div className="grid gap-8 lg:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)] lg:items-end">
            <div className="space-y-8">
              <div className="space-y-5">
                <Badge variant="outline">{t('hero.eyebrow')}</Badge>
                <h1 className="max-w-4xl text-4xl font-semibold leading-tight tracking-tight text-foreground sm:text-5xl lg:text-6xl">
                  {t('hero.title')}
                </h1>
                <p className="max-w-2xl text-lg leading-8 text-muted-foreground">
                  {t('hero.description')}
                </p>
              </div>

              <div className="flex flex-wrap gap-3">
                {heroActions.map((action) => (
                  <Button
                    asChild
                    key={action.href}
                    variant={
                      action.variant === 'secondary' ? 'outline' : 'default'
                    }
                  >
                    <a href={action.href}>
                      {action.label}
                      <ArrowRight className="size-4" aria-hidden="true" />
                    </a>
                  </Button>
                ))}
              </div>
            </div>

            <aside aria-labelledby={heroFeatureHeadingId}>
              <Card>
                <CardHeader>
                  <h2
                    className="text-base font-semibold"
                    id={heroFeatureHeadingId}
                  >
                    {t('hero.featureTitle')}
                  </h2>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-4">
                    {heroSignalLines.map((line) => (
                      <li
                        className="flex items-start gap-3 text-sm leading-6"
                        key={line}
                      >
                        <CheckCircle2
                          aria-hidden="true"
                          className="mt-0.5 size-4 shrink-0 text-primary"
                        />
                        <span>{line}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            </aside>
          </div>

          <Tabs className="mt-10" defaultValue="overview">
            <TabsList aria-label={t('tabs.label')}>
              <TabsTrigger value="overview">
                {t('navigation.overview')}
              </TabsTrigger>
              <TabsTrigger value="architecture">
                {t('navigation.architecture')}
              </TabsTrigger>
              <TabsTrigger value="workflow">
                {t('navigation.workflow')}
              </TabsTrigger>
              <TabsTrigger value="quality">
                {t('navigation.quality')}
              </TabsTrigger>
            </TabsList>
            <TabsContent value="overview">
              <p className="max-w-2xl text-sm leading-7 text-muted-foreground">
                {t('tabs.overview')}
              </p>
            </TabsContent>
            <TabsContent value="architecture">
              <p className="max-w-2xl text-sm leading-7 text-muted-foreground">
                {t('tabs.architecture')}
              </p>
            </TabsContent>
            <TabsContent value="workflow">
              <p className="max-w-2xl text-sm leading-7 text-muted-foreground">
                {t('tabs.workflow')}
              </p>
            </TabsContent>
            <TabsContent value="quality">
              <p className="max-w-2xl text-sm leading-7 text-muted-foreground">
                {t('tabs.quality')}
              </p>
            </TabsContent>
          </Tabs>
        </div>
      </section>

      <section
        aria-labelledby={sectionHeadingIds.overview}
        className={sectionClass}
        id="overview"
      >
        <div className={`${pageShell} space-y-8`}>
          <SectionIntro
            description={t('overview.description')}
            headingId={sectionHeadingIds.overview}
            label={t('overview.label')}
            title={t('overview.title')}
          />

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {overviewCards.map((card) => (
              <InfoCard
                description={card.description}
                key={card.title}
                title={card.title}
              />
            ))}
          </div>
        </div>
      </section>

      <section
        aria-labelledby={sectionHeadingIds.architecture}
        className={sectionClass}
        id="architecture"
      >
        <div
          className={`${pageShell} grid gap-8 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] xl:items-start`}
        >
          <div className="space-y-8">
            <SectionIntro
              description={t('architecture.description')}
              headingId={sectionHeadingIds.architecture}
              label={t('architecture.label')}
              title={t('architecture.title')}
            />

            <ul className="grid gap-3">
              {architectureHighlights.map((highlight) => (
                <li
                  className="flex items-start gap-3 rounded-lg border bg-card p-4 text-sm leading-6"
                  key={highlight}
                >
                  <CheckCircle2
                    aria-hidden="true"
                    className="mt-0.5 size-4 shrink-0 text-primary"
                  />
                  <span>{highlight}</span>
                </li>
              ))}
            </ul>
          </div>

          <ArchitectureDiagram />
        </div>
      </section>

      <section
        aria-labelledby={sectionHeadingIds.workflow}
        className={sectionClass}
        id="workflow"
      >
        <div
          className={`${pageShell} grid gap-8 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]`}
        >
          <SectionIntro
            description={t('workflow.description')}
            headingId={sectionHeadingIds.workflow}
            label={t('workflow.label')}
            title={t('workflow.title')}
          />

          <ol className="grid gap-4">
            {workflowSteps.map((step, index) => (
              <li key={step.key}>
                <Card>
                  <CardContent className="flex gap-4">
                    <Badge className="mt-1 size-8 shrink-0 rounded-full">
                      {index + 1}
                    </Badge>
                    <div className="space-y-2">
                      <h3 className="text-lg font-semibold">{step.key}</h3>
                      <p className="text-sm leading-7 text-muted-foreground">
                        {step.description}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section
        aria-labelledby={sectionHeadingIds.quality}
        className={sectionClass}
        id="quality"
      >
        <div className={`${pageShell} space-y-8`}>
          <SectionIntro
            description={t('quality.description')}
            headingId={sectionHeadingIds.quality}
            label={t('quality.label')}
            title={t('quality.title')}
          />

          <div className="grid gap-4 lg:grid-cols-2">
            {qualityGroups.map((group) => (
              <InfoCard
                description={group.summary ?? group.description}
                items={group.items}
                key={group.title}
                title={group.title}
              />
            ))}
          </div>
        </div>
      </section>

      <section className="py-12 md:py-16 lg:py-20">
        <div className={pageShell}>
          <Card>
            <CardContent className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
              <div className="space-y-3">
                <Badge variant="outline">{t('final.eyebrow')}</Badge>
                <h2 className="text-3xl font-semibold tracking-tight">
                  {t('final.title')}
                </h2>
                <p className="max-w-2xl text-base leading-7 text-muted-foreground">
                  {t('final.description')}
                </p>
              </div>

              <Separator className="lg:hidden" />

              <div className="flex flex-wrap gap-3">
                {finalActions.map((action) => (
                  <Button
                    asChild
                    key={action.href}
                    variant={
                      action.variant === 'secondary' ? 'outline' : 'default'
                    }
                  >
                    <a href={action.href}>
                      {action.label}
                      <ArrowRight className="size-4" aria-hidden="true" />
                    </a>
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </section>
    </main>
  )
}

export default LandingPage
