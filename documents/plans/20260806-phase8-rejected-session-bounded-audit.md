# Phase 8 Rejected Session Bounded Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** revoked / expired など既知だが inactive な session token の replay 監査を bounded にし、同時に replay count signal を保持する。

**Architecture:** Schema 追加は行わず、既存 `auth_audit_logs.detail_json` を aggregate state に使う。`AuthRepository.record_rejected_session_replay()` が session 単位の PostgreSQL advisory transaction lock を try 取得し、取得できない場合は replay 1 件の記録をスキップして CSRF middleware 経路を待たせない。lock 取得時は window 内の既存 aggregate `SESSION_REJECTED` row を `replay_count` / 送信元 metadata 更新、なければ 1 row 作成する。`AuthUsecase._audit_known_rejected_session()` は `authenticate_session()` と `validate_session_csrf()` の両経路から同じ repository method を呼ぶ。

**Tech Stack:** Python 3.12、FastAPI、SQLModel、PostgreSQL、pytest、Typer、Markdown

---

## Files

- Modify: `backend/app/interfaces/services/auth_repository_interface.py`
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/integration/services/test_auth_repository.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/AGENTS.md`
- Modify: `documents/plans/20260804-phase8-hardening-backlog.md`

## Task 1: Usecase Contract

- [x] Step 1.1: Add unit tests proving `authenticate_session()` and `validate_session_csrf()` call `record_rejected_session_replay()` for known inactive sessions, not raw `create_audit_log()`.
- [x] Step 1.2: Run targeted unit tests and confirm they fail because the current usecase still writes raw `SESSION_REJECTED` audit logs.
- [x] Step 1.3: Update `AuthRepositoryInterface` and `AuthUsecase._audit_known_rejected_session()` to call the bounded replay method.
- [x] Step 1.4: Run targeted unit tests and confirm they pass.

## Task 2: Repository Aggregation

- [x] Step 2.1: Add repository integration tests for bounded row count, `detail_json.replay_count`, aggregate window rollover, and concurrent replay serialization.
- [x] Step 2.2: Run targeted integration tests and confirm they fail before implementation.
- [x] Step 2.3: Implement `AuthRepository.record_rejected_session_replay()` with a transaction-scoped advisory lock, window lookup, insert on first replay, and JSONB aggregate update on later replays.
- [x] Step 2.4: Run targeted repository integration tests and confirm they pass.
- [x] Step 2.5: Replace blocking advisory lock with `pg_try_advisory_xact_lock`; if the per-session lock is busy, skip that replay record rather than blocking a CSRF middleware request while holding a DB connection.
- [x] Step 2.6: Record replay source metadata in `detail_json`: `last_ip_address`, `last_user_agent`, `distinct_ip_count`, and capped `recent_ip_addresses`.
- [x] Step 2.7: Exclude raw `SESSION_REJECTED` rows from aggregate anchor lookup by requiring `detail_json` to contain `replay_count`; first rejection and replay aggregate remain separate events.
- [x] Step 2.8: Do not add a composite index for the initial template implementation. The lookup starts from the existing `session_id` index, each session has a bounded number of aggregate rows in normal operation, and adding `(session_id, event_type, created_at)` would require a migration without clear benefit at template scale. Revisit with EXPLAIN data if a production DB shows many auth audit rows per session.
- [x] Step 2.9: Reject in-memory throttle for this backend contract. It reduces DB round trips in a single process but fails across multiple workers / instances, while auth audit is a cross-process operational signal.

## Task 3: Controller / Middleware Behavior

- [x] Step 3.1: Add integration tests proving repeated `/api/auth/me` replay and CSRF middleware `POST /api/unknown` replay are bounded and retain replay count.
- [x] Step 3.2: Run targeted controller integration tests; they pass because Task 1/2 already wired both usecase paths.
- [x] Step 3.3: Make any wiring fixes needed by the controller tests. No extra wiring fixes were needed.
- [x] Step 3.4: Run targeted controller integration tests and confirm they pass.

## Task 4: Docs and Backlog

- [x] Step 4.1: Update `backend/AGENTS.md` with the known rejected session replay bounded audit contract, replay count signal, 5 minute aggregate window, and advisory-lock concurrency note.
- [x] Step 4.2: Mark P8-BE-1 complete in `documents/plans/20260804-phase8-hardening-backlog.md`.
- [x] Step 4.3: Run docs grep checks for `known rejected session replay`, `bounded audit`, and `replay_count`.
- [x] Step 4.4: Run `git diff --check`.

## Task 5: Verification

- [x] Step 5.1: Run backend static checks touched by this change: `uv run ruff check .`, `uv run isort . --check-only`, `uv run yapf -dr app/ tests/ alembic/ manage.py`, `uv run mypy app manage.py`.
- [x] Step 5.2: Run backend unit tests for auth usecase.
- [x] Step 5.3: Run backend integration tests for auth repository and auth controller when PostgreSQL is available.
