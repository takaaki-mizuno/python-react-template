import i18next from 'i18next'
import { initReactI18next } from 'react-i18next'

import { defaultLanguage } from './languages'
import { defaultNamespace, resources } from './resources'
import { readLastResolvedLanguage } from './storage'

export const i18n = i18next.createInstance()

void i18n.use(initReactI18next).init({
  resources,
  lng: readLastResolvedLanguage() ?? defaultLanguage,
  fallbackLng: defaultLanguage,
  defaultNS: defaultNamespace,
  ns: ['common', 'auth', 'landing', 'app', 'admin'],
  interpolation: {
    escapeValue: false,
  },
})

export default i18n
