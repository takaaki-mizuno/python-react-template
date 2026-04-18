import AnchorButton from './AnchorButton'
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
} from '@/routes/index.data'

const LandingPage = () => {
  return (
    <main className="landing-page" id="top">
      <section className="landing-hero">
        <div className="landing-shell">
          <div className="landing-hero-grid">
            <div className="space-y-8">
              <div className="space-y-4">
                <p className="landing-eyebrow">{heroContent.eyebrow}</p>
                <h1 className="landing-hero-title">{heroContent.title}</h1>
                <p className="landing-hero-copy">{heroContent.description}</p>
              </div>

              <div className="flex flex-wrap gap-3">
                {heroContent.actions.map((action) => (
                  <AnchorButton
                    href={action.href}
                    key={action.href}
                    label={action.label}
                    variant={action.variant}
                  />
                ))}
              </div>
            </div>

            <aside
              className="landing-signal-panel"
              aria-label="テンプレートの特徴"
            >
              <p className="landing-panel-label">このテンプレートの要点</p>
              <ul className="space-y-4">
                {heroContent.signalLines.map((line) => (
                  <li className="landing-panel-line" key={line}>
                    <span aria-hidden="true" className="landing-panel-dot" />
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </aside>
          </div>
        </div>
      </section>

      <section
        aria-labelledby={sectionHeadingIds.overview}
        className="landing-section"
        id="overview"
      >
        <div className="landing-shell space-y-8">
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
        className="landing-section"
        id="architecture"
      >
        <div className="landing-shell grid gap-8 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] xl:items-start">
          <div className="space-y-8">
            <SectionIntro
              description={architectureSection.description}
              headingId={sectionHeadingIds.architecture}
              label={architectureSection.label}
              title={architectureSection.title}
            />

            <ul className="space-y-3">
              {architectureSection.highlights.map((highlight) => (
                <li className="landing-detail-item" key={highlight}>
                  <span aria-hidden="true" className="landing-panel-dot" />
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
        className="landing-section"
        id="workflow"
      >
        <div className="landing-shell grid gap-8 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
          <SectionIntro
            description={workflowSection.description}
            headingId={sectionHeadingIds.workflow}
            label={workflowSection.label}
            title={workflowSection.title}
          />

          <ol className="space-y-4">
            {workflowSection.steps.map((step, index) => (
              <li className="landing-step" key={step.key}>
                <div className="landing-step-index">{index + 1}</div>
                <div className="space-y-2">
                  <h3 className="landing-card-title">{step.key}</h3>
                  <p className="landing-card-copy">{step.description}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section
        aria-labelledby={sectionHeadingIds.quality}
        className="landing-section"
        id="quality"
      >
        <div className="landing-shell space-y-8">
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

      <section className="landing-section border-b-0">
        <div className="landing-shell">
          <div className="landing-final-panel">
            <div className="space-y-3">
              <p className="landing-eyebrow">{finalSection.eyebrow}</p>
              <h2 className="landing-section-title">{finalSection.title}</h2>
              <p className="landing-copy">{finalSection.description}</p>
            </div>

            <div className="flex flex-wrap gap-3">
              {finalSection.actions.map((action) => (
                <AnchorButton
                  href={action.href}
                  key={action.href}
                  label={action.label}
                  variant={action.variant}
                />
              ))}
            </div>
          </div>
        </div>
      </section>
    </main>
  )
}

export default LandingPage
