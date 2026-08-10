import { ArrowRight, CheckCircle2 } from 'lucide-react'

import ArchitectureDiagram from './ArchitectureDiagram'
import InfoCard from './InfoCard'
import SectionIntro from './SectionIntro'
import {
  architectureSection,
  finalSection,
  heroContent,
  overviewCards,
  overviewSection,
  qualitySection,
  sectionHeadingIds,
  workflowSection,
} from './data'
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
const tabSummaries = {
  overview: '初期構成で何が揃うかを確認する。',
  architecture: 'frontend / backend / static 配信の接続点を見る。',
  workflow: 'Plan から Act までの作業順を確認する。',
  quality: '変更前後に通す確認ゲートを把握する。',
} as const

const LandingPage = () => {
  return (
    <main id="top">
      <section className="border-b py-12 md:py-16 lg:py-20">
        <div className={pageShell}>
          <div className="grid gap-8 lg:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)] lg:items-end">
            <div className="space-y-8">
              <div className="space-y-5">
                <Badge variant="outline">{heroContent.eyebrow}</Badge>
                <h1 className="max-w-4xl text-4xl font-semibold leading-tight tracking-tight text-foreground sm:text-5xl lg:text-6xl">
                  {heroContent.title}
                </h1>
                <p className="max-w-2xl text-lg leading-8 text-muted-foreground">
                  {heroContent.description}
                </p>
              </div>

              <div className="flex flex-wrap gap-3">
                {heroContent.actions.map((action) => (
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
                    このテンプレートの要点
                  </h2>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-4">
                    {heroContent.signalLines.map((line) => (
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
            <TabsList aria-label="ページ概要">
              <TabsTrigger value="overview">概要</TabsTrigger>
              <TabsTrigger value="architecture">構成</TabsTrigger>
              <TabsTrigger value="workflow">進め方</TabsTrigger>
              <TabsTrigger value="quality">品質</TabsTrigger>
            </TabsList>
            <TabsContent value="overview">
              <p className="max-w-2xl text-sm leading-7 text-muted-foreground">
                {tabSummaries.overview}
              </p>
            </TabsContent>
            <TabsContent value="architecture">
              <p className="max-w-2xl text-sm leading-7 text-muted-foreground">
                {tabSummaries.architecture}
              </p>
            </TabsContent>
            <TabsContent value="workflow">
              <p className="max-w-2xl text-sm leading-7 text-muted-foreground">
                {tabSummaries.workflow}
              </p>
            </TabsContent>
            <TabsContent value="quality">
              <p className="max-w-2xl text-sm leading-7 text-muted-foreground">
                {tabSummaries.quality}
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
            description={overviewSection.description}
            headingId={sectionHeadingIds.overview}
            label={overviewSection.label}
            title={overviewSection.title}
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
              description={architectureSection.description}
              headingId={sectionHeadingIds.architecture}
              label={architectureSection.label}
              title={architectureSection.title}
            />

            <ul className="grid gap-3">
              {architectureSection.highlights.map((highlight) => (
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
            description={workflowSection.description}
            headingId={sectionHeadingIds.workflow}
            label={workflowSection.label}
            title={workflowSection.title}
          />

          <ol className="grid gap-4">
            {workflowSection.steps.map((step, index) => (
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
            description={qualitySection.description}
            headingId={sectionHeadingIds.quality}
            label={qualitySection.label}
            title={qualitySection.title}
          />

          <div className="grid gap-4 lg:grid-cols-2">
            {qualitySection.groups.map((group) => (
              <InfoCard
                description={group.summary}
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
                <Badge variant="outline">{finalSection.eyebrow}</Badge>
                <h2 className="text-3xl font-semibold tracking-tight">
                  {finalSection.title}
                </h2>
                <p className="max-w-2xl text-base leading-7 text-muted-foreground">
                  {finalSection.description}
                </p>
              </div>

              <Separator className="lg:hidden" />

              <div className="flex flex-wrap gap-3">
                {finalSection.actions.map((action) => (
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
