# Phase 8 Auth Feedback Component Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Login、register、account deletion の auth form feedback markup を shared component に寄せ、P8-FE-0 の a11y 契約から drift しにくくする。

**Architecture:** `AuthFormFeedback` molecule を作り、`message` がある場合だけ既存と同じ `p.text-sm.text-red-600[role=alert]` を描画する。Field association と invalid state は各 form の責務に残し、visible copy と error id は既存のまま維持する。

**Tech Stack:** React、TypeScript、Vitest、React Testing Library

---

## Files

- Create: `frontend/src/components/molecules/AuthFormFeedback.tsx`
- Create: `frontend/src/components/molecules/AuthFormFeedback.test.tsx`
- Modify: `frontend/src/components/organisms/Auth/LoginForm.tsx`
- Modify: `frontend/src/components/organisms/Auth/RegisterForm.tsx`
- Modify: `frontend/src/components/organisms/Auth/AccountDeletionPanel.tsx`
- Modify: `documents/plans/20260804-phase8-hardening-backlog.md`

## Task 1: Shared Component Contract

- [x] Step 1.1: Add a failing `AuthFormFeedback` test that renders no alert for `message={null}`.
- [x] Step 1.2: Add a failing `AuthFormFeedback` test that renders `role="alert"` with the supplied `id` and message.
- [x] Step 1.3: Implement `AuthFormFeedback`.
- [x] Step 1.4: Run `npm test -- AuthFormFeedback.test.tsx --run` and confirm it passes.

## Task 2: Form Adoption

- [x] Step 2.1: Replace inline alert markup in `LoginForm` with `AuthFormFeedback`.
- [x] Step 2.2: Replace inline alert markup in `RegisterForm` with `AuthFormFeedback`.
- [x] Step 2.3: Replace inline alert markup in `AccountDeletionPanel` with `AuthFormFeedback`.
- [x] Step 2.4: Run auth form component tests and confirm existing a11y behavior is unchanged.

## Task 3: Backlog and Verification

- [x] Step 3.1: Mark P8-FE-3 complete in `documents/plans/20260804-phase8-hardening-backlog.md`.
- [x] Step 3.2: Run frontend CI check, full tests, build, and `git diff --check`.
