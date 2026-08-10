# Code-Managed Authorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. ユーザーから別途許可があるまで `git add` / `git commit` は行わない。

> Implementation note: RED phase verification steps 2.2 / 3.2 / 4.2 / 5.2 / 6.2 were skipped during implementation and are intentionally left unchecked. DB-backed Step 7.3 / 7.5 / 10.3 were verified afterward by Claude Code against a disposable PostgreSQL database on 2026-08-10.

> Migration squash note: The repository had no applied migrations when implementation completed, so the development-only `20260418_0001` through `20260810_0006` chain was replaced with one initial schema revision, `backend/alembic/versions/20260810_0001_initial_schema.py`. The initial revision creates `user_roles(user_id, role_code, assigned_at, assigned_by_user_id)` directly and never creates `roles`, `permissions`, or `role_permissions`.

**Goal:** `roles` / `permissions` / `role_permissions` DB catalog と `authz-sync` を廃止し、role / permission catalog はコードだけを正、DB は user ごとの `role_code` assignment だけを持つ設計へ移行する。

**Architecture:** Authorization catalog は `backend/app/config/authorization.py` の code-managed definitions から直接解決し、DB には `user_roles(user_id, role_code, assigned_at, assigned_by_user_id)` だけを残す。Session 認証、login/OIDC response、admin API は DB catalog を読まず、user の `role_code` set とコード定義から permission set を計算する。Frontend の `AuthUser.roles` / `permissions`、permission guard、Backend の `require_permission()` 契約は維持する。

**Tech Stack:** FastAPI, SQLModel, Alembic, Injector, PostgreSQL, Typer, Pytest, React 19, TypeScript, TanStack Router, Vitest

---

## 背景

2026-08-08 の RBAC 実装では、次の 4 table を DB に作った。

- `roles`
- `permissions`
- `role_permissions`
- `user_roles`

その後の議論で、`roles` / `permissions` / `role_permissions` はコード定義を `authz-sync` で DB に同期するだけであり、運用者に「DB で自由編集してよい catalog」と誤解されるリスクがあることが分かった。

今回の変更では、custom role の DB 管理は考慮しない。role / permission catalog はコードに閉じ込め、DB は user assignment だけを保持する。

## 新しい設計

### Catalog

Catalog の正は `backend/app/config/authorization.py` に置く。

```python
DEFAULT_AUTHORIZATION_PERMISSIONS: tuple[PermissionDefinition, ...] = (
    PermissionDefinition(
        code="admin:access",
        display_name="Admin access",
        description="Access administrative endpoints.",
    ),
)

DEFAULT_AUTHORIZATION_DEFINITIONS: tuple[RoleDefinition, ...] = (
    RoleDefinition(
        code="admin",
        display_name="Admin",
        description="Full administrative access for this template.",
        permission_codes=("admin:access",),
    ),
)
```

この定義は DB に同期しない。Backend の admin API はこのコード定義から catalog response を返す。

### DB

DB に残す authorization table は `user_roles` だけにする。

```text
user_roles
- user_id UUID NOT NULL FK users.id ON DELETE CASCADE
- role_code VARCHAR(64) NOT NULL
- assigned_at TIMESTAMPTZ NOT NULL
- assigned_by_user_id UUID NULL FK users.id ON DELETE SET NULL
- PRIMARY KEY (user_id, role_code)
- INDEX ix_user_roles_role_code (role_code)
```

`role_code` は FK ではなく文字列である。存在検証は application code が `backend/app/config/authorization.py` の role catalog に対して行う。

### Permission 解決

User の permissions は次の流れで解決する。

1. DB から対象 user の `role_code` set を読む。
2. read 境界では未知 `role_code` を permission に寄与させず、warning log に残す。未知 role を持つ user の認証 request を 500 にしない。
3. public response の `roles` には既知 role だけを返す。未知 role は frontend/API response へ露出せず、ログと `authz-check-assignments` で観測する。
4. 既知 role の `permission_codes` を union する。
5. 未知 permission が role definition に含まれていれば startup/test/check で検出する。

通常運用では `RoleDefinition.permission_codes` は同じ file の `DEFAULT_AUTHORIZATION_PERMISSIONS` に含まれる必要がある。

Write 境界では未知 `role_code` を拒否する。`AuthorizationUsecase.replace_user_roles()`、admin API、`authz-grant-role` は repository write 前に code catalog で検証し、未知 role は `RoleNotFoundError` / `ROLE_NOT_FOUND` として扱う。

この方針での "fail closed" は「未知 role は権限を与えず public role としても返さない」という意味であり、read 経路で例外を投げて認証済み request を落とす意味ではない。role code rename/delete で DB に orphan assignment が残った場合、その user は未知 role 由来の role/permission を失うが、既知 role 由来の role/permission は維持する。

### CLI

`authz-sync` / `authz-sync --check` / `authz-check` は廃止する。

残す CLI:

- `authz-grant-role --email <email> --role <roleCode>`

追加する CLI:

- `authz-check-config`
- `authz-check-assignments`
- `authz-prune-unknown-role-assignments --yes`

`authz-check-config` は DB を読まず、コード定義だけを検査する。

検査内容:

- duplicate permission code がない。
- duplicate role code がない。
- permission catalog が空ではない。
- role catalog が空ではない。
- role が参照する permission code がすべて定義済み。
- role code が 1-64 文字である。
- permission code が 1-120 文字である。

`authz-check-assignments` は DB を読み、`user_roles.role_code` のうち code catalog に存在しない値を報告して exit 1 にする。`authz-prune-unknown-role-assignments --yes` は同じ未知 assignment を削除する復旧用 command とする。`--yes` がない場合は対象件数と `--yes` が必要なことを表示して exit 1 にし、削除しない。

## 影響範囲

### Backend files

- Modify: `backend/app/config/authorization.py`
- Modify: `backend/app/bootstrap/create_app.py`
- Modify: `backend/app/models/authorization.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/authorization_errors.py`
- Modify: `backend/app/interfaces/services/authorization_repository_interface.py`
- Modify: `backend/app/services/authorization_repository.py`
- Modify: `backend/app/interfaces/usecases/authorization_usecase_interface.py`
- Modify: `backend/app/usecases/authorization_usecase.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/app/usecases/oauth_oidc_usecase.py`
- Modify: `backend/app/usecases/account_deletion_usecase.py`
- Modify: `backend/app/controllers/authorization_controller.py`
- Modify: `backend/manage.py`
- Create: `backend/alembic/versions/20260810_0001_initial_schema.py` (squashed initial schema; replaces the development-only migration chain)
- Keep: `backend/app/controllers/auth_dependencies.py`
- Keep: `backend/app/models/auth_context.py`
- Keep: `backend/app/models/auth_schemas.py`

### Backend tests

- Modify: `backend/tests/unit/models/test_authorization.py`
- Modify: `backend/tests/unit/models/test_metadata.py`
- Modify: `backend/tests/unit/bootstrap/test_create_app.py`
- Modify: `backend/tests/unit/bootstrap/test_authorization_module.py`
- Replace or heavily modify: `backend/tests/unit/services/test_authorization_repository.py`
- Modify: `backend/tests/unit/usecases/test_authorization_usecase.py`
- Modify: `backend/tests/unit/controllers/test_authorization_controller.py`
- Modify: `backend/tests/unit/test_manage.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py`
- Modify: `backend/tests/unit/usecases/test_account_deletion_usecase.py`
- Modify: `backend/tests/unit/usecases/test_account_deletion_coverage.py`
- Replace or heavily modify: `backend/tests/integration/services/test_authorization_repository.py`
- Modify: `backend/tests/integration/test_authorization_controller.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/tests/integration/test_manage_cli.py`
- Modify: `backend/tests/integration/conftest.py`

### Frontend files

Frontend runtime behavior should not change.

- Keep: `frontend/src/lib/authApi.ts`
- Keep: `frontend/src/lib/permissions.ts`
- Keep: `frontend/src/lib/authGuard.ts`
- Keep: `frontend/src/routes/_authenticated.admin.tsx`
- Keep: existing Frontend tests unless response fixture setup changes.

### Docs

- Modify: `AGENTS.md`
- Modify: `backend/AGENTS.md`
- Modify: `documents/references/backend-app-structure.md`
- Modify: `documents/references/rbac-authorization-operations.md`
- Modify: `documents/references/oauth-oidc-google-setup-guide.md`
- Modify: `documents/plans/20260808-rbac-authorization.md` only if preserving historical notes needs an addendum. Do not rewrite its completed history.

## Pre-flight

- [x] **Step 0.1: Confirm current uncommitted work before editing**

Run:

```bash
rtk git status --short
```

Expected:

- Existing unrelated user changes may be present.
- Do not revert files not touched by this plan.
- If the earlier `authz-check` implementation is still uncommitted in `backend/manage.py` / `backend/tests/unit/test_manage.py`, this plan supersedes it. Remove those additions as part of Task 7.

- [x] **Step 0.2: Read relevant local instructions**

Run:

```bash
rtk read AGENTS.md
rtk read backend/AGENTS.md
rtk read frontend/AGENTS.md
rtk grep -n "AuthorizationUsecase|AuthorizationRepository|OAuthOidcUsecase|Logger" backend/tests
```

Expected:

- Confirm docs are Japanese.
- Confirm DB schema change requires clear migration plan.
- Confirm quality gates before completion.
- Confirm bootstrap/DI tests that resolve authorization components are included in the task impact list.

## Task 1: Add code-managed catalog helpers

**Files:**

- Modify: `backend/app/config/authorization.py`
- Modify: `backend/app/bootstrap/create_app.py`
- Modify: `backend/tests/unit/models/test_authorization.py`
- Modify: `backend/tests/unit/bootstrap/test_create_app.py`

- [x] **Step 1.1: Write failing tests for catalog validation and lookup**

Add tests that describe the desired code-only behavior.

```python
from uuid import uuid4

from app.config.authorization import (
    DEFAULT_AUTHORIZATION_DEFINITIONS,
    DEFAULT_AUTHORIZATION_PERMISSIONS,
    authorization_config_errors,
    permission_catalog_by_code,
    permissions_for_role_codes,
    role_catalog_by_code,
    roles_with_permissions,
    unknown_role_codes,
    user_authorization_from_role_codes,
)
from app.models.authorization import PermissionDefinition, RoleDefinition


def test_default_authorization_config_is_valid():
    assert authorization_config_errors(
        DEFAULT_AUTHORIZATION_PERMISSIONS,
        DEFAULT_AUTHORIZATION_DEFINITIONS,
    ) == []


def test_role_catalog_by_code_rejects_duplicate_role_codes():
    errors = authorization_config_errors(
        DEFAULT_AUTHORIZATION_PERMISSIONS,
        (
            RoleDefinition("admin", "Admin", permission_codes=("admin:access",)),
            RoleDefinition("admin", "Admin duplicate", permission_codes=("admin:access",)),
        ),
    )

    assert errors == ["Duplicate role codes: admin"]


def test_permission_catalog_by_code_rejects_duplicate_permission_codes():
    errors = authorization_config_errors(
        (
            PermissionDefinition("admin:access", "Admin access"),
            PermissionDefinition("admin:access", "Admin access duplicate"),
        ),
        DEFAULT_AUTHORIZATION_DEFINITIONS,
    )

    assert errors == ["Duplicate permission codes: admin:access"]


def test_authorization_config_rejects_unknown_role_permission_reference():
    errors = authorization_config_errors(
        DEFAULT_AUTHORIZATION_PERMISSIONS,
        (
            RoleDefinition("admin", "Admin", permission_codes=("missing:permission",)),
        ),
    )

    assert errors == ["Role admin references unknown permissions: missing:permission"]


def test_authorization_config_rejects_codes_longer_than_storage_contract():
    errors = authorization_config_errors(
        (
            PermissionDefinition("p" * 121, "Too long"),
        ),
        (
            RoleDefinition("r" * 65, "Too long", permission_codes=()),
        ),
    )

    assert errors == [
        "Permission code exceeds 120 characters: " + "p" * 121,
        "Role code exceeds 64 characters: " + "r" * 65,
    ]


def test_authorization_config_rejects_empty_codes():
    errors = authorization_config_errors(
        (
            PermissionDefinition("", "Empty"),
        ),
        (
            RoleDefinition("", "Empty", permission_codes=()),
        ),
    )

    assert errors == [
        "Permission code must not be empty.",
        "Role code must not be empty.",
    ]


def test_authorization_config_rejects_empty_catalogs():
    errors = authorization_config_errors((), ())

    assert errors == [
        "Permission catalog must not be empty.",
        "Role catalog must not be empty.",
    ]


def test_permissions_for_role_codes_resolves_permissions_from_code_catalog():
    permissions = permissions_for_role_codes(("admin",))

    assert permissions == frozenset({"admin:access"})


def test_permissions_for_role_codes_ignores_unknown_role_codes():
    permissions = permissions_for_role_codes(("missing", "admin"))

    assert permissions == frozenset({"admin:access"})


def test_unknown_role_codes_reports_unknown_assignments():
    assert unknown_role_codes(("missing", "admin", "missing")) == frozenset({"missing"})


def test_user_authorization_from_role_codes_filters_unknown_roles_and_permissions():
    authorization = user_authorization_from_role_codes(
        user_id=uuid4(),
        role_codes=("missing", "admin"),
    )

    assert authorization.roles == frozenset({"admin"})
    assert authorization.permissions == frozenset({"admin:access"})


def test_roles_with_permissions_returns_catalog_for_admin_api():
    roles = roles_with_permissions()
    permissions = permission_catalog_by_code()
    role_catalog = role_catalog_by_code()

    assert set(role_catalog) == {"admin"}
    assert set(permissions) == {"admin:access"}
    assert roles[0].code == "admin"
    assert roles[0].permissions == ("admin:access",)
```

- [x] **Step 1.2: Run the tests and verify they fail**

Run:

```bash
cd backend
uv run pytest tests/unit/models/test_authorization.py -q
```

Expected:

- FAIL because `authorization_config_errors`, `permission_catalog_by_code`, `role_catalog_by_code`, `permissions_for_role_codes`, `unknown_role_codes`, `user_authorization_from_role_codes`, and `roles_with_permissions` do not exist yet.

- [x] **Step 1.3: Implement catalog helper functions**

In `backend/app/config/authorization.py`, keep existing definitions and add helper functions.

```python
from collections import Counter
from collections.abc import Iterable
from uuid import UUID

from app.models.authorization import (
    PermissionDefinition,
    RoleDefinition,
    RoleWithPermissions,
    UserAuthorization,
)

ROLE_CODE_MAX_LENGTH = 64
PERMISSION_CODE_MAX_LENGTH = 120


def permission_catalog_by_code(
    permissions: tuple[PermissionDefinition, ...] = DEFAULT_AUTHORIZATION_PERMISSIONS,
) -> dict[str, PermissionDefinition]:
    return {permission.code: permission for permission in permissions}


def role_catalog_by_code(
    roles: tuple[RoleDefinition, ...] = DEFAULT_AUTHORIZATION_DEFINITIONS,
) -> dict[str, RoleDefinition]:
    return {role.code: role for role in roles}


def authorization_config_errors(
    permissions: tuple[PermissionDefinition, ...] = DEFAULT_AUTHORIZATION_PERMISSIONS,
    roles: tuple[RoleDefinition, ...] = DEFAULT_AUTHORIZATION_DEFINITIONS,
) -> list[str]:
    errors: list[str] = []
    permission_counts = Counter(permission.code for permission in permissions)
    role_counts = Counter(role.code for role in roles)
    duplicate_permissions = sorted(code for code, count in permission_counts.items() if count > 1)
    duplicate_roles = sorted(code for code, count in role_counts.items() if count > 1)
    empty_permissions = sorted(code for code in permission_counts if not code)
    empty_roles = sorted(code for code in role_counts if not code)
    oversized_permissions = sorted(
        code for code in permission_counts if code and len(code) > PERMISSION_CODE_MAX_LENGTH
    )
    oversized_roles = sorted(
        code for code in role_counts if code and len(code) > ROLE_CODE_MAX_LENGTH
    )
    if duplicate_permissions:
        errors.append(f"Duplicate permission codes: {', '.join(duplicate_permissions)}")
    if duplicate_roles:
        errors.append(f"Duplicate role codes: {', '.join(duplicate_roles)}")
    if not permissions:
        errors.append("Permission catalog must not be empty.")
    if not roles:
        errors.append("Role catalog must not be empty.")
    if empty_permissions:
        errors.append("Permission code must not be empty.")
    if empty_roles:
        errors.append("Role code must not be empty.")
    for code in oversized_permissions:
        errors.append(f"Permission code exceeds 120 characters: {code}")
    for code in oversized_roles:
        errors.append(f"Role code exceeds 64 characters: {code}")
    permission_codes = frozenset(permission_counts)
    for role in roles:
        missing_permissions = sorted(frozenset(role.permission_codes) - permission_codes)
        if missing_permissions:
            errors.append(
                f"Role {role.code} references unknown permissions: "
                f"{', '.join(missing_permissions)}"
            )
    return errors


def unknown_role_codes(role_codes: Iterable[str]) -> frozenset[str]:
    roles = role_catalog_by_code()
    return frozenset(code for code in role_codes if code not in roles)


def permissions_for_role_codes(role_codes: Iterable[str]) -> frozenset[str]:
    roles = role_catalog_by_code()
    permissions: set[str] = set()
    for role_code in role_codes:
        role = roles.get(role_code)
        if role is None:
            continue
        permissions.update(role.permission_codes)
    return frozenset(permissions)


def user_authorization_from_role_codes(
    user_id: UUID,
    role_codes: Iterable[str],
) -> UserAuthorization:
    normalized_role_codes = tuple(dict.fromkeys(role_codes))
    roles = role_catalog_by_code()
    known_role_codes = tuple(code for code in normalized_role_codes if code in roles)
    return UserAuthorization(
        user_id=user_id,
        roles=frozenset(known_role_codes),
        permissions=permissions_for_role_codes(known_role_codes),
    )


def roles_with_permissions() -> list[RoleWithPermissions]:
    return [
        RoleWithPermissions(
            code=role.code,
            display_name=role.display_name,
            description=role.description,
            permissions=tuple(sorted(dict.fromkeys(role.permission_codes))),
        )
        for role in sorted(DEFAULT_AUTHORIZATION_DEFINITIONS, key=lambda role: role.code)
    ]
```

- [x] **Step 1.4: Add startup validation**

In `backend/app/bootstrap/create_app.py`, call `authorization_config_errors()` at the start of `create_app()`, before `build_container()`. If it returns any errors, raise `RuntimeError("Authorization config is invalid: ...")` before DB/container setup and before routes are registered.

Add a unit test in `backend/tests/unit/bootstrap/test_create_app.py` that monkeypatches `create_app_module.authorization_config_errors` to return `["Role admin references unknown permissions: missing"]` and asserts `create_app()` raises `RuntimeError`.

- [x] **Step 1.5: Run tests and verify they pass**

Run:

```bash
cd backend
uv run pytest tests/unit/models/test_authorization.py tests/unit/bootstrap/test_create_app.py -q
```

Expected:

- PASS.

## Task 2: Change authorization DB model to `user_roles(role_code)`

**Files:**

- Modify: `backend/app/models/authorization.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260810_0001_initial_schema.py`
- Modify: `backend/tests/unit/models/test_authorization.py`
- Modify: `backend/tests/unit/models/test_metadata.py`
- Modify: `backend/tests/integration/conftest.py`

- [x] **Step 2.1: Write failing model metadata test**

Add or update tests so `UserRole` exposes `role_code` and no longer depends on `Role` / `Permission` SQLModel tables.

```python
from app.models.authorization import UserRole


def test_user_role_uses_role_code_assignment():
    columns = UserRole.__table__.columns

    assert "user_id" in columns
    assert "role_code" in columns
    assert "role_id" not in columns
```

Also update `backend/tests/unit/models/test_metadata.py` in this step:

- Remove `permissions`, `roles`, and `role_permissions` from `EXPECTED_TABLE_MODELS`.
- Change `test_authorization_foreign_keys_have_deterministic_names` so `user_roles` only has `fk_user_roles_user_id_users` and `fk_user_roles_assigned_by_user_id_users`.
- Change `test_authorization_table_shape_matches_plan` so it asserts `user_roles.c.role_code.type.length == 64`, `role_id` is absent, and `{index.name for index in user_roles.indexes} == {"ix_user_roles_role_code"}`.
- Delete assertions for `roles`, `permissions`, and `role_permissions` table shape.

- [ ] **Step 2.2: Run model test and verify failure**

Run:

```bash
cd backend
uv run pytest \
  tests/unit/models/test_authorization.py::test_user_role_uses_role_code_assignment \
  tests/unit/models/test_metadata.py::test_app_models_init_imports_all_table_models_for_alembic_metadata \
  tests/unit/models/test_metadata.py::test_authorization_foreign_keys_have_deterministic_names \
  tests/unit/models/test_metadata.py::test_authorization_table_shape_matches_plan \
  -q
```

Expected:

- FAIL because `UserRole` still has `role_id`.

- [x] **Step 2.3: Modify SQLModel definitions**

In `backend/app/models/authorization.py`:

- Delete table classes `Role`, `Permission`, and `RolePermission`.
- Keep dataclasses `RoleDefinition`, `PermissionDefinition`, `UserAuthorization`, `RoleWithPermissions`, `UserRoleReplacementResult`.
- Add dataclass `UnknownRoleAssignment(user_id: UUID, role_code: str)` for CLI orphan assignment reporting.
- Remove `current_permission_codes` from `UserRoleReplacementResult`; callers compute response permissions from code catalog at the boundary.
- Change `UserRole` to store `role_code`.

Target shape:

```python
class UserRole(SQLModel, table=True):
    __tablename__ = "user_roles"
    __table_args__ = (Index("ix_user_roles_role_code", "role_code"),)

    user_id: UUID = Field(sa_column=Column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    ))
    role_code: str = Field(sa_column=Column(String(length=64), nullable=False, primary_key=True))
    assigned_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow)
    )
    assigned_by_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid,
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
```

In `backend/app/models/__init__.py`, remove exports for `Permission`, `Role`, and `RolePermission`.

- [x] **Step 2.4: Create migration from catalog tables to code-managed assignment**

Post-implementation squash: because no migration from this repository had been
applied yet, the development-only migration chain was replaced with
`backend/alembic/versions/20260810_0001_initial_schema.py`. The squashed
initial revision creates `user_roles.role_code` directly and never creates
`roles`, `permissions`, or `role_permissions`.

The pre-squash transition migration design was:

Migration behavior:

- Add `user_roles.role_code` nullable.
- Backfill `role_code` from existing `roles.code`.
- Make `role_code` non-null.
- Drop old PK on `(user_id, role_id)`.
- Drop old `role_id` FK and column. PostgreSQL will drop the dependent `ix_user_roles_role_id` index with the column; do not add a redundant explicit `drop_index` unless local verification shows it is required.
- Create PK on `(user_id, role_code)`.
- Create `ix_user_roles_role_code`.
- Drop `role_permissions`, `permissions`, and `roles`.

Important:

- Existing user assignments must survive.
- Unknown role cannot exist before this migration because old schema had FK to `roles`.
- Downgrade must not import `app.config.authorization` or any app code. Alembic revisions must be schema/data snapshots, not live application definitions.
- Downgrade must recreate `roles`, `permissions`, and `role_permissions` from literal constants embedded in `20260810_0006_code_managed_authorization.py`, then backfill `user_roles.role_id` by joining `user_roles.role_code` to recreated `roles.code`.
- Downgrade must fail before destructively changing `user_roles` if `user_roles.role_code` contains a code that is not present in the migration's `_ROLES` snapshot; otherwise old code would come back with assignments that cannot be joined.
- Downgrade cannot restore custom DB catalog rows because custom role catalog is explicitly out of scope. Document that limitation in the migration docstring.
- The `ix_user_roles_role_code` index is kept because repair/inspection commands need to find users by role code and future role rename/delete migrations need bounded scans.

Embed the catalog snapshot in the migration:

```python
_ROLES = (
    ("00000000-0000-0000-0000-000000000001", "admin", "Admin", "Full administrative access for this template."),
)
_PERMISSIONS = (
    ("00000000-0000-0000-0000-000000000101", "admin:access", "Admin access", "Access administrative endpoints."),
)
_ROLE_PERMISSIONS = (("admin", "admin:access"),)
```

Pseudo migration:

```python
def upgrade() -> None:
    op.add_column("user_roles", sa.Column("role_code", sa.String(length=64), nullable=True))
    op.execute("""
        UPDATE user_roles
        SET role_code = roles.code
        FROM roles
        WHERE user_roles.role_id = roles.id
    """)
    op.alter_column("user_roles", "role_code", nullable=False)
    op.drop_constraint(op.f("pk_user_roles"), "user_roles", type_="primary")
    op.drop_constraint(op.f("fk_user_roles_role_id_roles"), "user_roles", type_="foreignkey")
    op.drop_column("user_roles", "role_id")
    op.create_primary_key(op.f("pk_user_roles"), "user_roles", ["user_id", "role_code"])
    op.create_index("ix_user_roles_role_code", "user_roles", ["role_code"], unique=False)
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
```

Pseudo downgrade:

```python
def downgrade() -> None:
    # Recreate catalog tables with the same columns/indexes as 20260808_0005.
    # Insert the literal _ROLES, _PERMISSIONS, and _ROLE_PERMISSIONS snapshot.
    # Use fixed UUID literals from the snapshot and sa.func.now() for NOT NULL
    # created_at / updated_at fields.
    # Abort before changing user_roles if any existing role_code is absent from _ROLES.
    role_codes_sql = ", ".join(f"'{code}'" for _, code, _, _ in _ROLES)
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM user_roles
                WHERE role_code NOT IN ({role_codes_sql})
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade: user_roles contains unknown role_code';
            END IF;
        END $$;
    """)
    # Create roles, permissions, and role_permissions, then INSERT by looping over
    # _ROLES, _PERMISSIONS, and _ROLE_PERMISSIONS.
    op.add_column("user_roles", sa.Column("role_id", sa.Uuid(), nullable=True))
    op.execute("""
        UPDATE user_roles
        SET role_id = roles.id
        FROM roles
        WHERE user_roles.role_code = roles.code
    """)
    op.drop_constraint(op.f("pk_user_roles"), "user_roles", type_="primary")
    op.alter_column("user_roles", "role_id", nullable=False)
    op.drop_column("user_roles", "role_code")
    op.create_primary_key(op.f("pk_user_roles"), "user_roles", ["user_id", "role_id"])
    op.create_foreign_key(
        op.f("fk_user_roles_role_id_roles"),
        "user_roles",
        "roles",
        ["role_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"], unique=False)
```

- [x] **Step 2.5: Update integration cleanup table order**

In `backend/tests/integration/conftest.py`, remove `role_permissions`, `permissions`, and `roles` from truncate cleanup list. Keep `user_roles`.

- [x] **Step 2.6: Run model tests**

Run:

```bash
cd backend
uv run pytest tests/unit/models/test_authorization.py tests/unit/models/test_metadata.py -q
```

Expected:

- PASS.

## Task 3: Rewrite authorization repository around role codes

Task 2 and Task 3 are one atomic implementation unit. After `Role`, `Permission`, and `RolePermission` SQLModel classes are removed, `authorization_repository.py` imports will fail until Task 3 is complete. Do not run or report full `tests/unit` between the middle of Task 2 and the end of Task 3; use the targeted model/metadata tests named in Task 2, then immediately complete Task 3.

**Files:**

- Modify: `backend/app/interfaces/services/authorization_repository_interface.py`
- Modify: `backend/app/services/authorization_repository.py`
- Replace or heavily modify: `backend/tests/unit/services/test_authorization_repository.py`
- Replace or heavily modify: `backend/tests/integration/services/test_authorization_repository.py`

- [x] **Step 3.1: Write failing repository tests for code-managed behavior**

The repository should no longer upsert catalog rows. It should only read/write `user_roles`.

Expected interface:

```python
class AuthorizationRepositoryInterface(metaclass=ABCMeta):
    async def get_user_role_codes(self, user_id: UUID) -> tuple[str, ...]: ...
    async def list_unknown_role_assignments(
        self,
        known_role_codes: frozenset[str],
    ) -> tuple[UnknownRoleAssignment, ...]: ...
    async def delete_unknown_role_assignments(self, known_role_codes: frozenset[str]) -> int: ...
    async def replace_user_roles(
        self,
        user_id: UUID,
        role_codes: tuple[str, ...],
        assigned_by_user_id: UUID | None,
    ) -> UserRoleReplacementResult: ...
    async def delete_roles_for_user(self, user_id: UUID) -> int: ...
```

Add tests:

```python
async def test_replace_user_roles_grants_revokes_and_returns_role_codes(
    authorization_repository,
    auth_repository,
):
    user = await auth_repository.create_user("role-code@example.com", "hash")

    first_result = await authorization_repository.replace_user_roles(
        user.id,
        ("admin",),
        assigned_by_user_id=None,
    )
    second_result = await authorization_repository.replace_user_roles(
        user.id,
        (),
        assigned_by_user_id=None,
    )

    assert first_result.granted_role_codes == ("admin",)
    assert first_result.current_role_codes == ("admin",)
    assert second_result.revoked_role_codes == ("admin",)
    assert second_result.current_role_codes == ()
```

```python
async def test_get_user_role_codes_returns_stable_order(
    authorization_repository,
    auth_repository,
):
    user = await auth_repository.create_user("stable-roles@example.com", "hash")

    await authorization_repository.replace_user_roles(
        user.id,
        ("support", "admin"),
        assigned_by_user_id=None,
    )

    assert await authorization_repository.get_user_role_codes(user.id) == ("admin", "support")
```

```python
async def test_delete_roles_for_user_removes_only_target_assignments(
    authorization_repository,
    auth_repository,
):
    target_user = await auth_repository.create_user("delete-target@example.com", "hash")
    other_user = await auth_repository.create_user("delete-other@example.com", "hash")
    await authorization_repository.replace_user_roles(target_user.id, ("admin",), None)
    await authorization_repository.replace_user_roles(other_user.id, ("admin",), None)

    deleted_count = await authorization_repository.delete_roles_for_user(target_user.id)

    assert deleted_count == 1
    assert await authorization_repository.get_user_role_codes(target_user.id) == ()
    assert await authorization_repository.get_user_role_codes(other_user.id) == ("admin",)
```

```python
async def test_unknown_role_assignment_helpers_report_and_prune_orphan_codes(
    authorization_repository,
    auth_repository,
):
    user = await auth_repository.create_user("orphan-role@example.com", "hash")
    await authorization_repository.replace_user_roles(user.id, ("admin", "deleted-role"), None)

    assignments = await authorization_repository.list_unknown_role_assignments(frozenset({"admin"}))
    deleted_count = await authorization_repository.delete_unknown_role_assignments(
        frozenset({"admin"})
    )

    assert [(assignment.user_id, assignment.role_code) for assignment in assignments] == [
        (user.id, "deleted-role")
    ]
    assert deleted_count == 1
    assert await authorization_repository.get_user_role_codes(user.id) == ("admin",)
```

- [ ] **Step 3.2: Run repository tests and verify failure**

Run:

```bash
cd backend
uv run pytest tests/unit/services/test_authorization_repository.py -q
```

Expected:

- FAIL because repository still expects `roles`, `permissions`, and `role_permissions` DB tables.

- [x] **Step 3.3: Update repository interface**

Remove these methods from `AuthorizationRepositoryInterface`:

- `upsert_permission_definition`
- `upsert_role_definition`
- `replace_role_permissions`
- `list_roles_with_permissions`
- `list_permissions`
- `get_user_authorization`
- `get_existing_user_authorization`

Add:

```python
@abstractmethod
async def get_user_role_codes(self, user_id: UUID) -> tuple[str, ...]:
    raise NotImplementedError


@abstractmethod
async def list_unknown_role_assignments(
    self,
    known_role_codes: frozenset[str],
) -> tuple[UnknownRoleAssignment, ...]:
    raise NotImplementedError


@abstractmethod
async def delete_unknown_role_assignments(self, known_role_codes: frozenset[str]) -> int:
    raise NotImplementedError
```

Keep:

- `replace_user_roles`
- `delete_roles_for_user`

- [x] **Step 3.4: Update repository implementation**

`AuthorizationRepository` should:

- Delete all `Role`, `Permission`, and `RolePermission` imports.
- Delete catalog upsert/list methods.
- Implement `get_user_role_codes()` from `user_roles.role_code`.
- Implement `replace_user_roles()` by diffing existing role_code set vs target role_code set.
- Implement `_role_codes_for_user()` as `SELECT UserRole.role_code ... ORDER BY UserRole.role_code`.
- Implement `list_unknown_role_assignments()` and `delete_unknown_role_assignments()` for DB orphan inspection/repair commands.
- Handle empty `known_role_codes` explicitly: `list_unknown_role_assignments(frozenset())` returns every assignment as unknown; `delete_unknown_role_assignments(frozenset())` deletes every assignment only when the caller has already required an explicit destructive confirmation.
- Do not validate role codes in repository. Repository is storage-only; write validation happens in usecase/CLI.
- Do not calculate or return permissions from repository. `UserRoleReplacementResult` no longer has `current_permission_codes`.

Target repository logic:

```python
async def get_user_role_codes(self, user_id: UUID) -> tuple[str, ...]:
    async with self._unit_of_work.session_scope() as session:
        return await self._role_codes_for_user(session, user_id)


async def replace_user_roles(
    self,
    user_id: UUID,
    role_codes: tuple[str, ...],
    assigned_by_user_id: UUID | None,
) -> UserRoleReplacementResult:
    target_codes = tuple(dict.fromkeys(role_codes))
    async with self._unit_of_work.session_scope() as session:
        existing_role_codes = await self._role_codes_for_user(session, user_id)
        existing_set = frozenset(existing_role_codes)
        target_set = frozenset(target_codes)
        revoked = tuple(sorted(existing_set - target_set))
        granted = tuple(sorted(target_set - existing_set))

        if revoked:
            await session.exec(
                delete(UserRole).where(
                    col(UserRole.user_id) == user_id,
                    col(UserRole.role_code).in_(revoked),
                )
            )
        for code in granted:
            session.add(
                UserRole(
                    user_id=user_id,
                    role_code=code,
                    assigned_at=utcnow(),
                    assigned_by_user_id=assigned_by_user_id,
                )
            )

        await self._persist(session)
        return UserRoleReplacementResult(
            user_id=user_id,
            granted_role_codes=granted,
            revoked_role_codes=revoked,
            current_role_codes=tuple(sorted(target_set)),
        )
```

- [x] **Step 3.5: Run repository tests**

Run:

```bash
cd backend
uv run pytest tests/unit/services/test_authorization_repository.py -q
```

Expected:

- PASS.

## Task 4: Move permission resolution to code catalog usecase

**Files:**

- Modify: `backend/app/models/authorization_errors.py`
- Modify: `backend/app/usecases/authorization_usecase.py`
- Modify: `backend/app/interfaces/usecases/authorization_usecase_interface.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/app/usecases/oauth_oidc_usecase.py`
- Modify: `backend/tests/unit/usecases/test_authorization_usecase.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/unit/usecases/test_oauth_oidc_usecase.py`
- Modify: `backend/tests/unit/bootstrap/test_authorization_module.py`

- [x] **Step 4.1: Write failing usecase tests**

Authorization usecase should validate role codes against code catalog, list catalog from code, and compute permissions from role codes.

Add tests:

```python
async def test_list_roles_uses_code_catalog(authorization_usecase):
    roles = await authorization_usecase.list_roles()

    assert [role.code for role in roles] == ["admin"]
    assert roles[0].permissions == ("admin:access",)
```

```python
async def test_list_permissions_uses_code_catalog(authorization_usecase):
    permissions = await authorization_usecase.list_permissions()

    assert [permission.code for permission in permissions] == ["admin:access"]
```

```python
async def test_get_user_authorization_resolves_permissions_from_role_codes(
    authorization_usecase,
    authorization_repository,
    user,
):
    authorization_repository.get_user_role_codes.return_value = ("admin",)

    authorization = await authorization_usecase.get_user_authorization(user.id)

    assert authorization.roles == frozenset({"admin"})
    assert authorization.permissions == frozenset({"admin:access"})
```

```python
async def test_get_user_authorization_ignores_unknown_role_for_permissions(
    authorization_usecase,
    authorization_repository,
    user,
    caplog,
):
    authorization_repository.get_user_role_codes.return_value = ("deleted-role", "admin")

    authorization = await authorization_usecase.get_user_authorization(user.id)

    assert authorization.roles == frozenset({"admin"})
    assert authorization.permissions == frozenset({"admin:access"})
    assert "Unknown role codes ignored while resolving authorization" in caplog.text
```

```python
async def test_replace_user_roles_rejects_unknown_role_before_repository_write(
    authorization_usecase,
    authorization_repository,
    actor_context,
    target_user,
):
    with pytest.raises(RoleNotFoundError) as exc_info:
        await authorization_usecase.replace_user_roles(
            actor_context,
            target_user.id,
            ("missing",),
            ip_address=None,
            user_agent=None,
        )

    assert exc_info.value.role_codes == frozenset({"missing"})
    authorization_repository.replace_user_roles.assert_not_called()
```

- [ ] **Step 4.2: Run usecase tests and verify failure**

Run:

```bash
cd backend
uv run pytest tests/unit/usecases/test_authorization_usecase.py -q
```

Expected:

- FAIL because usecase still delegates catalog and permission resolution to repository.

- [x] **Step 4.3: Update domain errors if needed**

Keep `RoleNotFoundError` for unknown role codes.

Remove `PermissionNotFoundError` if no code path uses it after catalog table removal. If config validation detects unknown permission references, it should return config errors rather than runtime domain error.

- [x] **Step 4.4: Update authorization usecase**

Use config helpers from Task 1.

Add `logger: Logger` to `AuthorizationUsecase.__init__` and store it as `self._logger`. `Logger` is provided by `CoreModule`.

Update `backend/tests/unit/bootstrap/test_authorization_module.py`: import `CoreModule` and construct `Injector([CoreModule(), DatabaseModule(), AuthModule()])` in `test_auth_module_resolves_authorization_usecase_from_container()`. Without `CoreModule`, resolving `AuthorizationUsecaseInterface` after adding Logger injection will fail.

Target behavior:

```python
async def list_roles(self) -> list[RoleWithPermissions]:
    return roles_with_permissions()


async def list_permissions(self) -> list[PermissionDefinition]:
    return sorted(permission_catalog_by_code().values(), key=lambda permission: permission.code)


async def get_user_authorization(self, user_id: UUID) -> UserAuthorization:
    user = await self._auth_repository.find_user_by_id_for_authentication(user_id)
    if user is None or user.deleted_at is not None:
        raise AuthorizationUserNotFoundError(user_id)
    role_codes = await self._authorization_repository.get_user_role_codes(user_id)
    unknown_codes = unknown_role_codes(role_codes)
    if unknown_codes:
        self._logger.warning(
            "Unknown role codes ignored while resolving authorization",
            extra={"user_id": str(user_id), "role_codes": sorted(unknown_codes)},
        )
    return user_authorization_from_role_codes(user_id, role_codes)
```

For `replace_user_roles()`:

- Normalize duplicate role codes.
- Validate all target role codes exist in `role_catalog_by_code()`.
- Call repository only after validation.
- Return the repository `UserRoleReplacementResult` unchanged. It contains only role changes; controller/CLI compute permissions for public output from `result.current_role_codes`.
- Continue writing one audit row per grant/revoke.

- [x] **Step 4.5: Update `AuthUsecase` and OIDC usecase**

`AuthUsecase.login()` and `AuthUsecase.authenticate_session()` currently call repository methods returning `UserAuthorization`. Keep dependency direction simple: do not inject `AuthorizationUsecaseInterface` into auth/OIDC usecases; use the code catalog helper with repository role-code reads.

Use one shared helper from `backend/app/config/authorization.py` rather than copying `UserAuthorization` construction:

- Keep `AuthUsecase` injected with `AuthorizationRepositoryInterface`.
- Add private helper in `AuthUsecase`:

```python
async def _authorization_for_existing_user(self, user_id: UUID) -> UserAuthorization:
    role_codes = await self._authorization_repository.get_user_role_codes(user_id)
    unknown_codes = unknown_role_codes(role_codes)
    if unknown_codes:
        self._logger.warning(
            "Unknown role codes ignored while resolving authorization",
            extra={"user_id": str(user_id), "role_codes": sorted(unknown_codes)},
        )
    return user_authorization_from_role_codes(user_id, role_codes)
```

- Replace `get_existing_user_authorization(user.id)` with `_authorization_for_existing_user(user.id)`.

Apply the same pattern in `OAuthOidcUsecase`; add `logger: Logger` to `OAuthOidcUsecase.__init__` and store it as `self._logger` so unknown role assignments are observable there too.

- [x] **Step 4.6: Run affected unit tests**

Run:

```bash
cd backend
uv run pytest \
  tests/unit/usecases/test_authorization_usecase.py \
  tests/unit/usecases/test_auth_usecase.py \
  tests/unit/usecases/test_oauth_oidc_usecase.py \
  tests/unit/bootstrap/test_authorization_module.py \
  -q
```

Expected:

- PASS.

## Task 5: Update admin controller API while preserving public response

**Files:**

- Modify: `backend/app/controllers/authorization_controller.py`
- Modify: `backend/tests/unit/controllers/test_authorization_controller.py`
- Modify: `backend/tests/integration/test_authorization_controller.py`

- [x] **Step 5.1: Write or update tests for code catalog API**

`GET /api/admin/roles` should still return:

```json
{
  "roles": [
    {
      "code": "admin",
      "displayName": "Admin",
      "description": "Full administrative access for this template.",
      "permissions": ["admin:access"]
    }
  ],
  "permissions": [
    {
      "code": "admin:access",
      "displayName": "Admin access",
      "description": "Access administrative endpoints."
    }
  ]
}
```

But tests should no longer seed `roles`, `permissions`, or `role_permissions` tables. They should only assign `user_roles.role_code = "admin"` to admin test users.

- [ ] **Step 5.2: Run controller tests and verify failure**

Run:

```bash
cd backend
uv run pytest \
  tests/unit/controllers/test_authorization_controller.py \
  tests/integration/test_authorization_controller.py \
  -q
```

Expected:

- FAIL until test fixtures and usecase are updated away from DB catalog.

- [x] **Step 5.3: Keep controller response mapping, remove DB catalog assumptions**

Controller likely needs minimal changes if usecase methods keep the same public signatures:

- `list_roles()` returns code catalog roles.
- `list_permissions()` returns code catalog permissions.
- `get_user_authorization()` returns permissions computed from code.
- `replace_user_roles()` validates target role codes in usecase.
- `_user_role_replace_response()` computes `permissions=list(sorted(permissions_for_role_codes(result.current_role_codes)))` because `UserRoleReplacementResult` no longer carries permission codes.

Keep:

- `require_admin_access = require_permission("admin:access")`
- `GET /api/admin/roles`
- `GET /api/admin/users/{user_id}/roles`
- `PUT /api/admin/users/{user_id}/roles`
- PUT response includes permissions derived from the current role codes.
- `422 ROLE_NOT_FOUND`
- `404 USER_NOT_FOUND`
- CSRF behavior.

- [x] **Step 5.4: Run controller tests**

Run:

```bash
cd backend
uv run pytest \
  tests/unit/controllers/test_authorization_controller.py \
  tests/integration/test_authorization_controller.py \
  -q
```

Expected:

- PASS.

## Task 6: Remove authz-sync/check CLI and add config / assignment check CLI

**Files:**

- Modify: `backend/manage.py`
- Modify: `backend/tests/unit/test_manage.py`
- Modify: `backend/tests/integration/test_manage_cli.py`

- [x] **Step 6.1: Write failing CLI tests**

Remove tests for:

- `authz-sync`
- `authz-sync --check`
- `authz-check`

Add tests for:

For commands that normally read `DATABASE_URL` or build the DI container, follow the existing `backend/tests/unit/test_manage.py` style: monkeypatch `_get_explicit_database_settings` and `run_with_container` so the unit tests stay DB-free.

```python
def test_authz_check_config_passes_for_default_definitions():
    result = CliRunner().invoke(manage.app, ["authz-check-config"])

    assert result.exit_code == 0
    assert "Authorization config is valid." in result.stdout
```

```python
def test_authz_grant_role_rejects_unknown_code_role_before_repository_write(monkeypatch):
    async def fail_if_called(operation):
        raise AssertionError("container should not be built for unknown role")

    monkeypatch.setattr(manage, "run_with_container", fail_if_called)

    result = CliRunner().invoke(
        manage.app,
        ["authz-grant-role", "--email", "admin@example.com", "--role", "missing"],
    )

    assert result.exit_code == 1
    assert "Role not found: missing" in result.stderr
```

```python
def test_authz_check_assignments_reports_unknown_role_codes(monkeypatch):
    unknown = (UnknownRoleAssignment(user_id=uuid4(), role_code="deleted-role"),)

    class AuthorizationRepositoryStub:
        async def list_unknown_role_assignments(self, known_role_codes):
            return unknown

    class ContainerStub:
        def get(self, interface):
            if interface is AuthorizationRepositoryInterface:
                return AuthorizationRepositoryStub()
            raise AssertionError(f"Unexpected interface: {interface}")

    async def run_with_container_stub(operation):
        return await operation(ContainerStub())

    monkeypatch.setattr(manage, "_get_explicit_database_settings", lambda command_name: None)
    monkeypatch.setattr(manage, "run_with_container", run_with_container_stub)

    result = CliRunner().invoke(manage.app, ["authz-check-assignments"])

    assert result.exit_code == 1
    assert "Unknown role assignments found." in result.stderr
    assert "deleted-role" in result.stderr
```

```python
def test_authz_prune_unknown_role_assignments_requires_yes(monkeypatch):
    async def fail_if_called(operation):
        raise AssertionError("container should not be built without --yes")

    monkeypatch.setattr(manage, "run_with_container", fail_if_called)

    result = CliRunner().invoke(manage.app, ["authz-prune-unknown-role-assignments"])

    assert result.exit_code == 1
    assert "Pass --yes to delete unknown role assignments." in result.stderr
```

```python
def test_authz_prune_unknown_role_assignments_rejects_invalid_config(monkeypatch):
    monkeypatch.setattr(
        manage,
        "authorization_config_errors",
        lambda: ["Role catalog must not be empty."],
    )

    async def fail_if_called(operation):
        raise AssertionError("container should not be built for invalid authorization config")

    monkeypatch.setattr(manage, "run_with_container", fail_if_called)

    result = CliRunner().invoke(
        manage.app,
        ["authz-prune-unknown-role-assignments", "--yes"],
    )

    assert result.exit_code == 1
    assert "Authorization config is invalid." in result.stderr
    assert "Role catalog must not be empty." in result.stderr
```

Also add a `--yes` unit test that stubs both `AuthorizationRepositoryInterface` and `AuthRepositoryInterface` and asserts:

- `list_unknown_role_assignments()` is called before `delete_unknown_role_assignments()`.
- delete and audit happen inside `UnitOfWorkInterface.transaction()`.
- One `ROLE_REVOKED` audit log is written per unknown assignment.
- Audit `detail_json` includes `source="cli-prune"`, `targetUserId`, and `roleCode`.

- [ ] **Step 6.2: Run CLI tests and verify failure**

Run:

```bash
cd backend
uv run pytest tests/unit/test_manage.py -q
```

Expected:

- FAIL because `authz-check-config`, `authz-check-assignments`, and `authz-prune-unknown-role-assignments` are missing and `authz-grant-role` still relies on repository role validation.

- [x] **Step 6.3: Remove sync/check DB commands**

In `backend/manage.py`:

- Delete `authz_sync`.
- Delete `authz_check`.
- Delete `_sync_default_authorization`.
- Delete `_check_default_authorization`.
- Delete `_default_authorization_drift_messages`.
- Delete `_code_set_drift_messages`.
- Remove imports of `DEFAULT_AUTHORIZATION_DEFINITIONS` and `DEFAULT_AUTHORIZATION_PERMISSIONS` if replaced by config helpers.

- [x] **Step 6.4: Add `authz-check-config`**

Implement:

```python
@app.command("authz-check-config")
def authz_check_config() -> None:
    errors = authorization_config_errors()
    if not errors:
        typer.echo("Authorization config is valid.")
        return
    typer.secho("Authorization config is invalid.", err=True, fg=typer.colors.RED)
    for error in errors:
        typer.secho(error, err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1)
```

- [x] **Step 6.5: Add assignment inspection and prune commands**

Implement:

```python
@app.command("authz-check-assignments")
def authz_check_assignments() -> None:
    config_errors = authorization_config_errors()
    if config_errors:
        typer.secho("Authorization config is invalid.", err=True, fg=typer.colors.RED)
        for error in config_errors:
            typer.secho(error, err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    _get_explicit_database_settings("authz-check-assignments")
    known_role_codes = frozenset(role_catalog_by_code())

    async def operation(container: Injector) -> tuple[UnknownRoleAssignment, ...]:
        repository = container.get(AuthorizationRepositoryInterface)
        return await repository.list_unknown_role_assignments(known_role_codes)

    assignments = asyncio.run(run_with_container(operation))
    if not assignments:
        typer.echo("Authorization assignments are valid.")
        return
    typer.secho("Unknown role assignments found.", err=True, fg=typer.colors.RED)
    for assignment in assignments:
        typer.secho(
            f"user_id={assignment.user_id} role_code={assignment.role_code}",
            err=True,
            fg=typer.colors.RED,
        )
    raise typer.Exit(code=1)


@app.command("authz-prune-unknown-role-assignments")
def authz_prune_unknown_role_assignments(
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Delete unknown role assignments. Use only for role retirement, not rename.",
    ),
) -> None:
    if not yes:
        typer.secho(
            "Pass --yes to delete unknown role assignments.",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    config_errors = authorization_config_errors()
    if config_errors:
        typer.secho("Authorization config is invalid.", err=True, fg=typer.colors.RED)
        for error in config_errors:
            typer.secho(error, err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    _get_explicit_database_settings("authz-prune-unknown-role-assignments")
    known_role_codes = frozenset(role_catalog_by_code())

    async def operation(container: Injector) -> int:
        auth_repository = container.get(AuthRepositoryInterface)
        authorization_repository = container.get(AuthorizationRepositoryInterface)
        unit_of_work = container.get(UnitOfWorkInterface)
        async with unit_of_work.transaction():
            assignments = await authorization_repository.list_unknown_role_assignments(
                known_role_codes
            )
            deleted_count = await authorization_repository.delete_unknown_role_assignments(
                known_role_codes
            )
            for assignment in assignments:
                await auth_repository.create_audit_log(
                    AuthAuditLog(
                        user_id=None,
                        session_id=None,
                        event_type=AuthEventType.ROLE_REVOKED,
                        ip_address=None,
                        user_agent=None,
                        detail_json={
                            "source": "cli-prune",
                            "actorUserId": None,
                            "targetUserId": str(assignment.user_id),
                            "roleCode": assignment.role_code,
                        },
                    )
                )
        return deleted_count

    deleted_count = asyncio.run(run_with_container(operation))
    typer.echo(f"Deleted {deleted_count} unknown role assignment(s).")
```

- [x] **Step 6.6: Update `authz-grant-role` to validate role code from config**

Validate the role code from `role_catalog_by_code()` before `_get_explicit_database_settings()` and before container/transaction setup. Unknown role should fail without `DATABASE_URL`.

```python
if role not in role_catalog_by_code():
    typer.secho(f"Role not found: {role}", err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1)
```

Then use repository:

```python
existing_roles = frozenset(await authorization_repository.get_user_role_codes(user.id))
result = await authorization_repository.replace_user_roles(
    user.id,
    tuple(sorted(existing_roles | frozenset({role}))),
    assigned_by_user_id=None,
)
result_permissions = permissions_for_role_codes(result.current_role_codes)
```

Do not rely on `UserRoleReplacementResult.current_permission_codes`; that field is removed. CLI output must use `result_permissions`.

- [x] **Step 6.7: Run CLI unit tests**

Run:

```bash
cd backend
uv run pytest tests/unit/test_manage.py -q
```

Expected:

- PASS.

## Task 7: Update tests and fixtures for migration and integration

**Files:**

- Modify: `backend/tests/integration/test_manage_cli.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/tests/integration/test_authorization_controller.py`
- Modify: `backend/tests/integration/services/test_authorization_repository.py`
- Modify: `backend/tests/unit/usecases/test_account_deletion_coverage.py`

- [x] **Step 7.1: Remove DB catalog seeding helpers**

Delete integration test helpers that manually insert into:

- `permissions`
- `roles`
- `role_permissions`

Replace admin assignment setup with `user_roles.role_code = "admin"`.

Example helper:

```python
async def _grant_role(async_session, user_id, role_code: str = "admin") -> None:
    async_session.add(UserRole(user_id=user_id, role_code=role_code, assigned_by_user_id=None))
    await async_session.commit()
```

- [x] **Step 7.2: Update manage CLI integration tests**

Delete `test_authz_sync_creates_default_authorization_definitions`.

Add:

```python
def test_authz_check_config_runs_without_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = CliRunner().invoke(manage.app, ["authz-check-config"])

    assert result.exit_code == 0
    assert "Authorization config is valid." in result.stdout
```

Add DB-backed assignment check/prune coverage:

- Seed `user_roles(role_code="deleted-role")` directly.
- Assert `authz-check-assignments` exits 1 and prints the unknown role.
- Assert `authz-prune-unknown-role-assignments` without `--yes` exits 1 and does not delete.
- Assert `authz-prune-unknown-role-assignments --yes` deletes the unknown row and leaves known `admin` rows intact.
- Assert prune writes one `ROLE_REVOKED` audit row per deleted unknown assignment with `detail_json.source == "cli-prune"`.

Keep `authz-grant-role` integration test, but assertions should query `user_roles.role_code`.

```sql
SELECT role_code FROM user_roles WHERE user_id = :user_id ORDER BY role_code
```

- [x] **Step 7.3: Verify migration upgrade/downgrade round-trip on test DB**

Run this after Task 3 is complete, when `manage.py` can import the updated repository and a disposable PostgreSQL test DB is available. Use the same URL for `DATABASE_URL` and direct SQL seed commands. If `TEST_DATABASE_URL` / a disposable `DATABASE_URL` is not available in the current environment, record that this DB verification was not runnable.

Normal round-trip:

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run python manage.py db-upgrade
```

Seed one assignment in the new schema:

```sql
INSERT INTO users (id, email, password_hash, is_active, created_at, updated_at)
VALUES ('00000000-0000-0000-0000-00000000a001', 'downgrade-admin@example.com', 'hash', true, now(), now())
ON CONFLICT DO NOTHING;

INSERT INTO user_roles (user_id, role_code, assigned_at, assigned_by_user_id)
VALUES ('00000000-0000-0000-0000-00000000a001', 'admin', now(), NULL)
ON CONFLICT DO NOTHING;
```

Then verify downgrade and re-upgrade:

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run python manage.py db-downgrade --revision 20260808_0005
```

Expected after downgrade:

- `roles`, `permissions`, and `role_permissions` exist and contain the migration-local literal snapshot.
- `user_roles.role_id` is non-null and joins to `roles.code = 'admin'`.

Then:

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run python manage.py db-upgrade
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run python manage.py db-check
```

Expected after re-upgrade:

- `user_roles.role_code = 'admin'` is preserved.
- `db-check` reports no schema drift.

Abort guard:

- Upgrade to `20260810_0006`, seed `user_roles.role_code = 'deleted-role'`, then run `db-downgrade --revision 20260808_0005`.
- Expected: command fails with `Cannot downgrade: user_roles contains unknown role_code`.
- Expected: `user_roles` remains in the new schema with `role_code` intact; the failed downgrade must not drop or alter the assignment table.

- [x] **Step 7.4: Update account deletion coverage**

`user_roles` remains in `HANDLED_TABLES`. No catalog tables should be listed as user-owned cleanup responsibilities.

- [x] **Step 7.5: Run integration tests when DB is available**

Run:

```bash
cd backend
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test \
  uv run pytest tests/integration/test_manage_cli.py tests/integration/test_authorization_controller.py tests/integration/test_auth_controller.py -q
```

Expected:

- PASS when PostgreSQL test DB is available.

If `TEST_DATABASE_URL` is not set, record that integration tests were not runnable in the current environment.

## Task 8: Update docs to remove DB catalog / authz-sync language

**Files:**

- Modify: `AGENTS.md`
- Modify: `backend/AGENTS.md`
- Modify: `documents/references/backend-app-structure.md`
- Modify: `documents/references/rbac-authorization-operations.md`
- Modify: `documents/references/oauth-oidc-google-setup-guide.md`
- Modify: `documents/plans/20260808-rbac-authorization.md` only by adding an addendum if needed.

- [x] **Step 8.1: Update root and backend agent docs**

Replace statements like:

```text
roles / permissions / user_roles / role_permissions による RBAC
authz-sync は default authorization definitions を同期する
```

with:

```text
アプリケーション認可は code-managed RBAC を使う。role / permission catalog は
backend/app/config/authorization.py を正とし、DB には user_roles(user_id, role_code)
だけを保存する。endpoint は role ではなく permission code で守る。
```

Document:

- `authz-sync` does not exist.
- `authz-check-config` checks catalog consistency.
- `authz-check-assignments` detects role codes in `user_roles` that are no longer present in code.
- `authz-prune-unknown-role-assignments --yes` deletes those orphan assignments.
- `authz-grant-role` grants known code-defined roles.

- [x] **Step 8.2: Rewrite RBAC operations reference**

Update `documents/references/rbac-authorization-operations.md`.

Required sections:

- Conclusion: catalog is code-only.
- DB tables: only `user_roles`.
- Why DB catalog was removed: avoid operational ambiguity.
- How to add permission: edit code definitions, update endpoint, test, deploy. No sync.
- How to add role: edit code definitions, no migration unless DB constraints are introduced.
- How to grant role: CLI or admin API.
- How admin API returns catalog: from code definitions, not DB.
- How to check config: `authz-check-config`.
- How to check/prune DB assignments: `authz-check-assignments` and `authz-prune-unknown-role-assignments --yes`.
- Unknown stored role codes are not returned in public `roles` arrays and do not grant permissions; they are observable through warning logs and `authz-check-assignments`.
- Rename/delete caveats: role_code strings in existing `user_roles` may need migration/script if role code changes.
- Do not use prune for role rename. Rename needs an explicit remap migration/script from old role code to new role code. Use prune only when a role is intentionally retired and assignments should be removed.

- [x] **Step 8.3: Update backend structure reference**

`documents/references/backend-app-structure.md` should say:

```text
DB table は user_roles のみ。roles / permissions / role_permissions table は持たない。
role / permission catalog は app/config/authorization.py の code definitions を正とする。
```

- [x] **Step 8.4: Run doc grep**

Run:

```bash
rtk grep -n "authz-sync|authz-check|authz-grant-role|role_permissions|permissions table|roles table|roles / permissions" AGENTS.md backend/AGENTS.md documents/references documents/plans
```

Expected:

- Historical plan references may remain in `documents/plans/20260808-rbac-authorization.md`.
- Current operational docs should not tell users to run `authz-sync`.
- `authz-grant-role` is still a current command, so grep hits for it are expected; verify those hits describe code-defined role grants, not old DB catalog sync.

## Task 9: Frontend smoke checks

**Files:**

- Usually no source changes.
- Modify Frontend tests only if Backend response fixture names changed.

- [x] **Step 9.1: Confirm frontend contract remains unchanged**

`AuthUser` should still be:

```ts
export type AuthUser = {
  id: string
  email: string
  roles: Array<string>
  permissions: Array<string>
}
```

`hasPermission()` and route guards should continue checking permission code.

- [x] **Step 9.2: Run relevant frontend tests**

Run:

```bash
cd frontend
npm test -- permissions.test.ts authGuard.test.ts app.test.tsx
```

Expected:

- PASS.

## Task 10: Quality gates

**Files:**

- No source edit unless failures require fixes.

- [x] **Step 10.1: Backend static checks**

Run:

```bash
cd backend
uv run ruff check .
uv run isort . --check-only
uv run yapf -dr app/ tests/ alembic/ manage.py
uv run mypy app manage.py
```

Expected:

- All pass.

- [x] **Step 10.2: Backend unit tests**

Run:

```bash
cd backend
uv run pytest tests/unit
```

Expected:

- PASS.

- [x] **Step 10.3: Backend integration tests**

Run when PostgreSQL test DB is available:

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run python manage.py db-upgrade
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test \
  uv run pytest tests/integration -q -ra
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run python manage.py db-check
```

Expected:

- `db-upgrade` applies through Alembic head.
- Integration tests PASS against the upgraded schema.
- `db-check` reports no schema drift between SQLModel metadata and the migrated DB.

- [x] **Step 10.4: Frontend checks**

Run:

```bash
cd frontend
npm run check:ci
npm test
npm run build
```

Expected:

- PASS.

- [x] **Step 10.5: Docker checks**

Run:

```bash
docker compose config
docker build --target runtime -t python-react-template-runtime .
docker build --target backend-dev -t python-react-template-backend-dev .
```

Expected:

- PASS.

## Review checklist

- [x] `roles`, `permissions`, and `role_permissions` SQLModel table classes are gone.
- [x] Alembic head creates `user_roles.role_code` directly and never creates `roles`, `permissions`, or `role_permissions`.
- [x] Alembic downgrade for the squashed initial schema drops application tables back to base.
- [x] Upgrade/downgrade/re-upgrade round-trip was exercised on a disposable PostgreSQL DB before the migration squash, including the unknown-role abort case. After the squash, the relevant DB gate is fresh initial upgrade plus `db-check`.
- [x] `db-upgrade`, integration tests, and `db-check` all pass against the same PostgreSQL test database.
- [x] DB cleanup fixtures no longer truncate removed tables.
- [x] `authz-sync`, `authz-sync --check`, and `authz-check` are gone.
- [x] `authz-check-config` exists and does not require `DATABASE_URL`.
- [x] `authz-check-config` and startup validation reject empty permission/role catalogs.
- [x] `authz-check-assignments` reports unknown `user_roles.role_code` rows.
- [x] `authz-prune-unknown-role-assignments --yes` removes unknown role assignments and leaves known assignments intact.
- [x] `authz-prune-unknown-role-assignments --yes` writes one `ROLE_REVOKED` audit row per deleted assignment.
- [x] `authz-grant-role` rejects unknown role code from config before repository write.
- [x] `GET /api/admin/roles` still returns role and permission catalog, but from code definitions.
- [x] `PUT /api/admin/users/{user_id}/roles` still returns sorted current `roles`, computed `permissions`, `grantedRoles`, and `revokedRoles`.
- [x] `GET /api/auth/me`, login, register, and OIDC login still return sorted `roles` and `permissions`.
- [x] Unknown stored role codes are filtered out of public `roles`, ignored for permission resolution, and logged, not raised as raw `KeyError`.
- [x] `require_permission()` still enforces permission code from `AuthenticatedSessionContext`.
- [x] `create_app()` fails fast when the code authorization catalog is invalid.
- [x] `backend/tests/unit/models/test_metadata.py` matches the new table set, FK names, and `ix_user_roles_role_code`.
- [x] Account deletion still removes `user_roles`.
- [x] Docs no longer describe DB catalog sync as current operation.
- [x] Historical plan docs are either left as historical or clearly marked with a later addendum.

## Risks and decisions

- `user_roles.role_code` has no FK to a `roles` table. This is intentional. Application code must validate role codes in CLI/API before writes, while read paths filter unknown role codes out of public roles and permission resolution.
- Role code rename requires data migration or one-off remap script because existing `user_roles.role_code` rows store the old string. During the gap before migration, affected users lose the renamed/deleted role and its permissions, but authentication should continue and known roles should still work.
- `authz-check-assignments` must be part of operational checks before/after role code rename/delete. `authz-prune-unknown-role-assignments --yes` is the explicit cleanup path for retired-role orphan assignments, not for rename. Rename should remap old code to new code before prune is considered.
- Permission rename requires code updates in `require_permission()`, Frontend guards, and role definitions.
- DB no longer stores permission display names or role-permission mappings. Admin API must import code catalog to return them.
- `UserRoleReplacementResult` intentionally carries only role changes. Controller and CLI currently compute response permissions from `result.current_role_codes`; if a third caller needs the same response shape, consider adding an application-layer response result type instead of duplicating boundary mapping again.
- Existing uncommitted `authz-check` work, if present, should not be preserved. It solves drift for the old sync design and is obsolete in the new code-managed design.
