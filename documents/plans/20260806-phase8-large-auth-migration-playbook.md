# Phase 8 Large Auth Migration Playbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 5 auth operational migration を大規模 DB に適用する前の判断基準と代替 online migration 手順を docs に残す。

**Architecture:** Alembic migration logic は変更しない。`documents/references/backend-app-structure.md` に `large auth migration` playbook を追加し、fresh / small DB では現 migration を維持できること、大規模 DB では shadow column、batch backfill、短時間 lock の swap を検討することを明記する。

**Tech Stack:** Markdown、Alembic、PostgreSQL

---

## Files

- Modify: `documents/references/backend-app-structure.md`
- Modify: `backend/AGENTS.md`
- Modify: `documents/plans/20260804-phase8-hardening-backlog.md`

## Task 1: Reference Playbook

- [x] Step 1.1: Add a `large auth migration` section to `documents/references/backend-app-structure.md`.
- [x] Step 1.2: Document row count / lock / maintenance-window checks before applying `20260803_0003` to production-scale DBs.
- [x] Step 1.3: Document an alternate `batch backfill` path for `INET`, `issued_at`, and `updated_at` changes using nullable shadow columns and a short final swap.
- [x] Step 1.4: Document that fresh / small DBs can keep the current migration and that rewriting applied Alembic revisions requires a separate compatibility plan.

## Task 2: Agent Docs and Backlog

- [x] Step 2.1: Add a short pointer in `backend/AGENTS.md` to the large auth migration playbook.
- [x] Step 2.2: Mark P8-BE-4 complete in `documents/plans/20260804-phase8-hardening-backlog.md`.
- [x] Step 2.3: Run docs grep for `large auth migration`, `batch backfill`, and `INET`, then run `git diff --check`.
