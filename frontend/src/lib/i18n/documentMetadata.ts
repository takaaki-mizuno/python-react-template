import i18n from './i18n'

type MetadataKey = {
  titleKey: MetadataTranslationKey
  descriptionKey: MetadataTranslationKey
}

type MetadataTranslationKey =
  | 'landing:metadata.title'
  | 'landing:metadata.description'
  | 'auth:metadata.loginTitle'
  | 'auth:metadata.loginDescription'
  | 'auth:metadata.registerTitle'
  | 'auth:metadata.registerDescription'
  | 'app:metadata.settingsTitle'
  | 'app:metadata.settingsDescription'
  | 'app:metadata.appTitle'
  | 'app:metadata.appDescription'
  | 'admin:metadata.usersTitle'
  | 'admin:metadata.usersDescription'
  | 'admin:metadata.adminTitle'
  | 'admin:metadata.adminDescription'
  | 'common:metadata.defaultTitle'
  | 'common:metadata.defaultDescription'

const metadataByRoute: Array<[RegExp, MetadataKey]> = [
  [
    /^\/(en|ja)\/?$/,
    {
      titleKey: 'landing:metadata.title',
      descriptionKey: 'landing:metadata.description',
    },
  ],
  [
    /^\/(en|ja)\/login\/?$/,
    {
      titleKey: 'auth:metadata.loginTitle',
      descriptionKey: 'auth:metadata.loginDescription',
    },
  ],
  [
    /^\/(en|ja)\/register\/?$/,
    {
      titleKey: 'auth:metadata.registerTitle',
      descriptionKey: 'auth:metadata.registerDescription',
    },
  ],
  [
    /^\/app\/settings\/?$/,
    {
      titleKey: 'app:metadata.settingsTitle',
      descriptionKey: 'app:metadata.settingsDescription',
    },
  ],
  [
    /^\/app\/?$/,
    {
      titleKey: 'app:metadata.appTitle',
      descriptionKey: 'app:metadata.appDescription',
    },
  ],
  [
    /^\/admin\/users\/?$/,
    {
      titleKey: 'admin:metadata.usersTitle',
      descriptionKey: 'admin:metadata.usersDescription',
    },
  ],
  [
    /^\/admin\/?$/,
    {
      titleKey: 'admin:metadata.adminTitle',
      descriptionKey: 'admin:metadata.adminDescription',
    },
  ],
]

export function syncDocumentMetadata(pathname: string): void {
  document.documentElement.lang = i18n.resolvedLanguage ?? i18n.language

  const metadata = metadataByRoute.find(([pattern]) =>
    pattern.test(pathname),
  )?.[1]
  document.title = translateKey(
    metadata?.titleKey ?? 'common:metadata.defaultTitle',
  )

  const description = translateKey(
    metadata?.descriptionKey ?? 'common:metadata.defaultDescription',
  )
  let descriptionMeta = document.querySelector<HTMLMetaElement>(
    'meta[name="description"]',
  )
  if (!descriptionMeta) {
    descriptionMeta = document.createElement('meta')
    descriptionMeta.name = 'description'
    document.head.append(descriptionMeta)
  }
  descriptionMeta.content = description
}

function translateKey(key: MetadataTranslationKey): string {
  return i18n.t(key)
}
