# Phase 8 Account Deletion Retry-After Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Account deletion の 429 feedback に backend の `Retry-After` delay-seconds を反映し、`ApiError` から route-local に利用できるようにする。

**Decision:** Cooldown 中の submit button disabled は行わず、message-only を採用する。理由は、server-advised duration の表示だけで P8-FE-2 の実害を閉じられ、timer state と再 enable の責務を form component へ広げずに済むため。

**Architecture:** `apiClient` は non-2xx response から `ApiError` を作る際に response headers を渡す。`ApiError` は numeric `Retry-After` header の delay-seconds だけを `retryAfterSeconds` として公開し、未設定・不正値は `null` にする。`/app/settings` は account deletion 429 の form-level message に retry timing を含める。

**Tech Stack:** React、TypeScript、TanStack Router、Vitest、React Testing Library

---

## Files

- Modify: `frontend/src/lib/apiError.ts`
- Modify: `frontend/src/lib/apiError.test.ts`
- Modify: `frontend/src/lib/apiClient.ts`
- Modify: `frontend/src/lib/apiClient.test.ts`
- Modify: `frontend/src/routes/_authenticated.app_.settings.tsx`
- Modify: `frontend/src/routes/app.settings.test.tsx`
- Modify: `documents/plans/20260804-phase8-hardening-backlog.md`

## Task 1: ApiError Retry-After Contract

- [x] Step 1.1: Add failing `ApiError` tests for numeric, missing, and invalid `Retry-After`.
- [x] Step 1.2: Implement `retryAfterSeconds` parsing in `ApiError`.
- [x] Step 1.3: Run `apiError` tests and confirm they pass.

## Task 2: API Client Header Propagation

- [x] Step 2.1: Add failing `apiClient` tests for 429 `Retry-After` propagation and invalid header fallback.
- [x] Step 2.2: Pass response headers into `ApiError`.
- [x] Step 2.3: Run `apiClient` tests and confirm they pass.

## Task 3: Account Deletion Feedback

- [x] Step 3.1: Add failing settings route test for retry-aware 429 message.
- [x] Step 3.2: Implement account deletion retry-aware form-level message.
- [x] Step 3.3: Run settings route tests and confirm they pass.

## Task 4: Backlog and Verification

- [x] Step 4.1: Mark P8-FE-2 complete in `documents/plans/20260804-phase8-hardening-backlog.md`.
- [x] Step 4.2: Run frontend targeted tests.
- [x] Step 4.3: Run frontend CI check, full tests, build, and `git diff --check`.
