# Phase 8 Deleted/Inactive User Session Revoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 認証時に deleted / inactive user を観測した場合、その user の全 active sessions を revoke する契約を固定する。

**Architecture:** 通常 active session path には追加 DB write を入れず、`user.deleted_at is not None` または `not user.is_active` の rare branch だけ `revoke_sessions_for_user(user.id, revoked_at)` を呼ぶ。Missing user は user id の正当性を確認できないため従来どおり観測 session だけを `revoke_session()` する。Audit log は観測 request/session に 1 件だけ残し、bulk revoked sessions 分には増やさない。

**Decision:** 認証 hot path の rare branch で bulk revoke を採用する。外部管理や手動運用で user status が後から変わった場合でも、最初に状態不整合を観測した request で同一 user の残存 active sessions を閉じられるため。通常 active user では branch に入らないため追加 UPDATE は走らない。

**Tech Stack:** FastAPI、Python、SQLModel、PostgreSQL、pytest

---

## Files

- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/AGENTS.md`
- Modify: `documents/plans/20260804-phase8-hardening-backlog.md`

## Task 1: Unit Contract

- [x] Step 1.1: Add failing unit assertions that deleted user authentication calls `revoke_sessions_for_user()` once and does not call `revoke_session()` for only the observed session.
- [x] Step 1.2: Add failing unit assertions that inactive user authentication follows the same bulk revoke contract.
- [x] Step 1.3: Add unit assertions that missing user still revokes only the observed session and active user does not call `revoke_sessions_for_user()`.
- [x] Step 1.4: Run `uv run pytest tests/unit/usecases/test_auth_usecase.py -q` and confirm the new deleted/inactive assertions fail.

## Task 2: Usecase Implementation

- [x] Step 2.1: Add an `AuthUsecase._reject_user_sessions()` helper that captures one `revoked_at = utcnow()`, calls `revoke_sessions_for_user(user_id, revoked_at)`, and writes one audit log for the observed `auth_session.id`.
- [x] Step 2.2: Change deleted / inactive branches in `authenticate_session()` to call `_reject_user_sessions()` instead of `_reject_session()`.
- [x] Step 2.3: Run `uv run pytest tests/unit/usecases/test_auth_usecase.py -q` and confirm unit tests pass.

## Task 3: Integration Coverage

- [x] Step 3.1: Add an integration test that creates two active sessions, marks the user deleted outside account deletion, authenticates one session, and asserts both sessions are revoked with one deleted-user audit row.
- [x] Step 3.2: Add an integration test that creates two active sessions, marks the user inactive, authenticates one session, and asserts both sessions are revoked with one inactive-user audit row.
- [x] Step 3.3: Run `TEST_DATABASE_URL=... uv run pytest tests/integration/test_auth_controller.py -q -ra` and confirm the new tests pass.

## Task 4: Docs and Backlog

- [x] Step 4.1: Update `backend/AGENTS.md` to document that deleted / inactive user observation bulk revokes active sessions, while missing user remains observed-session-only.
- [x] Step 4.2: Mark P8-BE-2 complete in `documents/plans/20260804-phase8-hardening-backlog.md`.
- [x] Step 4.3: Run backend static checks, relevant unit/integration tests, and `git diff --check`.
