type SectionIntroProps = {
  description: string
  headingId: string
  label: string
  title: string
}

const SectionIntro = ({
  description,
  headingId,
  label,
  title,
}: SectionIntroProps) => {
  return (
    <div className="max-w-3xl space-y-4">
      <p className="landing-eyebrow">{label}</p>
      <div className="space-y-3">
        <h2 className="landing-section-title" id={headingId}>
          {title}
        </h2>
        <p className="landing-copy">{description}</p>
      </div>
    </div>
  )
}

export default SectionIntro
