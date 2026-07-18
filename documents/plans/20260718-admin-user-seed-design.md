# 管理用初期ユーザーseed設計

## 目的

ローカル開発環境で認証画面をすぐ確認できるよう、migration適用後に手動実行する初期ユーザーseedを提供する。

## 対象ユーザー

- email: `admin@example.com`
- password: `Password@123!`
- active: `true`

現在の`users`テーブルには管理者権限を表す属性がないため、このユーザーは権限上は通常ユーザーである。`admin`は初期ログイン用の識別名としてのみ扱う。

## 実行方法

`backend/manage.py`へ`seed-admin`コマンドを追加し、repository rootからDocker Compose経由で手動実行する。

```bash
docker compose exec -T backend \
  uv run python manage.py seed-admin
```

seedはmigrationを自動実行しない。利用者は先に`db-upgrade --revision head`を実行する。

## 動作

1. `ENVIRONMENT`が`local`または`development`であることを検証する。
2. `admin@example.com`を大文字・小文字を区別せず検索する。
3. 未登録なら、既存の`hash_password()`でパスワードをハッシュ化してactiveユーザーを作成する。
4. 登録済みなら、パスワードを同じ値で再ハッシュ化し、`is_active=true`へ戻す。
5. 作成または更新したことを標準出力へ表示する。平文パスワードは出力しない。

重複実行はエラーにせず、指定した初期ログイン状態へ収束させる。

## 安全性とエラー処理

- `production`など許可対象外の環境ではDBへ接続せず、理由を表示して非ゼロ終了する。
- パスワード保存は通常登録と同じArgon2ハッシュ処理を再利用する。
- migration未適用、DB接続失敗、更新失敗は成功扱いにせず、CLIを非ゼロ終了させる。
- seed専用のHTTP APIやPostgreSQL初期化SQLは追加しない。

## テスト

- 未登録時に期待するemail、検証可能なパスワード、active状態で作成される。
- 登録済みユーザーのパスワードとactive状態が更新され、ユーザーが重複しない。
- 許可対象外の環境ではseed処理を開始しない。
- CLIからseed処理が呼び出され、結果に応じたメッセージまたはエラーが返る。

## ドキュメント

ルート`README.md`の初回migration手順の後へ、手動seedコマンド、ログイン情報、再実行時の挙動、ローカル専用であることを追記する。
