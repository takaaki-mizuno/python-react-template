import { Card, CardContent, CardHeader } from '@/components/atoms/card'
import { Badge } from '@/components/atoms/badge'
import { Separator } from '@/components/atoms/separator'

type InfoCardProps = {
  description: string
  items?: ReadonlyArray<string>
  title: string
}

const InfoCard = ({ description, items, title }: InfoCardProps) => {
  return (
    <Card className="h-full">
      <CardHeader>
        <h3 className="text-base leading-6 font-semibold">{title}</h3>
      </CardHeader>
      <CardContent className="grid gap-5">
        <p className="text-sm leading-7 text-muted-foreground">{description}</p>

        {items && items.length > 0 ? (
          <>
            <Separator />
            <ul className="grid gap-2">
              {items.map((item) => (
                <li className="flex items-center gap-2" key={item}>
                  <Badge variant="outline">
                    <code className="font-mono text-[11px]">{item}</code>
                  </Badge>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}

export default InfoCard
