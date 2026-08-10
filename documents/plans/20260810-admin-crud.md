# ユーザー一覧をベースに、AdminCRUDの基礎を作る

documents/plans/20260808-rbac-authorization.md で権限管理の機能を追加した。詳細は @documents/references/rbac-authorization-operations.md

ここで、Adminのユーザー一覧の管理画面を作る。

- ユーザー権限を追加する（admin:user_management）を作り、adminロールはそれを見られるように
- ユーザーのCRUDを作り、admin:user_management permissionで利用可能にする
- ユーザーのCRUDは、すべての管理画面のCRUDの