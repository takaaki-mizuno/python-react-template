---
name: admin-crud
description: Use when adding an admin CRUD screen, admin CRUD API, or management workflow to this FastAPI and React template.
---

# Admin CRUD

## Core Rule

Admin CRUD is a permission-gated management workflow. Backend authorization is the security boundary; Frontend guards are display and navigation helpers only.

## Backend Pattern

1. Read `backend/AGENTS.md` and the relevant `documents/plans/` entry first.
2. Put domain dataclasses and response/request schemas in `backend/app/models/`.
3. Put persistence interface in `backend/app/interfaces/services/` and implementation in `backend/app/services/`.
4. Put orchestration in `backend/app/usecases/`; transaction boundaries belong in the usecase via `UnitOfWorkInterface.transaction()`.
5. Put HTTP mapping in `backend/app/controllers/`; controllers translate domain errors into RFC 9457 Problem Details via `api_error()`.
6. Register DI bindings in `backend/app/bootstrap/modules.py` and routers in `backend/app/bootstrap/route.py`.
7. Protect every admin endpoint with `require_permission("admin:access")` unless a plan explicitly introduces a narrower permission.
8. For admin list APIs, prefer `offset` / `limit`, `count`, snake_case query names, and reusable `AdminOffsetPageRequest` / `AdminOffsetPageResult`.
9. Keep public API request/response JSON and query names snake_case. Do not add camelCase compatibility aliases unless a plan explicitly documents a migration bridge.
10. Use offset pagination for admin search/filter lists. Keep cursor pagination for user-facing feeds where stable infinite scroll matters.
11. Production admin lockout recovery uses `authz-grant-role --email <email> --role admin`; `seed-admin` is local/development only.
12. Keep role / permission catalog code-managed in `backend/app/config/authorization.py`; never add DB catalog tables for a CRUD.

## Frontend Pattern

1. Put API clients and API types in `frontend/src/lib/`.
2. Put reusable CRUD controls in `frontend/src/components/molecules/`.
3. Put feature screens in `frontend/src/components/organisms/<Feature>/`.
4. Put routes in `frontend/src/routes/` and use `requirePermission("admin:access", options)` in `beforeLoad`.
5. If a route shares a path prefix with a page route but must not nest inside it, use TanStack Router trailing underscore naming, for example `_authenticated.admin_.users.tsx`.
6. Use React Query keys under `queryKeys.<feature>`, and invalidate both feature queries and `queryKeys.auth.me` when the current user's permissions or active state may have changed.
7. Keep admin UI dense and task-oriented: toolbar, filters, table, pagination, confirmation dialog. Avoid landing-page layout and nested cards.
8. Let `apiClient` handle CSRF bootstrap for unsafe methods. Components must not fetch `/api/auth/csrf` directly.

## User CRUD Specifics

- `/admin/users` is guarded by `admin:access`; Backend API is `/api/admin/users`.
- User delete is logical deletion. Deleted users are hidden from admin CRUD and return `user_not_found`.
- User edit sends user fields and roles in one `PATCH /api/admin/users/{user_id}` request to avoid partial success.
- Password changes and `is_active=false` revoke sessions. Email-only changes do not.
- Role audit detail should be built with `role_audit_detail()`. When `source` is `None`, omit the key instead of writing `"source": null`.
- User-owned resources must be cleaned up in both `AccountDeletionUsecase` and `AdminUserUsecase.delete_user()`.
- Do not force every resource through a generic repository base class. Prefer domain lifecycle, audit, and transaction clarity over premature inheritance.

## Verification

Run focused tests first, then broader gates:

- Backend unit tests for models, repository, usecase, controller, route, DI, and CLI.
- Backend integration tests when `TEST_DATABASE_URL` is available.
- Frontend tests for search params, API client, route guard/query flow, and organism behavior.
- Frontend `npm run typecheck` and project CI checks before reporting completion.
