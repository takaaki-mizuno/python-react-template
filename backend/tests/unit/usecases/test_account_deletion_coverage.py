from sqlmodel import SQLModel

import app.models  # noqa: F401

AUTH_INTERNAL_TABLES = {"auth_sessions", "auth_audit_logs"}
HANDLED_TABLES = {"auth_identities", "sample_items"}


def test_every_user_owned_table_is_handled_on_account_deletion() -> None:
    user_owned = {
        table.name
        for table in SQLModel.metadata.tables.values()
        for fk in table.foreign_keys
        if fk.column.table.name == "users" and table.name not in AUTH_INTERNAL_TABLES
    }
    message = ("users を参照する新しい table を追加した場合、"
               "AccountDeletionUsecase の削除方針を決めて HANDLED_TABLES を更新すること")
    assert user_owned == HANDLED_TABLES, message
