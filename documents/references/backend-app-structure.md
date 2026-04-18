# アプリの構造

## バックエンドアプリケーション (FastAPI)

### ディレクトリ構造

アプリケーション本体は `backend/app` 配下にあり、起動は `backend/app/main.py` から行う。
静的ファイルは `backend/static` を公開する。

```
backend/
  app/
    main.py                  # create_app() を呼び出して FastAPI を生成
    bootstrap/
      create_app.py           # アプリ生成と Injector のセットアップ
      container.py            # DI 定義 (Config/Logger/UseCase など)
      route.py                # ルーティング登録と static のマウント
    config/
      __init__.py             # Config 定義と .env 読み込み
    controllers/              # HTTP 層 (FastAPI Router)
    usecases/                 # アプリケーション層 (ユースケース実装)
    services/                 # ドメイン/業務関心 (実装フォルダ名は固定)
    repositories/             # 永続化/外部ストレージ (今後追加予定)
    interfaces/
      usecases/               # UseCase の抽象インタフェース
      services/               # Service の抽象インタフェース
      repositories/           # Repository の抽象インタフェース (今後追加予定)
    models/                   # Response/Domain Model (SQLModel/Pydantic)
    libraries/                # 共通ライブラリ (必要に応じて)
  static/                     # `route.py` で `/` にマウント
```

### 依存関係とレイヤ構造

現状の流れは `Controller -> UseCase`。今後は `Controller -> UseCase -> Service -> Repository` を基本とする。

- Controller: HTTP リクエストを受け、UseCase を呼び出す。ビジネスロジックは持たない。
- UseCase: 1つの Controller(エンドポイント) に対し基本 1つ。Service を組み合わせて処理を編成。
- Service: もう少し粒度の大きい関心事ごとに 1 つ設ける。業務ロジック・外部連携などを担当。
- Repository: DB 操作を担う (将来追加予定)。Service から利用。

### Dependency Injection (DI)

DI には `injector` ライブラリを使用する。`backend/app/bootstrap/container.py` が定義の中心。

- `build_container()` で `Injector` を生成し、`create_app()` で `app.state.injector` に保存。
- Controller では `request.app.state.injector.get(Interface)` で依存解決する。
- UseCase/Service/Repository は必ず DI で解決し、Controller から直接実装クラスを new しない。

現状のパターン:

1. `interfaces/` に抽象インタフェースを定義
2. 実装は `usecases/` (または `services/`, `repositories/`) に置く
3. `container.py` で interface -> 実装インスタンスを `binder.bind()` する

#### DI に関するルール

- **UseCase / Service / Repository はすべて DI 必須**
- **必ず `Config` と `Logger` をコンストラクタで受け取る**
- 追加依存 (Service/Repository) もコンストラクタで受け取る
- DI 登録は `container.py` の `configure()` に集約する

例 (現状のパターン):

```python
# container.py
get_sample_index_usecase = GetSampleIndexUsecase(
    config=config,
    logger=logger,
)
binder.bind(GetSampleIndexUsecaseInterface, to=get_sample_index_usecase)
```

### Config

- `app/config/__init__.py` で `dotenv` を読み込み、`Config` を `BaseSettings` で定義。
- `config = Config()` をグローバルなシングルトンとして DI する。
- 追加設定は `Config` にフィールドを増やし、`.env` または環境変数から読み込む。

注意点:
- `create_app(environment: str = 'local')` の引数は現在未使用。環境切り替えは `ENVIRONMENT` で行う方針。

### Logging

- `container.py` で `getLogger(__name__)` を生成し、`Logger` を DI する。
- UseCase / Service / Repository は **Logger を DI で受け取り、内部で新規生成しない**。
- ログフォーマットやレベル設定は **Config 経由で管理する**。

### Controller -> UseCase -> Service の流れ

現状:

1. `controller` が `request.app.state.injector` から UseCase を取得
2. UseCase の `handle()` を実行し、`Status` などのモデルを返す

今後の標準フロー (推奨):

1. Controller は入力検証と HTTP 変換のみ
2. UseCase が Service を呼び出し、必要に応じて複数の Service を組み合わせる
3. Service が Repository を通して DB へアクセス
4. 返却値は `models/` に定義した Pydantic/SQLModel にマッピング

### ルーティングとエンドポイント

- `bootstrap/route.py` でルーターをまとめて `/api` にマウント。
- ルート `/` は `StaticFiles(directory="static", html=True)` にマウント。
- 追加 Controller を作成したら `route.py` で `include_router()` する。

### モデル

- `models/status.py` の `Status` は `SQLModel(table=False)` として Response 用モデルに使う。
- Controller の `responses` では `Status` の `model_dump()` を利用して統一的なレスポンス形式を維持する。

### 追加する際の指針 (まとめ)

- Controller は interface に依存し、具象クラスを import しない
- UseCase / Service / Repository は interface + implementation の2段構成
- **DI では Config と Logger を必ず注入**
- DI 登録は `container.py` に一元化
- レイヤ間依存は `Controller -> UseCase -> Service -> Repository` の一方向
- DB 実装追加時は `interfaces/repositories` と `repositories/` を新設し同様に DI
 - UseCase の `handle()` は **async に統一する**

### 決定事項

1. Service/Repository の実装フォルダ名は `services/` / `repositories/` で固定
2. Logger の出力フォーマット・レベル設定は Config で管理
3. UseCase の `handle()` は async に統一
