# REST API and Problem Details Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. この計画の実装では、ユーザーが明示するまで `git add` / `git commit` を行わない。

**Goal:** 既存の FastAPI / React API 契約を Web standard と project-local REST API skill に揃え、JSON key を `snake_case`、日時 response を Unix timestamp、error response を RFC 9457 Problem Details へ移行する。

**Architecture:** まず `.agents/skills/restful-api-design/SKILL.md` と `.claude/skills/restful-api-design/SKILL.md` を Web standard ベースの規約へ更新する。次に Backend の API DTO / error handler / CSRF middleware / OpenAPI response 定義を新 wire format に置き換え、Frontend は API boundary 型を `snake_case` / Unix timestamp / Problem Details に合わせる。Problem type は code registry を source of truth にし、docs は registry と同期させる。

**Tech Stack:** FastAPI, Pydantic v2, SQLModel, pytest, React 19, TypeScript, TanStack Query, Vitest, RFC 9110, RFC 9457 Problem Details

---

## 決定事項

ユーザーの追加指示により、この計画では次を確定事項として扱う。

- `restful-api-design` skill は修正してよい。
- OPN 固有文言は削除する。
- Web standard に沿う。
- JSON key は `snake_case` を死守する。
- 時間の response は Unix timestamp を死守する。

前回計画の「現行実装に合わせて `camelCase` を正にする」方針は撤回する。現行実装は `camelCase` / ISO 8601 datetime response を返しているため、今回の実装対象には API breaking change が含まれる。

## 背景と現状

2026-08-12 時点の主な API mismatch は次のとおり。

| 領域 | 現行実装 | 新 REST skill / 今回の正 |
|---|---|---|
| JSON key | `camelCase` alias | `snake_case` |
| 日時 response | ISO 8601 string | Unix timestamp number |
| error response | `{ "error": { "code", "message", "details" } }` | RFC 9457 Problem Details |
| field validation details | Pydantic `loc` / `message` / `type` | Problem Details `errors` extension。body は JSON Pointer、query/path/header/cookie は parameter |
| list response | `items` / `total` or `items` / `nextCursor` | `data` / `count` or `data` / `next_cursor` |
| admin search query | `search` | `query` |
| health check | `/api/healthz` static OK | root `/healthz` も追加。この template では lightweight liveness として維持 |
| content negotiation | ほぼ未実装 | skill には規約として残すが、実装は別計画に切り出す |
| OpenAPI error content | `application/json` + `ErrorResponse` | `application/problem+json` + explicit schema |

主な API route は次のとおり。

| Controller | 現行 path | 方針 |
|---|---|---|
| `backend/app/controllers/healthz_controller.py` | `GET /api/healthz` | root `/healthz` 追加。既存 `/api/healthz` は互換維持 |
| `backend/app/controllers/auth_controller.py` | `/api/auth/*` | Auth path は維持。ただし JSON body / query / response keys は `snake_case` へ移行 |
| `backend/app/controllers/sample_controller.py` | `/api/samples` | CRUD path は維持。list は `data` / `next_cursor`、日時は Unix timestamp |
| `backend/app/controllers/admin_user_controller.py` | `/api/admin/users` | CRUD path は維持。list は `data` / `count`、query は `query`、keys は `snake_case` |
| `backend/app/controllers/authorization_controller.py` | `/api/admin/roles`, `/api/admin/users/{user_id}/roles` | role catalog response も `data` を primary collection にする。`PUT roles` は set replacement として維持 |

## 設計方針

### 方針 1: REST skill は Web standard + project constraints へ全面改訂する

旧 skill は OPN 固有文言、OAuth2 Password Grant 前提、`PUT` partial update、Status error、snake_case URL segment、Accept 必須検証、Unix timestamp などが混在していた。今回、次へ整理する。

- HTTP method は RFC 9110 の意味論に沿わせる。
- `PATCH` を partial update、`PUT` を complete replacement / set replacement とする。
- Error は RFC 9457 Problem Details とする。
- JSON key は `snake_case`。
- 日時 response は Unix timestamp。
- Auth / OIDC path は browser session workflow の例外として許容する。
- service-to-service API key / Bearer auth は別 profile とし、browser session endpoint に混ぜない。
- health check は `/healthz` を正とする。この template では現行の lightweight liveness を維持し、DB 等の readiness check は派生 project の要件が出た時点で `/readyz` などとして追加する。

### 方針 2: Auth path は維持するが、payload key は `snake_case` にする

Auth endpoint は browser session / CSRF / OIDC redirect workflow として既存 path を維持する。

| Path | 維持理由 |
|---|---|
| `POST /api/auth/login` | cookie session 発行 command として明確 |
| `POST /api/auth/register` | user 作成 + session 発行 workflow |
| `POST /api/auth/logout` | current session command |
| `GET /api/auth/me` | current authenticated principal singleton |
| `PATCH /api/auth/me` | current user preference partial update |
| `DELETE /api/auth/me` | self-service account deletion |
| `GET /api/auth/csrf` | unsafe request bootstrap |
| `GET /api/auth/oidc/{provider_id}/start` / `reauth` / `callback` | full-page redirect workflow |

`providerId`, `languageCode`, `confirmEmail`, `csrfToken`, `oidcError`, `oidcReauth` は JSON API / query key としては `provider_id`, `language_code`, `confirm_email`, `csrf_token`, `oidc_error`, `oidc_reauth` へ移行する。ただし cookie 名 `csrf_token` は既に snake_case なので維持する。

### 方針 3: 日時 response は Unix timestamp seconds を標準にする

Public API の日時 field は Unix timestamp seconds の number にする。

- `created_at`, `updated_at`, `registered_at`, `last_login_at`, `deleted_at`, `expires_at`, `issued_at` などは seconds。
- DB 内部の business timestamp が milliseconds でも、API response は seconds へ変換する。変換は floor division (`milliseconds // 1000`) に統一し、同一秒内 ordering は API timestamp だけに依存させず、既存の DB ordering / `id` tie-breaker を維持する。
- milliseconds が必要な field は `_at_ms` suffix を使うが、今回の既存 API 移行では追加しない。
- Date-only value は `YYYY-MM-DD` string を許容する。

### 方針 4: Problem Details は registry を source of truth にする

`api_error()` の呼び出しごとに title/type を手書きしない。`backend/app/models/problem_types.py` を追加し、code registry を正とする。

Registry entry:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ProblemType:
    code: str
    type: str
    title: str
    status: int


PROBLEM_TYPES: dict[str, ProblemType] = {
    "invalid_credentials": ProblemType(
        code="invalid_credentials",
        type="/problems/invalid_credentials",
        title="Invalid credentials",
        status=401,
    ),
}
```

Machine code は RFC 9457 上は opaque value だが、この template では JSON key と同じ可読性・検索性のため `snake_case` に統一する。既存 `INVALID_CREDENTIALS` 等は `invalid_credentials` へ移行する。Frontend message mapping も同じ変更で更新する。

### 方針 5: Problem Details extension は必要な時だけ出す

Base shape:

```json
{
  "type": "/problems/invalid_credentials",
  "title": "Invalid credentials",
  "status": 401,
  "detail": "The email or password is incorrect.",
  "instance": "/api/auth/login",
  "code": "invalid_credentials"
}
```

Validation shape:

```json
{
  "type": "/problems/validation_error",
  "title": "Validation error",
  "status": 422,
  "detail": "Request validation failed.",
  "instance": "/api/auth/login",
  "code": "validation_error",
  "errors": [
    {
      "location": "body",
      "pointer": "#/email",
      "detail": "Input should be a valid email address.",
      "code": "value_error"
    }
  ]
}
```

`errors` は `None` default にし、field errors がない場合は body に出さない。Pydantic response dump は `exclude_none=True` を使う。

### 方針 6: OpenAPI additional responses は explicit schema で書く

FastAPI の `responses={status: {"model": ProblemDetails, "content": {"application/problem+json": {}}}}` は、schema が成功 response media type の `application/json` 側に注入され得る。したがって error response は `model` shorthand を使わず、`content.application/problem+json.schema` を明示する。

Helper:

```python
PROBLEM_DETAILS_SCHEMA_REF = {"$ref": "#/components/schemas/ProblemDetails"}


def problem_response_openapi(description: str = "Problem Details") -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/problem+json": {
                "schema": PROBLEM_DETAILS_SCHEMA_REF,
            },
        },
    }
```

実装前に小さい FastAPI app で OpenAPI 生成を確認し、test では `application/problem+json` 側に `$ref` があり、`application/json` 側に error schema が混入していないことを検証する。

### 方針 7: Legacy parser fallback は入れない

Backend / Frontend を同じ repository で同時に変更するため、Frontend に旧 `{ error: ... }` fallback は残さない。旧形式を返す backend と接続する互換性は今回の goal ではない。

### 方針 8: Breaking change は派生プロジェクト向けに明記する

この template は派生プロジェクトがある前提で運用されている。`camelCase` → `snake_case`、ISO 8601 → Unix timestamp、error envelope → Problem Details、`items` → `data`、`search` → `query` は明確な breaking change として `backend/AGENTS.md`、`frontend/AGENTS.md`、`documents/references/api-problem-details.md` に migration note を書く。

### 方針 9: Content negotiation 実装は別計画に切り出す

`restful-api-design` skill には `Accept` / `Content-Type` の規約を残すが、今回の実装では middleware / dependency を追加しない。理由は、今回の core migration だけで API wire format、Frontend 型、日時表示、Problem Details、OpenAPI を一斉に変える大きな変更であり、さらに `/api/auth/oidc/*` の redirect endpoint を壊さない content negotiation 判定を同時に設計すると scope が広がりすぎるためである。

今回やること:

- Problem Details の error response media type を `application/problem+json` にする。
- OpenAPI に content negotiation は将来対応として書く。

今回やらないこと:

- `/api` 全体への `Accept` / `Content-Type` enforcement middleware 追加。
- `406 not_acceptable` / `415 unsupported_media_type` を返す runtime 実装。

ただし problem registry には将来実装用の `not_acceptable` / `unsupported_media_type` を含める。

## Problem code registry 初期一覧

実装時は `rtk grep -n "api_error\\(" backend/app` と CSRF middleware を確認し、少なくとも次を registry に含める。

| old code | new code | status |
|---|---|---:|
| `BAD_REQUEST` | `bad_request` | 400 |
| `UNAUTHORIZED` | `unauthorized` | 401 |
| `FORBIDDEN` | `forbidden` | 403 |
| `PERMISSION_DENIED` | `permission_denied` | 403 |
| `NOT_FOUND` | `not_found` | 404 |
| `CONFLICT` | `conflict` | 409 |
| `VALIDATION_ERROR` | `validation_error` | 422 |
| `RATE_LIMITED` | `rate_limited` | 429 |
| `INTERNAL_SERVER_ERROR` | `internal_server_error` | 500 |
| Starlette 405 | `method_not_allowed` | 405 |
| future 406 | `not_acceptable` | 406 |
| future 415 | `unsupported_media_type` | 415 |
| `CSRF_VALIDATION_FAILED` | `csrf_validation_failed` | 403 |
| `INVALID_ADMIN_USER_QUERY` | `invalid_admin_user_query` | 422 |
| `EMAIL_ALREADY_REGISTERED` | `email_already_registered` | 409 |
| `WEAK_PASSWORD` | `weak_password` | 422 |
| `ROLE_NOT_FOUND` | `role_not_found` | 422 |
| `USER_NOT_FOUND` | `user_not_found` | 404 |
| `SAMPLE_ITEM_INVALID_CURSOR` | `sample_item_invalid_cursor` | 400 |
| `SAMPLE_ITEM_NOT_FOUND` | `sample_item_not_found` | 404 |
| `ACCOUNT_DELETION_CONFIRMATION_MISMATCH` | `account_deletion_confirmation_mismatch` | 400 |
| `ACCOUNT_DELETION_REAUTH_REQUIRED` | `account_deletion_reauth_required` | 400 |
| `ACCOUNT_DELETION_INVALID_PASSWORD` | `account_deletion_invalid_password` | 400 |
| `ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` | `account_deletion_oidc_reauth_required` | 400 |
| `ACCOUNT_DELETION_REAUTH_RATE_LIMITED` | `account_deletion_reauth_rate_limited` | 429 |
| `INVALID_CREDENTIALS` | `invalid_credentials` | 401 |
| `REGISTER_RATE_LIMITED` | `register_rate_limited` | 429 |
| `LOGIN_RATE_LIMITED` | `login_rate_limited` | 429 |

`http_error` は registry table には置かない。未知の framework HTTP status は `problem_type_for_status(status_code)` で `code="http_error"`, `type="/problems/http_error"`, `title="HTTP error"`, `status=<actual status>` の dynamic fallback を作る。これにより registry test の「status は 400-599」と矛盾させず、405 / 404 string detail など framework 由来経路も HTTP status を失わない。

OIDC redirect query codes are not Problem Details. They may remain uppercase during this plan if changing URL query compatibility would expand scope too far, but JSON API query keys should still be snake_case (`oidc_error`, `oidc_reauth`) if those route search params are changed.

## 変更予定ファイル

### REST skill / docs

- Modify: `.agents/skills/restful-api-design/SKILL.md`
- Modify: `.claude/skills/restful-api-design/SKILL.md`
- Modify: `AGENTS.md`
- Modify: `backend/AGENTS.md`
- Modify: `frontend/AGENTS.md`
- Modify: `documents/references/backend-app-structure.md`
- Modify: `documents/references/frontend-app-structure.md`
- Modify: `documents/references/rbac-authorization-operations.md`
- Modify: `documents/references/oauth-oidc-google-setup-guide.md`
- Modify: `documents/references/postgrest-compatible-api-spec.md` only to mark it as PostgREST compatibility exception
- Create: `documents/references/api-problem-details.md`

### Backend implementation

- Modify: `backend/app/bootstrap/error_handlers.py`
- Modify: `backend/app/bootstrap/csrf.py`
- Modify: `backend/app/bootstrap/route.py`
- Modify: `backend/app/controllers/auth_dependencies.py`
- Modify: `backend/app/controllers/healthz_controller.py`
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/app/controllers/sample_controller.py`
- Modify: `backend/app/controllers/admin_user_controller.py`
- Modify: `backend/app/controllers/authorization_controller.py`
- Modify: `backend/app/models/error.py`
- Create: `backend/app/models/problem_types.py`
- Modify: `backend/app/models/auth_schemas.py`
- Modify: `backend/app/models/sample_item_schemas.py`
- Modify: `backend/app/models/admin_user_schemas.py`
- Modify: `backend/app/models/authorization_schemas.py`

### Backend tests

- Modify: `backend/tests/unit/bootstrap/test_error_handlers.py`
- Modify: `backend/tests/unit/bootstrap/test_csrf_middleware.py`
- Modify: `backend/tests/unit/bootstrap/test_route.py`
- Modify: `backend/tests/unit/bootstrap/test_create_app.py`
- Modify: `backend/tests/unit/controllers/test_admin_user_controller.py`
- Modify: `backend/tests/unit/controllers/test_auth_controller_dependency.py`
- Modify: `backend/tests/unit/controllers/test_auth_controller_helpers.py`
- Modify: `backend/tests/unit/controllers/test_auth_dependencies.py`
- Modify: `backend/tests/unit/controllers/test_auth_permission_dependencies.py`
- Modify: `backend/tests/unit/controllers/test_authorization_controller.py`
- Modify: `backend/tests/unit/controllers/test_sample_controller.py`
- Modify: `backend/tests/unit/controllers/test_sample_controller_dependency.py`
- Modify: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/tests/integration/test_auth_oidc_controller.py`
- Modify: `backend/tests/integration/test_admin_user_controller.py`
- Modify: `backend/tests/integration/test_authorization_controller.py`
- Modify: `backend/tests/integration/test_sample_item_controller.py`
- Create: `backend/tests/unit/models/test_problem_types.py`

### Frontend implementation / tests

- Modify: `frontend/src/lib/apiError.ts`
- Modify: `frontend/src/lib/apiError.test.ts`
- Modify: `frontend/src/lib/apiClient.test.ts`
- Modify: `frontend/src/lib/authApi.ts`
- Modify: `frontend/src/lib/authApi.test.ts`
- Modify: `frontend/src/lib/adminUsersApi.ts`
- Modify: `frontend/src/lib/adminUsersApi.test.ts`
- Modify: `frontend/src/lib/adminSearchParams.ts`
- Modify: `frontend/src/lib/adminSearchParams.test.ts`
- Modify: `frontend/src/lib/i18n/formatters.ts`
- Modify: `frontend/src/lib/i18n/LanguageSyncManager.tsx`
- Modify: `frontend/src/lib/i18n/LanguageSyncManager.test.tsx`
- Modify: `frontend/src/lib/permissions.test.ts`
- Modify: `frontend/src/hooks/useAccountDeletion.test.tsx`
- Modify: `frontend/src/hooks/useAuthSession.test.tsx`
- Modify: `frontend/src/components/organisms/Auth/AccountDeletionPanel.tsx`
- Modify: `frontend/src/components/organisms/Auth/AccountDeletionPanel.test.tsx`
- Modify: `frontend/src/components/organisms/Header/index.tsx`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`
- Modify: `frontend/src/components/molecules/OidcProviderButton.tsx`
- Modify: `frontend/src/components/molecules/OidcProviderButton.test.tsx`
- Modify: `frontend/src/components/organisms/AdminUsers/AdminUsersPage.tsx`
- Modify: `frontend/src/components/organisms/AdminUsers/AdminUsersPage.test.tsx`
- Modify: `frontend/src/components/organisms/AdminUsers/types.ts`
- Modify: `frontend/src/routes/-login.tsx`
- Modify: `frontend/src/routes/-register.tsx`
- Modify: `frontend/src/routes/_authenticated.admin_.users.tsx`
- Modify: `frontend/src/routes/_authenticated.app_.settings.tsx`
- Modify: `frontend/src/routes/admin.users.test.tsx`
- Modify: `frontend/src/routes/app.settings.test.tsx`
- Modify: `frontend/src/routes/{-$locale}/login.tsx`
- Modify: `frontend/src/routes/{-$locale}/register.tsx`
- Modify: `frontend/src/routes/login.test.tsx`
- Modify: `frontend/src/routes/register.test.tsx`
- Modify: locale JSON files if user-facing error code mappings change

## 具体的なタスク

### Task 0: 実装前の安全確認

- [x] `rtk git status --short` を実行し、既存の未コミット差分を確認する。
- [x] `rtk read .agents/skills/restful-api-design/SKILL.md` と `rtk read .claude/skills/restful-api-design/SKILL.md` を読み、内容一致を確認する。
- [x] REST skill が未更新または内容不一致の場合は、Task 1 より前に `.agents/skills/restful-api-design/SKILL.md` と `.claude/skills/restful-api-design/SKILL.md` をこの計画の決定事項に合わせて更新する。最低限、OPN 文言削除、`snake_case` JSON key、Unix timestamp response、RFC 9110 method semantics、RFC 9457 Problem Details、content negotiation 規約、health check 規約を含める。
- [x] `cmp .agents/skills/restful-api-design/SKILL.md .claude/skills/restful-api-design/SKILL.md` で skill の一致を確認する。
- [x] `backend/AGENTS.md` と `frontend/AGENTS.md` を読み直す。
- [x] `rtk grep -n "api_error\\(|json_error_response|ErrorResponse|error\\.details|\\[\"error\"\\]|createdAt|updatedAt|languageCode|confirmEmail|providerId|displayName|csrfToken|nextCursor|isActive|lastLoginAt|oidcError|oidcReauth|search" backend/app backend/tests frontend/src backend/AGENTS.md frontend/AGENTS.md documents/references` を実行し、変更対象を再確認する。
- [x] FastAPI の `responses` OpenAPI 生成挙動を最小 app で確認し、`model` shorthand ではなく explicit `content.application/problem+json.schema` を使う判断を検証する。
- [x] この計画作成時点では `git add` / `git commit` を行っていないため、実装中もユーザーが明示するまで staging / commit を行わない。

### Task 1: Problem type registry を追加する

- [x] `backend/tests/unit/models/test_problem_types.py` を作成し、registry が次を満たす test を先に書く。
  - code は全件 `snake_case`
  - type は `/problems/<code>` と一致
  - title は空でない
  - status は 400-599
  - 既存 `api_error()` / CSRF / default map の code が全件 registry に存在する
  - framework 由来の 405 は `method_not_allowed` として返せる
  - future content negotiation 用の `not_acceptable` / `unsupported_media_type` が registry に存在する
- [x] `backend/app/models/problem_types.py` を追加し、`ProblemType` と `PROBLEM_TYPES` を定義する。
- [x] `problem_type_for_code(code: str, fallback_status: int) -> ProblemType` を追加する。未知 code は `problem_type_for_status(fallback_status)` に委譲し、unknown code をそのまま出さない。
- [x] `problem_type_for_status(status_code: int) -> ProblemType` を追加する。registry に status 専用 code がある場合はそれを返し、未知 status は dynamic `http_error` ProblemType を actual status 付きで返す。
- [x] `old uppercase code -> new snake_case code` の変換 helper は migration 中だけ `normalize_problem_code()` として置く。実装完了時点で backend controller 呼び出しは snake_case を直接渡す。

### Task 2: Problem Details model / response helper を実装する

- [x] `backend/app/models/error.py` を Problem Details 用 model に置き換える。旧 `ErrorResponse` alias は残さない。

```python
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProblemError(BaseModel):
    model_config = ConfigDict(extra="allow")

    location: str | None = None
    pointer: str | None = None
    parameter: str | None = None
    detail: str
    code: str | None = None


class ProblemDetails(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: str | None = None
    errors: list[ProblemError | dict[str, Any]] | None = Field(default=None)
```

- [x] `backend/app/bootstrap/error_handlers.py` に `problem_response()` を追加する。`request_path: str | None` を受け取り、`instance` に入れる。
- [x] `problem_response()` は `ProblemDetails(...).model_dump(mode="json", exclude_none=True)` を使う。
- [x] `problem_response()` は `JSONResponse(media_type="application/problem+json")` を返す。
- [x] 401 では `Cache-Control: no-store` を維持する。
- [x] 429 では caller が渡した `Retry-After` header を維持する。
- [x] `json_error_response()` は削除する。互換 alias は残さない。
- [x] `api_error()` は request を知らないまま `HTTPException.detail` に `code`, `detail`, `errors`, optional extensions を入れる。`instance` 注入は exception handler が行う。
- [x] `http_exception_handler()` は `request.url.path` を `problem_response()` に渡す。
- [x] `backend/app/bootstrap/csrf.py` は `problem_response(..., request_path=request.url.path)` を直接呼ぶ。
- [x] CSRF middleware の internal error path も `internal_server_error` Problem Details を返す。

### Task 3: Validation error details を新形式にする

- [x] `backend/tests/unit/bootstrap/test_error_handlers.py` の validation error test を Problem Details shape に更新する。
- [x] `RequestValidationError` handler は `validation_error` code を使う。
- [x] body field は JSON Pointer として `pointer: "#/confirm_email"` のように返す。
- [x] query/path/header/cookie は `location` と `parameter` を返し、`pointer` は返さない。
- [x] `errors` item は `detail` と `code` を持つ。
- [x] `frontend/src/routes/_authenticated.app_.settings.tsx` の `accountDeletionValidationField()` は `error.errors` を読み、`pointer` または `parameter` から `confirm_email` / `password` を判定する。
- [x] `frontend/src/routes/app.settings.test.tsx` に、Problem Details validation error で `confirm_email` field だけが invalid になる regression test を追加する。

### Task 4: OpenAPI error response を explicit schema へ変更する

- [x] `backend/app/models/error.py` または `backend/app/controllers/_problem_responses.py` に `problem_response_openapi()` helper を置く。
- [x] controller の `ERROR_RESPONSE` は `{"model": ProblemDetails}` を使わず、`content.application/problem+json.schema` の `$ref` を明示する。
- [x] `backend/tests/unit/bootstrap/test_route.py` で OpenAPI schema を検証する。
  - `components.schemas.ProblemDetails` が存在する
  - error response の `application/problem+json.schema.$ref` が `#/components/schemas/ProblemDetails`
  - 同じ error response の `application/json` に `ProblemDetails` schema が混入していない
- [x] `backend/tests/unit/controllers/test_sample_controller.py` と `test_authorization_controller.py` の `ErrorResponse` ref assertion を `ProblemDetails` explicit content assertion に変更する。

### Task 5: Backend controller error code と response schema を更新する

- [x] `backend/app/controllers/auth_dependencies.py` の `api_error()` code を `unauthorized` / `permission_denied` へ変更する。
- [x] `backend/app/controllers/auth_controller.py` の error code を registry の snake_case code へ変更する。
- [x] `ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` の linked providers は top-level `providers` extension として `provider_id`, `display_name` を返す。
- [x] `backend/app/controllers/admin_user_controller.py` の error code を snake_case へ変更する。
- [x] `backend/app/controllers/sample_controller.py` の error code を snake_case へ変更する。
- [x] `backend/app/controllers/authorization_controller.py` の error code を snake_case へ変更し、unknown role codes は snake_case extension key `role_codes` で返す。
- [x] Backend tests の `response.json()["error"]["code"]` を `response.json()["code"]` へ変更し、expected code も snake_case にする。

### Task 6: API DTO を snake_case / Unix timestamp に変更する

- [x] Pydantic schema base から `alias_generator=to_camel` を削除する。
- [x] `populate_by_name=True` は必要な internal compatibility がなければ削除する。
- [x] `extra="forbid"` は維持する。
- [x] `AuthUserResponse.language_code`, `CsrfTokenResponse.csrf_token`, OIDC providers `provider_id` / `display_name` を wire format にする。
- [x] `AccountDeletionRequest.confirm_email` を wire format にする。
- [x] `AdminUserResponse.is_active`, `created_at`, `updated_at`, `last_login_at` を wire format にする。
- [x] `SampleItemResponse.is_completed`, `created_at`, `updated_at` を wire format にする。
- [x] Datetime serializer を追加し、response の datetime は Unix timestamp seconds にする。
- [x] Datetime serializer には明示的な return type annotation (`-> int`) を付ける。Pydantic v2 は serializer の戻り値注釈がないと OpenAPI serialization schema を `string` / `date-time` のままにし得るため、wire format と schema のズレを防ぐ。
- [x] Unit tests で representative response model の `model_dump(mode="json")` が Unix timestamp number を返すことを検証する。
- [x] `backend/tests/unit/bootstrap/test_route.py` に OpenAPI schema assertion を追加し、少なくとも `AdminUserResponse.created_at` と `SampleItemResponse.created_at` が `type: integer` であることを確認する。
- [x] Integration tests で auth / admin / sample response の datetime field が string ではなく number であることを確認する。
- [x] `frontend/src/lib/i18n/formatters.ts` の `formatDateTime(value: Date | number | string, ...)` を見直す。API 由来の日付表示には Unix timestamp seconds 専用の `formatUnixTimestampSeconds(value: number, language_code: LanguageCode)` を用意し、内部で `new Date(value * 1000)` に変換する。
- [x] 既存の `formatDateTime()` を残す場合は Date / ISO string 専用に狭める。`number` を受ける union は削除し、Unix seconds を JavaScript milliseconds と誤解する経路を型で塞ぐ。
- [x] `frontend/src/components/organisms/AdminUsers/AdminUsersPage.test.tsx` に Unix seconds の `created_at` / `updated_at` / `last_login_at` が 1970 年表示にならない regression test を追加する。

### Task 7: Collection response を `data` へ移行する

- [x] `SampleItemListResponse` を `data` / `next_cursor` に変更する。
- [x] `AdminUserListResponse` を `data` / `count` / `offset` / `limit` に変更する。
- [x] `RoleListResponse` は `data: list[RoleResponse]` と `permissions: list[PermissionResponse]` に変更する。primary collection は `data` にする。
- [x] 既存 class 名 `SampleItemListResponse` / `AdminUserListResponse` は今回リネームしない。REST skill の `XxxPage` / `XxxCursorPage` は recommended naming であり、wire format 変更と class rename を同時に行うリスクを避ける。
- [x] Backend controller と tests を更新する。
- [x] Frontend API types と UI usage を `items` / `total` から `data` / `count` へ変更する。

### Task 8: Admin query / route search を `query` へ移行する

- [x] `backend/app/controllers/admin_user_controller.py` の query parameter `search` を `query` に変更する。
- [x] `backend/app/controllers/admin_user_controller.py` の `is_active` query parameter は `alias="isActive"` を削除し、wire query key を `is_active` にする。
- [x] `backend/app/models/admin_user.py` の domain field 名は `search` のままでもよいが、controller boundary では `query` を受けて明示変換する。
- [x] `frontend/src/lib/adminUsersApi.ts` の `AdminUserListParams.search` を `query` に変更する。
- [x] `frontend/src/lib/adminUsersApi.ts` の `isActive` を `is_active` に変更し、query string も `is_active` にする。
- [x] `frontend/src/lib/adminSearchParams.ts` と test を `query` に変更する。
- [x] `frontend/src/lib/adminSearchParams.ts` と test を `isActive` から `is_active` に変更する。
- [x] `frontend/src/routes/_authenticated.admin_.users.tsx` と `AdminUsersPage.tsx` の prop / state を更新する。
- [x] UI 表示文言としての「検索」は維持してよい。

### Task 9: Frontend `ApiError` を Problem Details 専用にする

- [x] `frontend/src/lib/apiError.ts` の parser を Problem Details 専用にする。旧 envelope fallback は入れない。
- [x] `ApiError` は `type`, `title`, `status`, `detail`, `instance`, `code`, `errors`, `retryAfterSeconds` を持つ。
- [x] `details` property は削除する。
- [x] `toUserMessage()` の code mapping を snake_case code に更新する。
- [x] `accountDeletionOidcReauthProviders()` は Problem Details top-level `providers` extension から `provider_id`, `display_name` を読む。
- [x] `frontend/src/lib/apiError.test.ts` と `apiClient.test.ts` を Problem Details 正に更新する。
- [x] settings / login / register / admin UI tests の mock error body を Problem Details に更新する。

### Task 10: Location header を作成 endpoint に追加する

- [x] `POST /api/samples` は `201 Created` response に `Location: /api/samples/{item_id}` を付ける。
- [x] `POST /api/admin/users` は `201 Created` response に `Location: /api/admin/users/{user_id}` を付ける。
- [x] `POST /api/auth/register` は browser session workflow であり、canonical newly-created user URL を public resource として案内しないため Location header 対象外とする。この例外を docs に書く。
- [x] Unit / integration tests で samples と admin users の Location header を検証する。
- [x] Content negotiation runtime enforcement (`406 not_acceptable`, `415 unsupported_media_type`) は今回実装しない。別計画で JSON endpoint allowlist / OIDC redirect endpoint exclusion / CSRF middleware ordering を設計してから追加する。

### Task 11: Health check を実質要件に合わせる

- [x] root `/healthz` を追加し、既存 `/api/healthz` を維持する。
- [x] SPA static mount より先に explicit route が解決されることを `backend/tests/unit/bootstrap/test_route.py` で確認する。
- [x] この template の `/healthz` は lightweight liveness として維持し、DB 接続確認は入れない。
- [x] `.agents/skills/restful-api-design/SKILL.md` と `.claude/skills/restful-api-design/SKILL.md` の `## Health Checks` 節を書き換え、「この template の `/healthz` は liveness 相当であり、readiness は派生 project で `/readyz` 等として追加する」と明記する。
- [x] docs にも同じ health check 方針を反映する。
- [x] 将来 DB readiness を追加する場合は usecase / repository / DI 境界を使い、controller から DB session を直接持たないことを docs に残す。

### Task 12: Problem Details reference と migration notes を作る

- [x] `documents/references/api-problem-details.md` を作成する。
- [x] `PROBLEM_TYPES` registry の code / type / title / status を表として記載する。
- [x] この template の Problem Details `type` は absolute path (`/problems/<code>`) を採用することを明記する。Public API として公開する派生 project では absolute HTTPS URI へ切り替えてよい。
- [x] validation error `errors` item の `location` / `pointer` / `parameter` 規則を書く。
- [x] `instance` に path を入れる場合、path parameter の ID が response body に載ることを security note に書く。
- [x] OIDC redirect query code は Problem Details ではないことを書く。
- [x] 派生プロジェクト向け breaking change note を書く。
  - JSON key: `camelCase` → `snake_case`
  - datetime: ISO 8601 string → Unix timestamp seconds
  - error: `{ error: ... }` → Problem Details
  - list: `items` → `data`, `total` → `count`, `nextCursor` → `next_cursor`
  - query: `search` → `query`, `isActive` → `is_active`
  - code: uppercase → snake_case

### Task 13: AGENTS / docs を更新する

- [x] `backend/AGENTS.md` の API 設計を `snake_case` / Unix timestamp / Problem Details に変更する。
- [x] `backend/AGENTS.md` Phase 8 の `error.details` 記述を `errors` / `provider_id` / `display_name` に変更する。
- [x] `frontend/AGENTS.md` の API / Auth UI 節を Problem Details と `snake_case` DTO に変更する。
- [x] `frontend/AGENTS.md` Phase 8 の `error.details` 記述を `errors` に変更する。
- [x] `documents/references/backend-app-structure.md` と `frontend-app-structure.md` を更新する。
- [x] `documents/references/rbac-authorization-operations.md` と `documents/references/oauth-oidc-google-setup-guide.md` に残る old API casing examples を更新する。
- [x] `documents/references/postgrest-compatible-api-spec.md` は PostgREST compatibility API の例外文書であり、この REST skill の一般規約とは別物であることを冒頭または注記に追記する。
- [x] historical plan 本文は原則書き換えず、必要なら末尾に「現行 REST API 注記」を追記する。

### Task 14: Backend verification を実行する

- [x] `cd backend && rtk uv run pytest tests/unit/models/test_problem_types.py -q`
- [x] `cd backend && rtk uv run pytest tests/unit/bootstrap/test_error_handlers.py tests/unit/bootstrap/test_csrf_middleware.py tests/unit/bootstrap/test_route.py -q`
- [x] `cd backend && rtk uv run pytest tests/unit/controllers/test_admin_user_controller.py tests/unit/controllers/test_auth_controller_dependency.py tests/unit/controllers/test_auth_controller_helpers.py tests/unit/controllers/test_auth_dependencies.py tests/unit/controllers/test_auth_permission_dependencies.py tests/unit/controllers/test_authorization_controller.py tests/unit/controllers/test_sample_controller.py tests/unit/controllers/test_sample_controller_dependency.py -q`
- [x] `cd backend && rtk uv run pytest tests/unit -q`
- [x] PostgreSQL が利用できる状態で `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration -q -ra`
  - 実行結果: 既存 `app_test` は古い schema で `ck_auth_oidc_authorization_states_language_code_supported` が欠けていたため、fresh temporary DB `app_test_codex_rest` を作成し、`DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test_codex_rest rtk uv run python manage.py db-upgrade` 後に `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test_codex_rest rtk uv run pytest tests/integration -q -ra` を実行して 158 passed。検証後、一時 DB は削除済み。
- [x] `cd backend && rtk uv run ruff check .`
- [x] `cd backend && rtk uv run isort . --check-only`
- [x] `cd backend && rtk uv run yapf -dr app/ tests/ alembic/ manage.py`
- [x] `cd backend && rtk uv run mypy app manage.py`

### Task 15: Frontend verification を実行する

- [x] `cd frontend && rtk npm test -- apiError.test.ts apiClient.test.ts adminUsersApi.test.ts adminSearchParams.test.ts authApi.test.ts`
- [x] `cd frontend && rtk npm test -- LanguageSyncManager.test.tsx useAccountDeletion.test.tsx useAuthSession.test.tsx permissions.test.ts`
- [x] `cd frontend && rtk npm test -- app.settings.test.tsx admin.users.test.tsx AdminUsersPage.test.tsx AccountDeletionPanel.test.tsx OidcProviderButton.test.tsx login.test.tsx register.test.tsx`
- [x] `cd frontend && rtk npm test`
- [x] `cd frontend && rtk npm run check:ci`
- [x] `cd frontend && rtk npm run build`

### Task 16: Contract smoke test を行う

- [ ] Backend dev server を起動できる状態で、`GET /healthz` と `GET /api/healthz` が 200 を返すことを確認する。
- [ ] 未ログインで `GET /api/auth/me` を叩き、`Content-Type: application/problem+json`、`status: 401`、`code: unauthorized` を確認する。
- [ ] invalid payload で `POST /api/auth/login` を叩き、`status: 422`、`code: validation_error`、`errors[0].location` を確認する。
- [ ] admin user list を叩き、response が `data` / `count` / `offset` / `limit` と Unix timestamp number を返すことを確認する。
- [ ] sample list を叩き、response が `data` / `next_cursor` と Unix timestamp number を返すことを確認する。
- [x] 429 は自動テストで同等 coverage がある場合、手動 smoke を省略して完了報告に代替根拠を書く。406 / 415 runtime enforcement は今回の対象外である。
  - 未実行理由: Backend dev server / DB を使う contract smoke は起動せず、自動テストと OpenAPI/unit tests で代替確認。

### Task 17: 最終差分確認

- [x] `cmp .agents/skills/restful-api-design/SKILL.md .claude/skills/restful-api-design/SKILL.md` を実行し、skill が一致していることを確認する。
- [x] `rtk git diff --stat` を実行し、変更範囲がこの計画の想定ファイルに収まっていることを確認する。
- [x] `rtk grep -n "camelCase|createdAt|updatedAt|languageCode|confirmEmail|providerId|displayName|csrfToken|nextCursor|isActive|lastLoginAt|oidcError|oidcReauth|\\[\"error\"\\]|ErrorResponse|error\\.details|json_error_response" backend/app frontend/src backend/AGENTS.md frontend/AGENTS.md documents/references .agents/skills/restful-api-design/SKILL.md .claude/skills/restful-api-design/SKILL.md` を実行し、旧契約の残存を確認する。残ってよいものは historical compatibility note、OIDC provider external claim、明示した migration note、i18n translation key、または `apiClient.ts` 内の local variable / `X-CSRF-Token` header name に限定する。
- [x] `git add` / `git commit` を実行していないことを確認する。
- [x] 完了報告には、採用した Auth path、Problem Details payload の代表例、`snake_case` / Unix timestamp breaking change、実行した検証コマンド、未実行検証と理由を含める。

## Review checklist

- [x] REST skill は `.agents` と `.claude` で一致している。
- [x] REST skill から OPN 固有文言が削除されている。
- [x] REST skill は HTTP method semantics、RFC 9457、`snake_case` JSON key、Unix timestamp response を明記している。
- [x] Backend error response は `application/problem+json` を返す。
- [x] Backend error body は `type`, `title`, `status`, `detail`, `instance`, `code` を持つ。
- [x] Problem code は `snake_case` で registry 管理されている。
- [x] Validation error は `errors` extension を持ち、body は JSON Pointer、query/path/header/cookie は parameter で表現している。
- [x] `errors` は空配列では出力されない。
- [x] `status` body member と HTTP status code が一致する。
- [x] CSRF middleware も Problem Details を返す。
- [x] 401 は `Cache-Control: no-store` を維持している。
- [x] 429 は `Retry-After` header を維持している。
- [x] OpenAPI error response は `application/problem+json` 側に schema ref を持ち、`application/json` 側に誤注入されていない。
- [x] Auth path は現行 cookie session / OIDC workflow として維持している。
- [x] Auth JSON / query keys は `snake_case` へ移行している。
- [x] response datetime は Unix timestamp number である。
- [x] Frontend date formatter は Unix timestamp seconds を JavaScript milliseconds と誤解しない型・実装になっている。
- [x] Collection response の primary list key は `data` である。
- [x] Offset pagination は `count`, `offset`, `limit` を返す。
- [x] Cursor pagination は `next_cursor` を返す。
- [x] Admin user list query parameter は `query` である。
- [x] Frontend `ApiError` は Problem Details 専用 parser で、旧 envelope fallback を持たない。
- [x] Account deletion field-specific error は Problem Details `errors` でも `aria-invalid` 契約を維持している。
- [x] `POST /api/samples` と `POST /api/admin/users` は canonical resource URL の `Location` header を返す。
- [x] `/healthz` は lightweight liveness として明記され、readiness は派生 project の別 endpoint として扱われている。
- [x] docs / AGENTS が旧 `camelCase` / ISO datetime / error envelope と矛盾していない。
- [x] 派生プロジェクト向け breaking change note がある。
- [x] PostgREST compatibility document は一般 REST skill の例外として注記されている。

## Claude Review Remediation Checklist

- [x] OpenAPI の `#/components/schemas/ProblemDetails` dangling reference を解消し、`ProblemDetails` / `ProblemError` component schema の存在を unit test で検証した。
- [x] FastAPI default 422 が `application/json` + `HTTPValidationError` として残っていた auth endpoints を `application/problem+json` に修正した。
- [x] `/api/auth/oidc/providers` を `{ "data": [...] }` envelope に統一し、Backend / Frontend tests を更新した。
- [x] `problem_type_for_status(503)` が `internal_server_error` へ丸められないよう、未知 HTTP status は dynamic `http_error` として status を維持する。
- [x] 未登録 problem code は warning を出して status fallback に落とす。
- [x] `api_error()` に top-level extension support を追加し、`role_codes` / `providers` を `errors` ではなく extension として返す。
- [x] `unix_timestamp_seconds()` は timezone-aware datetime だけを受け取り、pre-epoch timestamp も `math.floor()` で正しく seconds にする。
- [x] Backend の legacy `message` / `details` fallback を削除し、Problem Details `detail` を唯一の message source にした。
- [x] `LoginRequest` / `CsrfTokenResponse` を `AuthSchema(extra="forbid")` に揃え、回帰 test を追加した。
- [x] Frontend の API boundary 以外の local identifier は必要に応じて camelCase に戻し、wire format の `snake_case` と分離した。
- [x] `formatDateTime()` の未使用 export を削除し、Unix timestamp seconds 専用 formatter test に置き換えた。
- [x] admin CRUD / i18n skills の旧 `ErrorResponse` / `camelCase` / `languageCode` 指示を修正した。
- [x] 欠落していた `.claude/skills/internationalization/SKILL.md` を追加し、`.agents` 側と内容一致を確認した。

## Claude Re-review Follow-up Checklist

- [x] Existing `app_test` の `test_oidc_state_language_code_schema` failure は stale schema 由来であることを確認した。`AuthOidcState` metadata と Alembic migration はどちらも `ck_auth_oidc_authorization_states_language_code_supported` で一致し、fresh DB integration は 158 passed。
- [x] `GET /api/admin/users/{user_id}/roles` は collection envelope ではなく特定 user の authorization state representation として `roles` / `permissions` を返す判断を `documents/references/rbac-authorization-operations.md` に明記した。
- [x] Problem Details extension が reserved member (`type`, `title`, `status`, `detail`, `instance`, `code`, `errors`) と衝突しても handler 内で TypeError にならないよう、衝突 key を drop して warning する guard と unit test を追加した。
- [x] OIDC provider list docs を `{ "data": [...] }` envelope に更新し、account deletion OIDC reauth providers は `errors` ではなく `providers` extension として記述を揃えた。

## 参考

- RFC 9110: `https://datatracker.ietf.org/doc/html/rfc9110`
- RFC 9457: `https://datatracker.ietf.org/doc/html/rfc9457`
