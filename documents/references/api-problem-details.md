# API Problem Details

この template の JSON API error response は RFC 9457 Problem Details を正とする。

## Response Shape

Error response の media type は `application/problem+json`。

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

- `type`: stable problem type URI。この template では absolute path (`/problems/<code>`) を使う。public API として公開する派生 project では absolute HTTPS URI へ切り替えてよい。
- `title`: problem type ごとの安定した短い説明。
- `status`: HTTP status code と一致させる。
- `detail`: 発生ごとの人間向け説明。client logic で parse しない。
- `instance`: 発生箇所。この template では request path を入れる。
- `code`: application logic 用の `snake_case` machine code。

Optional extension member も `snake_case` にする。値がない場合は出力しない。`errors: []` は返さない。`errors` は field/parameter validation や sub-error collection のために予約し、追加 metadata は用途別の top-level extension member にする。

## Validation Errors

Validation failure は `code: "validation_error"` と `errors` extension を返す。

```json
{
  "type": "/problems/validation_error",
  "title": "Validation error",
  "status": 422,
  "detail": "Request validation failed.",
  "instance": "/api/auth/me",
  "code": "validation_error",
  "errors": [
    {
      "location": "body",
      "pointer": "#/confirm_email",
      "detail": "Field required.",
      "code": "missing"
    }
  ]
}
```

Body field は JSON Pointer (`pointer`) で示す。Query / path / header / cookie は `location` と `parameter` で示し、`pointer` は付けない。

## Application Extensions

Problem Details の追加情報は `snake_case` の top-level extension member で返す。既存例:

- `role_codes`: `role_not_found` で未知 role code の配列を返す。
- `providers`: `account_deletion_oidc_reauth_required` で再認証に使える OIDC provider の配列を返す。各要素は `provider_id` と `display_name` だけを含め、provider subject などの内部識別子は含めない。

`errors` は validation/sub-error 用に限定し、任意 metadata の入れ物として使わない。Extension member は RFC 9457 base member (`type`, `title`, `status`, `detail`, `instance`) と project-reserved member (`code`, `errors`) に衝突させない。衝突した extension member は response から drop され、warning log に記録される。

## Problem Type Registry

Source of truth は `backend/app/models/problem_types.py` の `PROBLEM_TYPES`。

| code | type | title | status |
|---|---|---|---:|
| `bad_request` | `/problems/bad_request` | Bad request | 400 |
| `unauthorized` | `/problems/unauthorized` | Unauthorized | 401 |
| `forbidden` | `/problems/forbidden` | Forbidden | 403 |
| `permission_denied` | `/problems/permission_denied` | Permission denied | 403 |
| `not_found` | `/problems/not_found` | Not found | 404 |
| `method_not_allowed` | `/problems/method_not_allowed` | Method not allowed | 405 |
| `not_acceptable` | `/problems/not_acceptable` | Not acceptable | 406 |
| `conflict` | `/problems/conflict` | Conflict | 409 |
| `unsupported_media_type` | `/problems/unsupported_media_type` | Unsupported media type | 415 |
| `validation_error` | `/problems/validation_error` | Validation error | 422 |
| `rate_limited` | `/problems/rate_limited` | Rate limited | 429 |
| `internal_server_error` | `/problems/internal_server_error` | Internal server error | 500 |
| `csrf_validation_failed` | `/problems/csrf_validation_failed` | CSRF validation failed | 403 |
| `invalid_admin_user_query` | `/problems/invalid_admin_user_query` | Invalid admin user query | 422 |
| `email_already_registered` | `/problems/email_already_registered` | Email already registered | 409 |
| `weak_password` | `/problems/weak_password` | Weak password | 422 |
| `role_not_found` | `/problems/role_not_found` | Role not found | 422 |
| `user_not_found` | `/problems/user_not_found` | User not found | 404 |
| `sample_item_invalid_cursor` | `/problems/sample_item_invalid_cursor` | Invalid sample item cursor | 400 |
| `sample_item_not_found` | `/problems/sample_item_not_found` | Sample item not found | 404 |
| `account_deletion_confirmation_mismatch` | `/problems/account_deletion_confirmation_mismatch` | Account deletion confirmation mismatch | 400 |
| `account_deletion_reauth_required` | `/problems/account_deletion_reauth_required` | Account deletion reauthentication required | 400 |
| `account_deletion_invalid_password` | `/problems/account_deletion_invalid_password` | Account deletion invalid password | 400 |
| `account_deletion_oidc_reauth_required` | `/problems/account_deletion_oidc_reauth_required` | Account deletion OIDC reauthentication required | 400 |
| `account_deletion_reauth_rate_limited` | `/problems/account_deletion_reauth_rate_limited` | Account deletion reauthentication rate limited | 429 |
| `invalid_credentials` | `/problems/invalid_credentials` | Invalid credentials | 401 |
| `register_rate_limited` | `/problems/register_rate_limited` | Register rate limited | 429 |
| `login_rate_limited` | `/problems/login_rate_limited` | Login rate limited | 429 |

Framework 由来の未知 HTTP status は dynamic fallback として `code: "http_error"`, `type: "/problems/http_error"`, `title: "HTTP error"` を返し、HTTP status は維持する。

## Security Notes

`instance` に request path を入れる場合、path parameter の ID が response body に載る。秘密値、token、provider authorization code、raw provider error、SQL、stack trace は `detail` / `errors` / extension に含めない。

401 response は `Cache-Control: no-store` を返す。Rate limit response は retry time が分かる場合に `Retry-After` header を返す。

## OIDC Redirect Query

OIDC callback failure の `oidc_error` query value は full-page redirect workflow 用であり、Problem Details ではない。JSON API query key は `snake_case` (`oidc_error`, `oidc_reauth`) にするが、OIDC redirect query code value は互換性のため `OIDC_*` の machine code を維持する。

## Breaking Changes For Derived Projects

2026-08-12 の REST alignment で次の wire format を変更した。

- JSON key: `camelCase` から `snake_case`
- datetime response: ISO 8601 string から Unix timestamp seconds
- error response: `{ "error": { ... } }` から RFC 9457 Problem Details
- list response: `items` から `data`
- offset list total: `total` から `count`
- cursor list next cursor: `nextCursor` から `next_cursor`
- admin search query: `search` から `query`
- active filter query: `isActive` から `is_active`
- application error code: uppercase から `snake_case`
