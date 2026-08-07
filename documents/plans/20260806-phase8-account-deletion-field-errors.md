# Phase 8 Account Deletion Field Errors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/app/settings` の account deletion form で field-specific error、stale error clear、browser native validation 方針を P8-FE-0 の契約に沿って固定する。

**Architecture:** `AccountDeletionPanel` は field change を route へ通知し、browser native validation を避けるため form に `noValidate` を付ける。Route は `ApiError.details` から FastAPI validation error の field を判定し、空の `confirmEmail` 422 を confirmation email field-specific error にする。Invalid field の編集時だけ stale field error を消し、429 / CSRF など form-level error は input を invalid にしない。

**Tech Stack:** React、TypeScript、TanStack Router、TanStack Query、Vitest、React Testing Library

---

## Files

- Modify: `frontend/src/components/organisms/Auth/AccountDeletionPanel.tsx`
- Modify: `frontend/src/components/organisms/Auth/AccountDeletionPanel.test.tsx`
- Modify: `frontend/src/routes/_authenticated.app_.settings.tsx`
- Modify: `frontend/src/routes/app.settings.test.tsx`
- Modify: `frontend/src/lib/apiError.ts`
- Modify: `frontend/src/lib/apiError.test.ts`
- Modify: `documents/plans/20260804-phase8-hardening-backlog.md`

## Task 1: Component Contract

- [x] Step 1.1: Add failing component tests for `noValidate` and `onFieldChange`.
- [x] Step 1.2: Implement `noValidate` and field change callbacks in `AccountDeletionPanel`.
- [x] Step 1.3: Run component tests and confirm they pass.

## Task 2: API Validation Details

- [x] Step 2.1: Add failing `ApiError` test for legacy FastAPI `detail: []` validation details.
- [x] Step 2.2: Extend `ApiError.details` extraction to include legacy `body.detail` arrays.
- [x] Step 2.3: Run `apiError` tests and confirm they pass.

## Task 3: Route Error Behavior

- [x] Step 3.1: Add failing route tests for empty `confirmEmail` 422 field error and stale field error clear.
- [x] Step 3.2: Implement account deletion validation field mapping and invalid-field edit clear.
- [x] Step 3.3: Run settings route tests and confirm they pass.

## Task 4: Backlog and Verification

- [x] Step 4.1: Mark P8-FE-1 complete in `documents/plans/20260804-phase8-hardening-backlog.md`.
- [x] Step 4.2: Run frontend targeted tests.
- [x] Step 4.3: Run frontend CI check and `git diff --check`.
