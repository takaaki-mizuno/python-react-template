import adminEn from './locales/en/admin.json'
import appEn from './locales/en/app.json'
import authEn from './locales/en/auth.json'
import commonEn from './locales/en/common.json'
import landingEn from './locales/en/landing.json'
import adminJa from './locales/ja/admin.json'
import appJa from './locales/ja/app.json'
import authJa from './locales/ja/auth.json'
import commonJa from './locales/ja/common.json'
import landingJa from './locales/ja/landing.json'

export const defaultNamespace = 'common'

export const resources = {
  ja: {
    common: commonJa,
    auth: authJa,
    landing: landingJa,
    app: appJa,
    admin: adminJa,
  },
  en: {
    common: commonEn,
    auth: authEn,
    landing: landingEn,
    app: appEn,
    admin: adminEn,
  },
} as const
