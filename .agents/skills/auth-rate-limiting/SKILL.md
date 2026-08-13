---
name: auth-rate-limiting
description: Use when modifying or using LoginRateLimiterInterface, auth rate limit behavior, in-memory or Redis auth rate limiter implementations, AUTH_RATE_LIMIT_* settings, or login/register/OIDC/account-deletion rate limiting in this FastAPI template.
---

# Auth Rate Limiting

この skill は、認証 rate limiter を実装・変更・利用するときの契約である。rate limiter は認証防御の一部であり、bucket 契約を変えると lockout、brute force 耐性、audit log amplification に影響する。

## When to Use

- `LoginRateLimiterInterface` を呼び出す、または method を追加・変更する。
- `InMemoryLoginRateLimiter` または `RedisLoginRateLimiter` を変更する。
- `AUTH_RATE_LIMIT_*` や `AUTH_RATE_LIMIT_REDIS_*` の設定を追加・変更する。
- login、register、OIDC authorization start、account deletion password reauth の rate limit を触る。
- controller / usecase / test fixture で rate limiter cleanup を扱う。

## Core Contract

- `LoginRateLimiterInterface` は async interface である。request path では必ず `await` する。
- login/register 失敗 rate limit は IP、email+IP、email 単独の 3 bucket で判定する。
- bucket への記録は失敗時だけ行う。rate-limited request は audit log INSERT を行わず 429 へ変換する。
- login 成功時に削除するのは email+IP bucket だけである。IP bucket と email 単独 bucket は削除しない。
- duplicate email など register 由来の失敗は login の email 単独 bucket へ記録しない。
- account deletion の password 再認証判定は IP bucket と email+IP bucket だけを読む。email 単独 bucket は読まない。
- register 成功 rate limit は login failure とは別 bucket と registration window で扱う。
- OIDC authorization start は login failure と同じ auth window だが、別 bucket で扱う。
- `reset_for_tests()` は test cleanup 用であり、production interface へ戻さない。

## Redis Pattern

- Redis 実装は `redis.asyncio` client を使う。sync Redis call や `asyncio.run()` で event loop を塞がない。
- Redis score の時刻軸は Redis server `TIME` の Unix epoch seconds を正典にする。process-local `time.monotonic()` や app server wall clock を score に使わない。
- check path は `TIME` 後に pipeline の `ZCOUNT key window_start +inf` だけで判定する。check path で trim しない。
- window 境界は inclusive である。`score == now - window_seconds` は有効な試行として数える。
- record path は `ZREMRANGEBYSCORE key -inf (window_start`、`ZADD`、`EXPIRE` を `transaction=True` pipeline へ積む。trim は exclusive boundary にする。
- Redis key に raw email / IP を入れない。scope と normalized key を digest 化し、prefix と scope と digest で key を作る。
- すべての rate limit key に TTL を付ける。Redis mode では app-level bucket cap ではなく Redis TTL と memory policy で bounded にする。
- operation 全体を deadline で囲み、socket timeout / connect timeout / `AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS` も設定する。Redis provider は blocking pool を使い、pool 枯渇を Redis outage breaker の連続失敗に数えず、pool 枯渇 warning は rate limit する。
- circuit breaker は process-local でよい。連続失敗で open し、Redis operation 成功時に連続失敗 count を 0 に戻す。
- Redis unavailable policy は `fail_closed` と `fail_open` を明示する。unavailable 時は `auth_rate_limiter.redis_unavailable` を log に残し、email、IP、Redis URL は出さない。

## Testing Checklist

- in-memory と Redis の両方で、email+IP、IP、email 単独 bucket の block 契約を確認する。
- window boundary inclusive の test を置く。Redis では `ZCOUNT` min inclusive、trim max exclusive を確認する。
- login success が email+IP だけを clear し、IP/email bucket を消さないことを確認する。
- register duplicate 相当の failure が email-only bucket に入らないことを確認する。
- account deletion reauth が email-only bucket を読まないことを確認する。
- rate-limited request が audit log を書かないことを usecase test で確認する。
- Redis score が Redis epoch seconds であり、monotonic の小さい値ではないことを integration test で確認する。
- 2 instance と subprocess の両方で Redis state 共有を確認する。
- Redis deadline timeout 後に同一 connection の次 command response がずれないことを、`max_connections=1` の Redis integration test で確認する。
- Redis unavailable policy、operation deadline、circuit breaker、connection pool max の設定と log を確認する。
- integration tests の default fixture は memory backend に固定し、Redis 専用 test だけ marker で opt-out する。

## Common Mistakes

- Redis score に `time.monotonic()` を使う。
- check path で `ZREMRANGEBYSCORE` を実行し、login hot path を write にする。
- Redis key に raw email / IP を入れる。
- login success で IP bucket や email 単独 bucket まで削除する。
- register duplicate を email-only bucket に記録し、任意 email を lockout できる経路を作る。
- Redis client の `aclose()` を lifespan / CLI cleanup に入れ忘れる。
- sync fixture で Redis limiter の async `reset_for_tests()` を呼び、coroutine を捨てる。
