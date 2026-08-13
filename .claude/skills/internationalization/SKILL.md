---
name: internationalization
description: Use when implementing, reviewing, debugging, or extending i18n/l10n behavior in this FastAPI + React template, including translated UI text, locale routing, language switching, user language preference, locale JSON files, metadata lang/title/description, or adding a new supported language.
---

# Internationalization

## Overview

Use the repository's existing i18n architecture. Public pages use URL locale, authenticated pages use the user's DB preference, and `LanguageSyncManager` is the only writer of the current i18next language.

## Source Of Truth

| Concern | Source |
|---|---|
| Translation text | `frontend/src/lib/i18n/locales/{ja,en}/*.json` |
| Translation aggregation | `frontend/src/lib/i18n/resources.ts` |
| Frontend language type/options | `frontend/src/lib/i18n/languages.ts` |
| Current language sync | `frontend/src/lib/i18n/LanguageSyncManager.tsx` |
| Public locale helpers | `frontend/src/lib/i18n/publicLocale.ts` |
| Storage hints | `frontend/src/lib/i18n/storage.ts` |
| Backend language constants | `backend/app/models/language.py` |
| User DB preference | `users.language_code` |

## Routing Rules

- Public routes are locale-prefixed: `/ja/`, `/en/`, `/ja/login`, `/en/register`.
- Authenticated routes are not locale-prefixed: `/app`, `/app/settings`, `/admin/...`.
- Legacy `/`, `/login`, and `/register` are canonicalized by `frontend/src/routes/{-$locale}.tsx`.
- Do not recreate static `routes/index.tsx`, `routes/login.tsx`, or `routes/register.tsx`; page modules live under `routes/-login.tsx` and `routes/-register.tsx`.
- `RouterProvider` does not accept children. Components that need router context, query cache, and global rendering belong in `frontend/src/routes/__root.tsx`.

## Current Language Rules

- `LanguageSyncManager` is the only code that calls `i18n.changeLanguage()` for normal app language state.
- Mutation handlers, login/register handlers, and UI components update cache, URL, or storage only; they must not call `i18n.changeLanguage()` directly.
- Resolution order is: public URL locale -> authenticated `user.language_code` -> `app.publicLanguage` -> `app.lastResolvedLanguage` -> browser language -> default language.
- Use `resolveLanguage(pathname, user?.language_code ?? null)` when Header or non-manager code needs the displayed current language.
- Clear `app.lastResolvedLanguage` on logout and account deletion so a previous authenticated user's DB language does not leak into the next anonymous session.

## Translation Rules

- Do not hardcode new UI text in components or routes. Add keys to the correct namespace: `common`, `auth`, `landing`, `app`, or `admin`.
- Keep every JSON locale file structurally identical between `ja` and `en`.
- Use natural UI copy, not mechanical word-for-word translation.
- React components should use `useTranslation()`.
- Pure utilities should import the i18n instance from `frontend/src/lib/i18n/i18n.ts`; do not use React hooks outside components.
- Date/number formatting belongs in `frontend/src/lib/i18n/formatters.ts`; do not inline `Intl.DateTimeFormat('ja-JP')` in screens.

## Backend Rules

- Backend public JSON uses snake_case: `language_code`.
- Backend model and DB fields use snake_case: `language_code`.
- `GET /api/auth/me`, password login, register, and OIDC login responses include `language_code`.
- `PATCH /api/auth/me` updates authenticated user language. Explicit `null` and unsupported codes are 422; empty body is no-op 200.
- Register accepts optional `language_code`; missing value defaults to `ja`.
- OIDC start accepts optional `language_code` only to seed auto-provisioned users. It must not overwrite existing users or account deletion reauth state.

## Adding A New Language

Update all of these in the same change:

- `backend/app/models/language.py`
- `backend/alembic/versions/20260810_0001_initial_schema.py` CHECK constraints for `users.language_code` and `auth_oidc_authorization_states.language_code`
- frontend `LanguageCode`, `languageOptions`, and formatter locale map
- every `frontend/src/lib/i18n/locales/{language}/*.json` namespace
- `resources.ts` and i18next typings
- tests that check language codes, resource parity, DB schema, auth API payloads, and UI language switching

If the initial migration has already been applied in a downstream project, stop and ask before editing the squashed initial revision.

## Required Verification

Use focused tests first, then the broader gates that match the change:

```bash
cd frontend && rtk npm test -- src/lib/i18n
cd frontend && rtk npm test -- src/routes/login.test.tsx src/routes/register.test.tsx src/routes/app.settings.test.tsx
cd frontend && rtk npm run check:ci
cd frontend && rtk npm test
cd frontend && rtk npm run build
cd backend && rtk uv run pytest tests/unit -q
cd backend && rtk env TEST_DATABASE_URL=<fresh-postgres-test-db> uv run pytest tests/integration -q -ra
```

For backend integration schema work, prefer a fresh PostgreSQL test DB. A stale `app_test` can hide or falsely report constraints when the initial migration was rewritten.

## Common Mistakes

- Adding a translation key to `ja` but not `en`.
- Calling `i18n.changeLanguage()` from a mutation hook or form handler.
- Letting authenticated `user.language_code` win on public localized pages.
- Writing account deletion or logout flows that leave `app.lastResolvedLanguage` behind.
- Adding locale-prefixed authenticated URLs.
- Updating frontend language options without backend CHECK constraints and OIDC state language validation.
