type InfoCardProps = {
  description: string
  items?: ReadonlyArray<string>
  title: string
}

const InfoCard = ({ description, items, title }: InfoCardProps) => {
  return (
    <article className="landing-card">
      <div className="space-y-3">
        <h3 className="landing-card-title">{title}</h3>
        <p className="landing-card-copy">{description}</p>
      </div>

      {items && items.length > 0 ? (
        <ul className="space-y-2 border-t border-landing-line pt-4 text-sm text-landing-muted">
          {items.map((item) => (
            <li className="flex items-start gap-2" key={item}>
              <span
                aria-hidden="true"
                className="mt-1.5 size-1.5 rounded-full bg-landing-accent"
              />
              <code className="font-medium text-landing-ink">{item}</code>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  )
}

export default InfoCard
