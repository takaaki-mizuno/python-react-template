# Phase 8 Auth Session Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `db-prune-auth` と auth repository の session / audit retention 契約を明確にし、audit log の `session_id ON DELETE SET NULL` を意図的な運用判断として文書化する。

**Architecture:** DB schema は変更しない。Repository method 名を `delete_sessions_expired_before()` に改め、CLI と tests を追従する。Docs には `db-prune-auth` の運用手順、audit log と session retention の関係、session 削除後に audit log の `session_id` が `NULL` になる契約を明記する。

**Tech Stack:** Python 3.12、Typer、SQLModel、PostgreSQL、pytest、Markdown

---

## Files

- Modify: `backend/app/interfaces/services/auth_repository_interface.py`
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/manage.py`
- Modify: `backend/tests/unit/test_manage.py`
- Modify: `backend/tests/unit/services/test_auth_repository.py`
- Modify: `backend/tests/integration/services/test_auth_repository.py`
- Modify: `backend/AGENTS.md`
- Modify: `documents/references/backend-app-structure.md`
- Modify: `README.md`
- Modify: `documents/plans/20260804-phase8-hardening-backlog.md`

## Task 1: Repository method name

- [x] Step 1.1: Update unit tests to call `delete_sessions_expired_before()` and verify `AuthRepositoryInterface` no longer exposes `delete_expired_sessions()`.
- [x] Step 1.2: Run targeted unit tests and confirm they fail because the new method does not exist.
- [x] Step 1.3: Rename interface and concrete repository method to `delete_sessions_expired_before()`.
- [x] Step 1.4: Update `manage.py` to call the new method.
- [x] Step 1.5: Run targeted unit tests and confirm they pass.

## Task 2: Audit/session retention behavior

- [x] Step 2.1: Add integration test proving expired session deletion keeps audit log row but sets `auth_audit_logs.session_id` to `NULL`.
- [x] Step 2.2: Run the integration test and confirm it fails before the method rename implementation or passes as a characterization after the rename.
- [x] Step 2.3: Keep DB behavior unchanged; this task documents the existing FK contract instead of changing schema.
- [x] Step 2.4: Run repository integration tests.

## Task 3: Documentation

- [x] Step 3.1: Update `backend/AGENTS.md` with `audit log session retention`, session retention >= audit retention guidance, and partial-success semantics.
- [x] Step 3.2: Update `documents/references/backend-app-structure.md` with the same contract.
- [x] Step 3.3: Add a real `db-prune-auth` operation section to `README.md`; do not add a contextless grep phrase.
- [x] Step 3.4: Review touched README migration examples. `db-upgrade --revision head` is valid, so the examples keep the explicit revision form.
- [x] Step 3.5: Run docs grep checks: `backend/AGENTS.md` contains `audit log session retention`; `README.md` contains the `Auth audit/session pruning` section with `session retention` and `audit log retention`.
- [x] Step 3.6: Record the public repository interface rename from `delete_expired_sessions()` to `delete_sessions_expired_before()` in `backend/AGENTS.md` for template consumers.

## Task 4: Backlog status and verification

- [x] Step 4.1: Mark P8-BE-3 complete in `documents/plans/20260804-phase8-hardening-backlog.md`.
- [x] Step 4.2: Run backend targeted unit tests.
- [x] Step 4.3: Run backend targeted integration tests if PostgreSQL is available.
- [x] Step 4.4: Run `git diff --check`.
