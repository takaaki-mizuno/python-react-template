# Phase 8 Auth Form Feedback Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Login、register、account deletion の auth form feedback / a11y 契約を `frontend/AGENTS.md` に固定し、P8-FE-1 以降の手戻りを防ぐ。

**Architecture:** UI 実装は変更せず、現状挙動を docs に明文化する。field-specific error と form-level error の `role="alert"` / `aria-invalid` / `aria-describedby` の扱いを区別し、挙動変更が必要な場合は P8-FE-3 に混ぜず別 Task として扱う。

**Tech Stack:** React、TypeScript、TanStack Router、Vitest、Markdown

---

## Files

- Modify: `frontend/AGENTS.md`
- Modify: `documents/plans/20260804-phase8-hardening-backlog.md`

## Task 1: Current Behavior Review

- [x] Step 1.1: Review `LoginForm`, `RegisterForm`, `AccountDeletionPanel`, and settings route error mapping.
- [x] Step 1.2: Confirm FE-0 is docs-only and does not require component behavior changes.

## Task 2: Contract Documentation

- [x] Step 2.1: Document field-specific error behavior: target field gets `aria-invalid` and alert association.
- [x] Step 2.2: Document form-level error behavior: `role="alert"`, no unrelated field gets `aria-invalid`.
- [x] Step 2.3: Document current `aria-describedby` behavior for form-level errors, including 429 / CSRF.
- [x] Step 2.4: Document login / register current behavior without changing it.
- [x] Step 2.5: Document that future behavior changes must be separate tasks, not hidden inside P8-FE-3 refactoring.

## Task 3: Backlog and Verification

- [x] Step 3.1: Mark P8-FE-0 complete in `documents/plans/20260804-phase8-hardening-backlog.md`.
- [x] Step 3.2: Run docs grep for `field-specific error`, `form-level error`, and `aria-describedby`.
- [x] Step 3.3: Run `git diff --check`.
