# OAuth/OIDC 設定手順書（Google ログイン）

作成日: 2026-08-08

この手順書は、このリポジトリを初めて触る人が Google アカウントでログインできる状態まで進めるためのガイドです。Google Cloud Console 側の設定、Backend の環境変数、ローカル起動、動作確認、よくあるエラーを順番に扱います。

## このリポジトリの OAuth/OIDC の前提

このアプリでは OAuth/OIDC の処理を Backend が担当します。

- Frontend は `/api/auth/oidc/providers` で表示可能な provider 一覧を取得します。
- ユーザーが「Googleで続行」を押すと、Frontend は `/api/auth/oidc/google/start?...` へ full-page redirect します。
- Backend は Google の認可画面へ redirect し、callback で authorization code を処理します。
- callback 成功後、Backend が session cookie と CSRF cookie を発行し、アプリ内の redirect 先へ戻します。
- Frontend callback route は作りません。
- Google の `access_token` / `refresh_token` は DB、audit log、URL、Frontend state に保存しません。

重要な URL は次の 1 つです。

```text
http://localhost:8000/api/auth/oidc/google/callback
```

これはローカル開発用の Google callback URL です。本番では `http://localhost:8000` を本番 Backend の公開 origin に置き換えます。

## 事前準備

必要なもの:

- Google Cloud Console にアクセスできる Google アカウント
- このリポジトリを clone 済みの開発環境
- Docker Compose を使う場合: Docker / Docker Compose
- 直接ローカル起動する場合: Python / uv / Node.js / npm / PostgreSQL

この手順では Docker Compose を推奨します。理由は、`docker-compose.yaml` が `backend/.env` を Backend container の process environment として読み込むため、OIDC 設定がそのまま反映されるからです。

直接 `cd backend && uv run python manage.py serve` で起動する場合、現行実装の OIDC 設定は `os.environ` を直接読むため、`backend/.env` に書いただけでは OIDC 設定が反映されません。その場合は後述の「直接ローカル起動する場合」のように OIDC 系の環境変数を shell に export してから起動してください。

## Step 1: Redirect URI を決める

まず、Google Cloud Console に登録する redirect URI を決めます。

### ローカル Docker Compose

```text
http://localhost:8000/api/auth/oidc/google/callback
```

Frontend は通常 `http://localhost:3000` で開きますが、Google callback は Backend に戻す必要があります。このリポジトリでは callback endpoint が Backend の `/api/auth/oidc/google/callback` だからです。

### ローカルで port を変える場合

Backend port を `8001` にするなら、redirect URI も同じ port にします。

```text
http://localhost:8001/api/auth/oidc/google/callback
```

この場合、後で設定する `AUTH_OIDC_REDIRECT_BASE_URL` も `http://localhost:8001` にします。

### 本番

本番では HTTPS の公開 Backend origin を使います。

```text
https://example.com/api/auth/oidc/google/callback
```

`AUTH_OIDC_REDIRECT_BASE_URL` は request の `Host` から自動推定されません。必ず、本番で Google から到達できる公開 origin を明示してください。

```env
AUTH_OIDC_REDIRECT_BASE_URL=https://example.com
AUTH_OIDC_PROVIDER_GOOGLE_CALLBACK_PATH=/api/auth/oidc/google/callback
```

## Step 2: Google Cloud Console で OAuth client を作る

Google の画面は変更されることがあります。以下は 2026-08-08 時点の公式ドキュメントに基づく流れです。

### 2.1 Google Cloud project を選ぶ、または作る

1. [Google Cloud Console](https://console.cloud.google.com/) を開きます。
2. 画面上部の project selector から既存 project を選ぶか、新しい project を作成します。
3. 本番用と検証用を分けたい場合は、Google Cloud project も分けると事故が少なくなります。

### 2.2 OAuth consent screen / Branding を設定する

1. Google Cloud Console で `APIs & Services` を開きます。
2. `OAuth consent screen` または `Branding` を開きます。
3. アプリ名、ユーザーサポートメール、開発者連絡先を入力します。
4. 本番公開する場合は、必要に応じて authorized domains、privacy policy、terms なども設定します。
5. ローカル検証だけなら、公開ステータスを testing にし、テストユーザーに自分の Google アカウントを追加します。

このテンプレートの標準 login では Google の基本 profile と email だけを使います。追加の Google API（Drive、Gmail、Calendar など）を呼び出す設計ではありません。

### 2.3 OAuth client ID を作る

1. Google Cloud Console で `APIs & Services` → `Credentials` を開きます。
2. `Create credentials` → `OAuth client ID` を選びます。
3. Application type は `Web application` を選びます。
4. Name は分かりやすく `python-react-template local` などにします。
5. `Authorized redirect URIs` に Step 1 で決めた URI を追加します。

ローカル Docker Compose なら次を追加します。

```text
http://localhost:8000/api/auth/oidc/google/callback
```

本番も同じ OAuth client で使うなら、本番 URI も追加します。

```text
https://example.com/api/auth/oidc/google/callback
```

6. 作成後に表示される `Client ID` と `Client secret` を控えます。

注意:

- Redirect URI は完全一致が必要です。scheme、host、port、path のどれか 1 文字でも違うと `redirect_uri_mismatch` になります。
- `http://localhost` はローカル検証用です。本番は HTTPS を使ってください。
- Client secret はリポジトリへコミットしないでください。

## Step 3: Backend の環境変数を設定する

### 3.1 Docker Compose の場合（推奨）

`backend/.env` を作ります。

```bash
cd /path/to/python-react-template
cp backend/.env.example backend/.env
```

`backend/.env` の OAuth/OIDC section を次のように編集します。

```env
# OAuth/OIDC providers. Keep empty to disable OIDC login.
AUTH_OIDC_ENABLED_PROVIDERS=google
AUTH_OIDC_REDIRECT_BASE_URL=http://localhost:8000
AUTH_OIDC_REAUTH_FRESHNESS_SECONDS=300
AUTH_OIDC_AUTHORIZATION_STARTS_PER_IP=20
AUTH_OIDC_STATE_TTL_SECONDS=300

AUTH_OIDC_PROVIDER_GOOGLE_DISPLAY_NAME=Google
AUTH_OIDC_PROVIDER_GOOGLE_ISSUER=https://accounts.google.com
AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_ID=<Google Cloud Console の Client ID>
AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_SECRET=<Google Cloud Console の Client secret>
AUTH_OIDC_PROVIDER_GOOGLE_SCOPE=openid email profile
AUTH_OIDC_PROVIDER_GOOGLE_TRUST_VERIFIED_EMAIL=true
AUTH_OIDC_PROVIDER_GOOGLE_AUTO_PROVISION=enabled
AUTH_OIDC_PROVIDER_GOOGLE_LINK_MODE=auto
AUTH_OIDC_PROVIDER_GOOGLE_CALLBACK_PATH=/api/auth/oidc/google/callback
AUTH_OIDC_PROVIDER_GOOGLE_CLAIMS_ALLOWLIST=
```

ローカル HTTP で動かす場合は、同じ `backend/.env` で次も設定します。

```env
ENVIRONMENT=local
AUTH_COOKIE_SECURE=false
AUTH_SESSION_COOKIE_PREFIX=
```

本番では `AUTH_COOKIE_SECURE=false` を使わないでください。未設定または `true` にします。

### 3.2 直接ローカル起動する場合

直接 `uv run python manage.py serve` で Backend を起動する場合は、OIDC 系の設定を shell に export します。

```bash
cd /path/to/python-react-template/backend

export AUTH_OIDC_ENABLED_PROVIDERS=google
export AUTH_OIDC_REDIRECT_BASE_URL=http://localhost:8000
export AUTH_OIDC_REAUTH_FRESHNESS_SECONDS=300
export AUTH_OIDC_AUTHORIZATION_STARTS_PER_IP=20
export AUTH_OIDC_STATE_TTL_SECONDS=300

export AUTH_OIDC_PROVIDER_GOOGLE_DISPLAY_NAME=Google
export AUTH_OIDC_PROVIDER_GOOGLE_ISSUER=https://accounts.google.com
export AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_ID='<Google Cloud Console の Client ID>'
export AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_SECRET='<Google Cloud Console の Client secret>'
export AUTH_OIDC_PROVIDER_GOOGLE_SCOPE='openid email profile'
export AUTH_OIDC_PROVIDER_GOOGLE_TRUST_VERIFIED_EMAIL=true
export AUTH_OIDC_PROVIDER_GOOGLE_AUTO_PROVISION=enabled
export AUTH_OIDC_PROVIDER_GOOGLE_LINK_MODE=auto
export AUTH_OIDC_PROVIDER_GOOGLE_CALLBACK_PATH=/api/auth/oidc/google/callback
export AUTH_OIDC_PROVIDER_GOOGLE_CLAIMS_ALLOWLIST=

export AUTH_COOKIE_SECURE=false
export AUTH_SESSION_COOKIE_PREFIX=
```

`AUTH_OIDC_PROVIDER_GOOGLE_SCOPE` は空白を含むため、shell では必ず quote してください。

### 3.3 auto provision / auto link の意味

初めて Google ログインを試すだけなら、次の設定が最も動作確認しやすいです。

```env
AUTH_OIDC_PROVIDER_GOOGLE_TRUST_VERIFIED_EMAIL=true
AUTH_OIDC_PROVIDER_GOOGLE_AUTO_PROVISION=enabled
AUTH_OIDC_PROVIDER_GOOGLE_LINK_MODE=auto
```

意味:

- `TRUST_VERIFIED_EMAIL=true`: Google が verified と返した email を、このアプリの本人確認済み email として信頼します。
- `AUTO_PROVISION=enabled`: 対応する user がまだ存在しない場合、OAuth-only user を自動作成します。
- `LINK_MODE=auto`: 既存 password user と Google の verified email が一致した場合、Google identity を自動連携します。

より保守的にしたい場合:

```env
AUTH_OIDC_PROVIDER_GOOGLE_AUTO_PROVISION=link-only
AUTH_OIDC_PROVIDER_GOOGLE_LINK_MODE=manual
```

ただし、現時点の Frontend には手動 link UI がありません。そのため `manual` のままだと、既存 user との email 一致時に `OIDC_IDENTITY_LINK_REQUIRED` になり、ログイン画面に「既存アカウントでログインしてから連携してください。」というエラーが表示されます。手動 link UI を作るまでは、開発環境では `auto` を使う方が動作確認しやすいです。

## Step 4: DB migration を適用する

OAuth/OIDC は DB に state、identity、session、audit log を保存します。起動前に migration を適用してください。

### Docker Compose の場合

`docker-compose.yaml` の Backend command は起動時に `uv run python manage.py db-upgrade` を実行します。通常は次の起動で migration も適用されます。

```bash
cd /path/to/python-react-template
docker compose up -d --build
```

ログを確認します。

```bash
docker compose logs -f backend
```

### 直接ローカル起動の場合

PostgreSQL を起動し、`DATABASE_URL` が正しいことを確認してから migration を適用します。

```bash
cd /path/to/python-react-template/backend
uv sync
uv run python manage.py db-upgrade
```

`DATABASE_URL` を shell で明示する場合:

```bash
DATABASE_URL='postgresql+asyncpg://app:app@localhost:5432/app' \
  uv run python manage.py db-upgrade
```

## Step 5: アプリを起動する

### Docker Compose の場合

```bash
cd /path/to/python-react-template
docker compose up -d --build
```

アクセス先:

```text
Frontend: http://localhost:3000
Backend:  http://localhost:8000
```

### 直接ローカル起動の場合

Terminal 1:

```bash
cd /path/to/python-react-template/backend
uv run python manage.py serve --host 0.0.0.0 --port 8000
```

Terminal 2:

```bash
cd /path/to/python-react-template/frontend
npm install
npm run dev
```

アクセス先:

```text
Frontend: http://localhost:3000
Backend:  http://localhost:8000
```

Frontend dev server は `/api` を Backend へ proxy します。Google callback は Backend の `http://localhost:8000/api/auth/oidc/google/callback` に戻ります。

## Step 6: Provider 一覧 API を確認する

ブラウザまたは curl で provider list を確認します。

```bash
curl -i http://localhost:8000/api/auth/oidc/providers
```

正常例:

```json
{
  "providers": [
    {
      "providerId": "google",
      "displayName": "Google"
    }
  ]
}
```

`providers` が空配列の場合:

- `AUTH_OIDC_ENABLED_PROVIDERS=google` が Backend process に入っていません。
- Docker Compose なら `backend/.env` を保存後、Backend container を再作成してください。
- 直接ローカル起動なら、OIDC 系の環境変数を export した shell で Backend を起動し直してください。

Backend 設定を変えた後は、必ず Backend を再起動します。

```bash
docker compose up -d --force-recreate backend
```

## Step 7: ログイン画面で確認する

1. `http://localhost:3000/login` を開きます。
2. 「Googleで続行」ボタンが表示されることを確認します。
3. ボタンを押します。
4. Google の認可画面へ遷移することを確認します。
5. Google 側で許可します。
6. アプリへ戻り、ログイン済み状態になることを確認します。

動作確認後、`GET /api/auth/me` は次のようなレスポンスを返します。

```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "email": "user@example.com",
  "roles": [],
  "permissions": []
}
```

RBAC を有効にして admin 権限を付けたい場合は、別途 `authz-sync` と `authz-grant-role` を使います。OAuth/OIDC の Google 設定だけでは admin 権限は付与されません。

```bash
cd backend
DATABASE_URL='postgresql+asyncpg://app:app@localhost:5432/app' \
  uv run python manage.py authz-sync

DATABASE_URL='postgresql+asyncpg://app:app@localhost:5432/app' \
  uv run python manage.py authz-grant-role --email user@example.com --role admin
```

Docker Compose の DB を使う場合は、host 側からは通常 `localhost:5432`、container 内からは `postgres:5432` です。

## Step 8: Account deletion の OAuth/OIDC reauth を確認する場合

OAuth-only user は password を持たないため、アカウント削除時に OAuth/OIDC reauth が必要です。

確認手順:

1. Google ログインで OAuth-only user を作成します。
2. `/app/settings` を開きます。
3. アカウント削除を実行します。
4. `ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` により、Google reauth button が表示されます。
5. Google で再認証します。
6. `/app/settings?oidcReauth=success` に戻ることを確認します。
7. 再度アカウント削除を実行します。

`AUTH_OIDC_REAUTH_FRESHNESS_SECONDS=300` の場合、reauth から 5 分以内だけ fresh とみなします。

## 本番設定チェックリスト

本番で有効化する前に確認してください。

- [ ] Google Cloud Console の redirect URI が本番 URL と完全一致している。
- [ ] `AUTH_OIDC_REDIRECT_BASE_URL` が HTTPS の本番公開 origin になっている。
- [ ] `AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_SECRET` を secret manager / deployment secret で管理している。
- [ ] `AUTH_COOKIE_SECURE` は未設定または `true` にしている。
- [ ] `AUTH_COOKIE_SECURE=false` を本番に入れていない。
- [ ] `AUTH_SESSION_COOKIE_PREFIX=__Host-` を使う場合、Secure、Path=/、Domain 未指定の条件を満たしている。
- [ ] reverse proxy 配下では `AUTH_TRUSTED_PROXY_IPS` に信頼できる直近 proxy だけを指定している。
- [ ] Google consent screen の公開ステータス、authorized domain、privacy policy、support email が本番向けになっている。
- [ ] `AUTO_PROVISION=enabled` と `LINK_MODE=auto` を本番で許可してよいか確認済み。
- [ ] Google API の追加 scope を要求していない。追加する場合は token 保存・暗号化・revoke UX を別設計にしている。
- [ ] Backend process/container を設定変更後に再起動している。

## 複数 provider を追加する場合

`AUTH_OIDC_ENABLED_PROVIDERS` に comma 区切りで provider id を追加します。

```env
AUTH_OIDC_ENABLED_PROVIDERS=google,example
```

provider id は小文字英数字、`-`、`_` を使えます。環境変数名では provider id を大文字化し、`-` は `_` として扱います。

例: provider id が `my-provider` の場合

```env
AUTH_OIDC_PROVIDER_MY_PROVIDER_DISPLAY_NAME=My Provider
AUTH_OIDC_PROVIDER_MY_PROVIDER_ISSUER=https://issuer.example.com
AUTH_OIDC_PROVIDER_MY_PROVIDER_CLIENT_ID=...
AUTH_OIDC_PROVIDER_MY_PROVIDER_CLIENT_SECRET=...
AUTH_OIDC_PROVIDER_MY_PROVIDER_SCOPE=openid email profile
AUTH_OIDC_PROVIDER_MY_PROVIDER_TRUST_VERIFIED_EMAIL=true
AUTH_OIDC_PROVIDER_MY_PROVIDER_AUTO_PROVISION=enabled
AUTH_OIDC_PROVIDER_MY_PROVIDER_LINK_MODE=auto
AUTH_OIDC_PROVIDER_MY_PROVIDER_CALLBACK_PATH=/api/auth/oidc/my-provider/callback
```

provider 側には次の redirect URI を登録します。

```text
https://example.com/api/auth/oidc/my-provider/callback
```

## よくあるエラーと確認ポイント

### ログイン画面に「Googleで続行」が出ない

確認すること:

- `/api/auth/oidc/providers` が `google` を返しているか。
- `AUTH_OIDC_ENABLED_PROVIDERS=google` が Backend process に入っているか。
- Backend を再起動したか。
- Frontend が正しい Backend に proxy しているか。

Docker Compose の場合:

```bash
docker compose logs backend
curl http://localhost:8000/api/auth/oidc/providers
```

### Google で `redirect_uri_mismatch` が出る

Google Cloud Console の `Authorized redirect URIs` と、アプリが送っている redirect URI が一致していません。

確認すること:

- `AUTH_OIDC_REDIRECT_BASE_URL`
- `AUTH_OIDC_PROVIDER_GOOGLE_CALLBACK_PATH`
- Google Cloud Console に登録した redirect URI
- `localhost` と `127.0.0.1` の違い
- port の違い
- `http` と `https` の違い
- trailing slash の有無

ローカル標準構成では次で統一します。

```env
AUTH_OIDC_REDIRECT_BASE_URL=http://localhost:8000
AUTH_OIDC_PROVIDER_GOOGLE_CALLBACK_PATH=/api/auth/oidc/google/callback
```

Google 側:

```text
http://localhost:8000/api/auth/oidc/google/callback
```

### `OIDC_PROVIDER_NOT_CONFIGURED`

指定した provider id が Backend 設定にありません。

確認すること:

- `AUTH_OIDC_ENABLED_PROVIDERS=google`
- Frontend が `/api/auth/oidc/google/start` を呼んでいるか。
- provider id の typo がないか。

### `OIDC_PROVIDER_METADATA_INVALID` または `OIDC_PROVIDER_UNAVAILABLE`

Google の discovery metadata を取得できない、または内容を検証できない状態です。

確認すること:

- `AUTH_OIDC_PROVIDER_GOOGLE_ISSUER=https://accounts.google.com`
- Backend から外部ネットワークへ接続できるか。
- corporate proxy / firewall が `https://accounts.google.com` や Google の JWKS endpoint を遮断していないか。

### `OIDC_EMAIL_NOT_VERIFIED`

Google が verified email を返していない、またはアプリが verified email を信頼しない設定です。

初回ログインを通したい場合:

```env
AUTH_OIDC_PROVIDER_GOOGLE_TRUST_VERIFIED_EMAIL=true
```

### `OIDC_PROVISIONING_DISABLED`

対応する user が存在せず、自動作成も無効です。

初回ログインで user を自動作成したい場合:

```env
AUTH_OIDC_PROVIDER_GOOGLE_AUTO_PROVISION=enabled
```

自動作成したくない場合は、先に password register で同じ email の user を作り、`LINK_MODE=auto` で自動 link させるか、手動 link UI を別途実装してください。

### `OIDC_IDENTITY_LINK_REQUIRED`

同じ verified email の既存 user は見つかりましたが、`LINK_MODE=manual` のため自動連携していません。

手動 link UI がない状態でログインを通したい場合:

```env
AUTH_OIDC_PROVIDER_GOOGLE_LINK_MODE=auto
```

### `OIDC_IDENTITY_UNAVAILABLE`

Google identity または email が、inactive / deleted user や衝突状態の user を指しています。

確認すること:

- 対象 user が `users.is_active=true` か。
- 対象 user が deleted ではないか。
- 同じ email の user が複数状態で衝突していないか。

### ログイン後に unsafe request が 403 になる

CSRF cookie / header の問題が疑われます。

確認すること:

- callback 後に `csrf_token` cookie が発行されているか。
- Frontend は `apiClient` 経由で unsafe request を送っているか。
- 本番 HTTPS で cookie secure 設定が正しいか。
- local HTTP では `AUTH_COOKIE_SECURE=false` になっているか。

## セキュリティ上の注意

- Client secret は `.env`、secret manager、deployment secret などに置き、Git に入れないでください。
- この実装は provider token を保存しません。Google API を代理呼び出しする機能はありません。
- 追加 scope を要求すると consent screen / verification / token 保存方針の設計が必要になります。
- `AUTO_PROVISION=enabled` は、Google の verified email を信頼して user を自動作成します。組織内ユーザーだけに限定したい場合は、Google 側の公開範囲やアプリ側の allowlist を別途設計してください。
- `LINK_MODE=auto` は、同じ verified email の既存 user に Google identity を自動連携します。email 所有確認を Google に委ねる判断なので、信頼する provider でだけ有効にしてください。

## 参考リンク

- [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect)
- [Using OAuth 2.0 for Web Server Applications](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Google API Console Help: Setting up OAuth 2.0](https://support.google.com/googleapi/answer/6158849)
- [README.md の OAuth/OIDC login セクション](../README.md#oauthoidc-login)
- [Backend OAuth/OIDC Client reference](references/backend-app-structure.md#oauthoidc-client)
