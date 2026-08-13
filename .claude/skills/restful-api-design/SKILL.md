---
name: restful-api-design
description: Use whenever designing, reviewing, or modifying JSON over HTTP APIs, including REST resource paths, HTTP methods and status codes, request/response DTOs, pagination, content negotiation, authentication endpoint exceptions, OpenAPI docs, Unix timestamp fields, snake_case JSON keys, and RFC 9457 Problem Details error responses.
---

# JSON over HTTP API Design Standards

この skill は、JSON over HTTP API を設計・実装・レビューするときの規約である。一般に REST API と呼ばれる設計を扱うが、目的は REST という言葉に厳密に合わせることではなく、HTTP の標準的な意味論に沿った、予測しやすい API を作ることである。

迷った場合は、この順で判断する。

1. HTTP Semantics (RFC 9110) と関連 RFC に従う。
2. エラーは Problem Details (RFC 9457) に従う。
3. この skill の project convention に従う。
4. 既存実装との互換性は、変更コストと利用者影響を明示して判断する。

## 基本方針

- API は HTTP status code、method、header、media type の意味を尊重する。
- Request / response body は原則 JSON object とする。Top-level JSON array は返さない。
- JSON object の key は request / response / Problem Details extension のすべてで `snake_case` を使う。
- 日時は response では Unix timestamp の number を使う。ISO 8601 string は返さない。
- 金額、任意精度 decimal、JavaScript safe integer を超える整数は string で返す。
- エラーは RFC 9457 Problem Details として返す。
- OpenAPI schema は実際の wire format と一致させる。

## URL Path

- Path segment は小文字英数字を基本にする。
- 複数語が必要な path segment は `snake_case` を使う。
- CRUD 対象 resource は複数形名詞を使う。
- Resource の識別子は path parameter に置く。
- できるだけ action 名を path に入れず、HTTP method で操作を表す。
- CRUD では表せない command は、resource 配下の動詞または command 名を使い、通常 `POST` にする。

例:

```text
GET    /api/users
POST   /api/users
GET    /api/users/{user_id}
PATCH  /api/users/{user_id}
DELETE /api/users/{user_id}
POST   /api/users/{user_id}/activate
POST   /api/notifications/{notification_id}/resend
```

Avoid:

```text
/api/getUsers
/api/userList
/api/notifications_2/{id}
/api/users/{id}/delete
```

## HTTP Methods

HTTP method は RFC 9110 の意味論に沿って使う。

| Method | 用途 |
|---|---|
| `GET` | Resource の取得。ログや計測以外の状態変更を起こさない |
| `POST` | Collection への作成、または resource / service に対する command |
| `PATCH` | Resource の partial update。送られた field だけを更新する |
| `PUT` | Resource representation の complete replacement、または set 全体の置き換え |
| `DELETE` | Resource の削除、無効化、または URI mapping の削除 |

`PUT` で partial update を表現しない。`PUT /api/users/{user_id}/roles` のように「roles set 全体を置き換える」場合は `PUT` が適切である。

## Status Codes

Success response:

| 状況 | Status |
|---|---:|
| 取得成功 | `200 OK` |
| 作成成功 | `201 Created` |
| 非同期受付 | `202 Accepted` |
| body を返さない command / deletion 成功 | `204 No Content` |
| redirect workflow | `303 See Other` など、HTTP redirect semantics に従う |

Error response:

| 状況 | Status |
|---|---:|
| Request body / query / path parameter が不正 | `400` または framework validation の `422` |
| 認証が必要、または認証失敗 | `401` |
| 認証済みだが権限がない | `403` |
| Resource がない、または存在を隠す | `404` |
| 一意制約や状態競合 | `409` |
| `Content-Type` が非対応 | `415` |
| `Accept` が満たせない | `406` |
| Rate limit | `429` |
| 予期しない server error | `500` |

## Request Data

- Resource ID は path parameter に置く。
- Filtering / search / sorting / pagination は query parameter に置く。
- 作成・更新 payload は JSON request body に置く。
- File upload は必要な場合だけ `multipart/form-data` を使う。
- Unsafe method (`POST`, `PUT`, `PATCH`, `DELETE`) では CSRF や認可境界を必ず検討する。

Query parameter も public API key と同じく `snake_case` にする。

```text
GET /api/users?limit=20&offset=0&order=registered_at&direction=desc&query=alice
```

## Content Negotiation

- JSON endpoint の request body は `Content-Type: application/json` を正とする。
- JSON endpoint で JSON 以外の request body を受け取った場合は `415 Unsupported Media Type` を返す。
- `Accept` が未指定、`*/*`、`application/json`、または `application/problem+json` を含む場合は通常どおり処理する。
- `Accept` が明示的に対応 media type を排除している場合は `406 Not Acceptable` を検討する。
- Error response は RFC 9457 に従い `application/problem+json` を返してよい。Problem Details は、client の `Accept` に列挙されていない場合でも返せる。

CSV や MessagePack など JSON 以外を追加する場合は、同じ resource に JSON 表現も残し、`Accept` によって選択する。

## JSON Keys

JSON key は `snake_case` を使う。

```json
{
  "access_token": "token",
  "created_at": 1786521600,
  "last_login_at": 1786521700
}
```

Avoid:

```json
{
  "accessToken": "token",
  "createdAt": "2026-08-12T00:00:00Z"
}
```

Python など server-side の内部名も `snake_case` を使う。TypeScript client も API boundary の型は `snake_case` のまま扱い、UI 内部で別名に変換する場合は境界を明確にする。

## Time Fields

日時を response に含める場合は Unix timestamp の number を使う。

- Field 名は `_at` suffix を使う。例: `created_at`, `updated_at`, `expires_at`, `deleted_at`
- Unit は API ごとに明示する。標準は Unix timestamp seconds とする。
- Milliseconds が必要な場合は field 名を `_at_ms` または `_timestamp_ms` にし、docs と schema に明記する。
- Date-only value は `YYYY-MM-DD` string を許容する。例: `billing_date: "2026-08-12"`
- Duration は timestamp ではないため、`ttl_seconds`, `retry_after_seconds` のように単位を suffix に含める。

## Collection Responses

Top-level JSON array は返さない。Collection response は object で包む。

Offset pagination:

```json
{
  "data": [
    {
      "id": "9b7b4a92-2c2c-4cd0-a508-9e9d2ea9d950",
      "email": "alice@example.com",
      "registered_at": 1786521600
    }
  ],
  "count": 1,
  "offset": 0,
  "limit": 20
}
```

Cursor pagination:

```json
{
  "data": [
    {
      "id": "9b7b4a92-2c2c-4cd0-a508-9e9d2ea9d950",
      "title": "Example",
      "created_at": 1786521600
    }
  ],
  "next_cursor": null
}
```

Offset pagination includes `count`, `offset`, and `limit`. Cursor pagination includes `next_cursor` and does not need `count` unless the product explicitly needs a total.

Recommended naming:

- Offset pagination response model: `XxxPage`
- Cursor pagination response model: `XxxCursorPage`
- Single resource response model: `XxxResponse`
- Create request model: `XxxCreateRequest`
- Partial update request model: `XxxUpdateRequest`

Compound responses are allowed only when the endpoint intentionally returns multiple named collections that are not a single primary list. Do not use this exception to avoid `data` for ordinary list endpoints.

## CRUD Shapes

Index:

```text
GET /api/users?limit=20&offset=0
```

```json
{
  "data": [],
  "count": 0,
  "offset": 0,
  "limit": 20
}
```

Show:

```text
GET /api/users/{user_id}
```

```json
{
  "id": "9b7b4a92-2c2c-4cd0-a508-9e9d2ea9d950",
  "email": "alice@example.com",
  "registered_at": 1786521600,
  "updated_at": 1786521700
}
```

Create:

```text
POST /api/users
```

Return `201 Created` and the created resource representation. Include `Location` when the canonical URL is available.

Partial update:

```text
PATCH /api/users/{user_id}
```

Request body contains only fields to change. Omitted field means unchanged. Explicit `null` is allowed only when the field is nullable and null has a documented meaning.

Delete:

```text
DELETE /api/users/{user_id}
```

Return `204 No Content` when there is no response body. Return `200 OK` only when the response body contains useful status or resulting representation.

## Problem Details

Error responses use RFC 9457 Problem Details.

Content-Type:

```text
application/problem+json
```

Base shape:

```json
{
  "type": "https://api.example.com/problems/invalid_credentials",
  "title": "Invalid credentials",
  "status": 401,
  "detail": "The email or password is incorrect.",
  "instance": "/api/auth/login",
  "code": "invalid_credentials"
}
```

Rules:

- `type` is the stable problem type URI. Prefer absolute HTTPS URLs for public APIs. Internal APIs may use absolute paths such as `/problems/invalid_credentials` if documented.
- `title` is a stable, short summary for the problem type. Do not vary it per occurrence except for localization.
- `status` matches the HTTP status code.
- `detail` is occurrence-specific human-readable guidance. Clients must not parse it for logic.
- `instance` identifies this occurrence. A request path is acceptable, but avoid leaking sensitive IDs when paths contain sensitive data.
- `code` is a snake_case machine code extension for application logic.
- Optional extension members use `snake_case`.
- Omit extension members that have no value. Do not emit `errors: []`.

Validation problem:

```json
{
  "type": "https://api.example.com/problems/validation_error",
  "title": "Validation error",
  "status": 422,
  "detail": "Request validation failed.",
  "instance": "/api/users",
  "code": "validation_error",
  "errors": [
    {
      "location": "body",
      "pointer": "#/email",
      "detail": "Input should be a valid email address.",
      "code": "value_error"
    },
    {
      "location": "query",
      "parameter": "limit",
      "detail": "Input should be less than or equal to 100.",
      "code": "less_than_equal"
    }
  ]
}
```

Use `pointer` only for JSON request body locations and format it as a JSON Pointer. Use `parameter` with `location: "query" | "path" | "header" | "cookie"` for non-body inputs.

## Problem Type Registry

Keep problem type definitions in code, not only in prose. The registry should define:

- `code`
- `type`
- `title`
- default `status`
- whether `retry_after` or field `errors` are expected

Documentation should be generated from, or checked against, this registry so it does not drift.

## Authentication Endpoint Exceptions

Authentication and browser session workflows often do not map cleanly to CRUD resources. These exceptions are acceptable when documented:

```text
POST   /api/auth/login
POST   /api/auth/register
POST   /api/auth/logout
GET    /api/auth/me
PATCH  /api/auth/me
DELETE /api/auth/me
GET    /api/auth/csrf
GET    /api/auth/oidc/{provider_id}/start
GET    /api/auth/oidc/{provider_id}/reauth
GET    /api/auth/oidc/{provider_id}/callback
```

Do not introduce OAuth2 Password Grant or bearer-token auth unless the project explicitly needs a non-browser API. Browser-first apps should keep the cookie session, CSRF, and OIDC redirect model coherent.

Service-to-service APIs may use `Authorization: Bearer <token>` or signed API keys, but that is a separate authentication profile. Do not mix it into browser session endpoints without a threat model and revocation design.

## Health Checks

Expose a health check endpoint for infrastructure.

```text
GET /healthz
```

If `/api/healthz` already exists for compatibility, keep both during migration.

For this template, `/healthz` is a lightweight liveness endpoint: it reports that the application process is running and can answer HTTP, and it should not depend on database connectivity. If production readiness checks are needed, expose them separately, for example `/readyz`, and include required dependencies such as database connectivity there.

## Security Notes

- Do not include stack traces, SQL, provider tokens, authorization codes, session tokens, CSRF tokens, password hashes, or secrets in API responses.
- Do not rely on frontend roles or permissions for authorization. Backend endpoints must enforce authorization.
- Keep error `detail` helpful but not diagnostic. Diagnostic details belong in server logs.
- Rate-limited responses should include `Retry-After` when the retry time is known.
- Unknown resources can intentionally return `404` instead of `403` when revealing existence is sensitive.
