import { Badge } from '@/components/atoms/badge'

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
      <Badge variant="outline">{label}</Badge>
      <div className="space-y-3">
        <h2
          className="text-3xl font-semibold tracking-tight text-foreground md:text-4xl"
          id={headingId}
        >
          {title}
        </h2>
        <p className="text-base leading-7 text-muted-foreground">
          {description}
        </p>
      </div>
    </div>
  )
}

export default SectionIntro
