# PostgREST互換 Tables/Views API 仕様（/api/db プレフィックス版・SQLite3/SQLModel想定）

本仕様は、PostgREST の Tables/Views API を **`/api/db/{db_name}/{resource}`** 配下で提供する互換 API として定義します。テーブル/ビューは 1 階層のリソースとして公開し、HTTP メソッドとクエリ文字列で操作します（深いネストルートは持ちません）。([PostgREST 14][1])

加えて、以下を **確定仕様**とします。

* Postgres 固有（配列/範囲/全文検索など）で SQLite に同等機能がない演算子は **`PGRST127` で明示的に拒否**する（HTTP 400）。([PostgREST 14][2])
* `Prefer: count=planned` / `Prefer: count=estimated` は統計推定を実装しないため **`PGRST127` で拒否**する（HTTP 400）。`count` 自体の値に `exact/planned/estimated` がある点は PostgREST の仕様に準拠します。([PostgREST 14][3])

---

## 1. ベース URL / ルーティング

* ベースパス：`/api/db`
* リソース：`/api/db/{db_name}/{resource}`

  * `{db_name}` は **データベース名**
  * `{resource}` は **テーブル名またはビュー名**
  * ルートは 1 階層のみ（`/api/db/my_db/people` のようにアクセス）。([PostgREST 14][1])

---

## 2. メソッドと概要

`/api/db/{db_name}/{resource}` は権限/設定に応じて `OPTIONS, GET, HEAD, POST, PATCH, PUT, DELETE` を提供します（互換 API としては実装対象）。([PostgREST 14][1])

* `GET`：行取得（JSON/CSV 等）
* `HEAD`：GET 同等だがボディなし（集計を避ける最適化）([PostgREST 14][1])
* `POST`：INSERT / UPSERT（Prefer による）
* `PATCH`：UPDATE（フィルタで対象指定）
* `PUT`：単一行 UPSERT（PK を `eq` で指定、全列必須）([PostgREST 14][4])
* `DELETE`：DELETE（フィルタで対象指定）

---

## 3. コンテンツネゴシエーション / ボディ形式

### 3.1 レスポンス（Accept）

* 標準：`application/json`（配列）
* CSV：`text/csv`
* ベンダ型：

  * `application/vnd.pgrst.object+json`（単一オブジェクト）
  * `application/vnd.pgrst.array+json`（配列。`nulls=stripped` パラメータ可）([PostgREST 14][5])
* 不明な media type は 415（`PGRST107`）。([PostgREST 14][5])

### 3.2 単一オブジェクト応答（vnd.pgrst.object）

* `Accept: application/vnd.pgrst.object+json` の場合、結果が 1 行のときのみオブジェクトで返します。
* 0 行または複数行の場合は 406（`PGRST116`）。([PostgREST 14][5])

### 3.3 リクエストボディ（POST/PATCH/PUT）

以下を受け付けます。([PostgREST 14][5])

* `application/json`
* `application/x-www-form-urlencoded`
* `text/csv`

---

## 4. クエリ仕様（パラメータ定義と許容演算子）

OpenAPI では列ごとの任意フィルタ（`?age=lt.13` のように **キーが列名**）を完全には型付けできないため、本仕様では

* 主要パラメータ（`select/order/limit/offset/...`）は OpenAPI に明示
* 列フィルタは **「追加クエリパラメータ」**として仕様化（実装は許容）
  という形で定義します。

### 4.1 垂直フィルタ（射影）：`select`

* 型：`string`（CSV 形式）
* 既定：`*`（全列）
* 例：`GET /api/db/my_db/people?select=first_name,age` ([PostgREST 14][4])
* 別名：`alias:column` で指定可（例：`select=fullName:full_name`）([PostgREST 14][4])
* キャスト：`column::type`（例：`select=salary::text`）([PostgREST 14][4])

### 4.2 並び替え：`order`

* 型：`string`
* 形式：`order=col.desc,col2.asc`
* 方向省略時は昇順
* `nullsfirst` / `nullslast` をサポート（例：`order=age.desc.nullslast`）([PostgREST 14][4])

### 4.3 ページング：`limit` / `offset` と Range

* `limit`：`integer(int32)`, `minimum: 0`
* `offset`：`integer(int32)`, `minimum: 0`
* Range 方式（推奨互換）：

  * リクエスト：`Range-Unit: items`, `Range: <start>-<end|空>`（例：`0-19`, `10-`）([PostgREST 14][3])
  * レスポンス：`Range-Unit: items`, `Content-Range: start-end/*`（または `start-end/total`）([PostgREST 14][3])
* `limit/offset` を使ってもサーバは Range 系ヘッダを返す（互換）。([PostgREST 14][3])
* 不正 Range は 416（`PGRST103`）。([PostgREST 14][2])

### 4.4 水平フィルタ（行フィルタ）：`{column}={op}.{value}`

* 形式例：`GET /api/db/my_db/people?age=lt.13` ([PostgREST 14][4])
* 条件追加はデフォルト AND（例：`age=gte.18&student=is.true`）([PostgREST 14][4])

#### 4.4.1 許容演算子（SQLite互換で実装するもの）

以下を **実装 MUST**（互換性の中心）とします。演算子一覧自体は PostgREST に準拠します。([PostgREST 14][4])

| 演算子             | 意味                                 | 例                                       |
| --------------- | ---------------------------------- | --------------------------------------- |
| `eq`            | 等しい                                | `id=eq.1`                               |
| `neq`           | 等しくない                              | `id=neq.1`                              |
| `gt/gte/lt/lte` | 大小比較                               | `age=gte.18`                            |
| `like`          | パターン一致（`*` は `%` の別名として許容）         | `name=like.J*` ([PostgREST 14][4])      |
| `ilike`         | 大文字小文字無視（同上）                       | `name=ilike.*doe*` ([PostgREST 14][4])  |
| `in`            | リストに含まれる                           | `a=in.(1,2,3)` ([PostgREST 14][4])      |
| `is`            | `null/not_null/true/false/unknown` | `x=is.null` ([PostgREST 14][4])         |
| `isdistinct`    | NULL を比較可能として扱う“不一致”               | `x=isdistinct.null` ([PostgREST 14][4]) |

#### 4.4.2 論理（OR / NOT / AND）

* OR：`or=(cond1,cond2,...)`（例：`or=(age.lt.18,age.gt.21)`）([PostgREST 14][4])
* NOT：`not.` プレフィックス（例：`a=not.eq.2`、`not.and=(...)`）([PostgREST 14][4])

#### 4.4.3 追加仕様（予約文字）

* フィルタ値に予約文字が含まれる場合はダブルクォートで包む（例：`or=(age_range.adj."[18,21)",...)`）([PostgREST 14][4])

---

## 5. Prefer ヘッダ（互換サブセット）

`Prefer` は RFC7240 に基づく挙動を持ち、以下の項目を受理します。([PostgREST 14][6])

### 5.1 handling（strict/lenient）

* 既定：`lenient`
* `handling=strict` で不正 Prefer を指定した場合は 400（`PGRST122`）。([PostgREST 14][6])

### 5.2 return（書き込みレスポンス）

* `return=minimal`（既定：ボディなし）([PostgREST 14][6])
* `return=representation`（更新結果を返す）([PostgREST 14][6])
* `return=headers-only`（主キーがある場合 `Location` を返せる）([PostgREST 14][6])

### 5.3 missing=default（DEFAULT の適用）

* `POST/PATCH` で payload に無い列は既定 `null`
* `Prefer: missing=default` で DEFAULT を使用([PostgREST 14][6])

### 5.4 resolution（Upsert）

* `Prefer: resolution=merge-duplicates` で `POST` を upsert 化([PostgREST 14][4])
* `Prefer: resolution=ignore-duplicates` を許容([PostgREST 14][4])
* `on_conflict`（クエリ）で衝突判定列（UNIQUE）を指定可能([PostgREST 14][4])

### 5.5 count（件数）

* PostgREST では `count=exact/planned/estimated` が定義されています。([PostgREST 14][3])
* 本仕様では **`count=exact` のみ実装**し、`planned/estimated` は **`PGRST127` で拒否**します（HTTP 400）。([PostgREST 14][3])

### 5.6 max-affected（影響行数上限）

* `Prefer: handling=strict, max-affected=N` を許容し、違反時は 400（`PGRST124`）。([PostgREST 14][6])

---

## 6. SQLite で拒否する演算子（PGRST127）

以下は PostgREST の演算子として存在しますが、SQLite 標準で同等機能がない（または互換実装をしない）ため **`PGRST127`**（HTTP 400）で拒否します。([PostgREST 14][4])

* 正規表現系：`match`, `imatch` ([PostgREST 14][4])
* 全文検索系：`fts`, `plfts`, `phfts`, `wfts` ([PostgREST 14][4])
* 配列/範囲系：`cs`, `cd`, `ov`, `sl`, `sr`, `nxr`, `nxl`, `adj` ([PostgREST 14][4])

---

## 7. `columns` パラメータ（挿入・更新キー制御）

* `columns`：`string`（カンマ区切り）
* 意味：payload のうち **挿入/更新対象にするキーのみ指定**し、それ以外のキーは無視する。([PostgREST 14][4])
* 主に `POST`（bulk insert 含む）および `PATCH` / upsert で使用。

---

## 8. エラー形式と対応表

### 8.1 エラー JSON 形式

```json
{
  "code": "PGRSTxxx",
  "message": "説明",
  "details": "詳細(任意)",
  "hint": "ヒント(任意)"
}
```

（PostgREST のエラー構造に準拠）([PostgREST 14][2])

### 8.2 主要エラーコード対応表（本 API の必須）

| HTTP | code     | 代表原因                                                                    |
| ---: | -------- | ----------------------------------------------------------------------- |
|  400 | PGRST100 | クエリ文字列パースエラー（フィルタ/ソート等）([PostgREST 14][2])                              |
|  400 | PGRST102 | 不正ボディ（空、壊れた JSON 等）([PostgREST 14][2])                                  |
|  416 | PGRST103 | Range 不正([PostgREST 14][2])                                             |
|  405 | PGRST105 | 不正 PUT リクエスト([PostgREST 14][2])                                         |
|  400 | PGRST114 | PUT upsert に limit/offset を付けた([PostgREST 14][2])                       |
|  400 | PGRST115 | PUT の PK（クエリ）とボディが不一致([PostgREST 14][2])                                |
|  406 | PGRST116 | vnd.pgrst.object 要求だが 1 行にできない([PostgREST 14][5])                       |
|  415 | PGRST107 | Content-Type/Accept 不正([PostgREST 14][5])                               |
|  400 | PGRST122 | handling=strict で不正 Prefer([PostgREST 14][6])                           |
|  400 | PGRST124 | max-affected 違反([PostgREST 14][6])                                      |
|  404 | PGRST205 | テーブル/ビューが存在しない([PostgREST 14][2])                                       |
|  400 | PGRST127 | 未実装機能（本仕様では「SQLite非対応演算子」「count=planned/estimated」等）([PostgREST 14][2]) |

---

# OpenAPI 3.1（テンプレートパス版）

> 注：`{resource}` は動的であり、列スキーマも動的です。そのため本 OpenAPI は「汎用行オブジェクト（追加プロパティ許容）」で表現し、**列フィルタ（クエリキー＝列名）**は `x-` 拡張と説明で定義します。

```yaml
openapi: 3.1.0
info:
  title: PostgREST互換 Tables/Views API（SQLite/SQLModel）
  version: 1.0.0
  description: |
    PostgRESTのTables/Views互換APIを /api/db/{db_name}/{resource} 配下に提供する。
    テーブル/ビューは1階層で公開し、GET/HEAD/POST/PATCH/PUT/DELETEをサポートする。  # 互換意図
    - Postgres固有でSQLiteに同等機能がない演算子はPGRST127で拒否
    - Prefer: count は exact のみ実装し planned/estimated はPGRST127

servers:
  - url: /
    description: Same-origin

tags:
  - name: TablesViews
    description: テーブル/ビュー互換エンドポイント

paths:
  /api/db/{db_name}/{resource}:
    parameters:
      - $ref: "#/components/parameters/Resource"

    options:
      tags: [TablesViews]
      summary: CORS/許可メソッド等の確認
      responses:
        "200":
          description: OK

    get:
      tags: [TablesViews]
      summary: 行の取得
      description: |
        クエリパラメータ（select/order/limit/offset/論理/列フィルタ）で結果を制御する。
        既定のレスポンスはJSON配列。AcceptでCSVや単一オブジェクト形式を指定可能。
      parameters:
        - $ref: "#/components/parameters/Select"
        - $ref: "#/components/parameters/Order"
        - $ref: "#/components/parameters/Limit"
        - $ref: "#/components/parameters/Offset"
        - $ref: "#/components/parameters/Or"
        - $ref: "#/components/parameters/And"
        - $ref: "#/components/parameters/Prefer"
        - $ref: "#/components/parameters/RangeUnit"
        - $ref: "#/components/parameters/Range"
      x-dynamicQueryParameters:
        description: |
          追加のクエリパラメータは列フィルタとして解釈する。
          形式: {column}={op}.{value}
          例: age=lt.13, student=is.true
      responses:
        "200":
          description: OK
          headers:
            Range-Unit:
              $ref: "#/components/headers/RangeUnit"
            Content-Range:
              $ref: "#/components/headers/ContentRange"
            Preference-Applied:
              $ref: "#/components/headers/PreferenceApplied"
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/GenericRows"
            text/csv:
              schema:
                type: string
                description: CSV形式
            application/vnd.pgrst.object+json:
              schema:
                $ref: "#/components/schemas/GenericRow"
            application/vnd.pgrst.array+json:
              schema:
                $ref: "#/components/schemas/GenericRows"
        "206":
          description: Partial Content（Rangeやcount等により部分応答になる場合）
          headers:
            Range-Unit:
              $ref: "#/components/headers/RangeUnit"
            Content-Range:
              $ref: "#/components/headers/ContentRange"
            Preference-Applied:
              $ref: "#/components/headers/PreferenceApplied"
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/GenericRows"
            text/csv:
              schema:
                type: string
            application/vnd.pgrst.object+json:
              schema:
                $ref: "#/components/schemas/GenericRow"
            application/vnd.pgrst.array+json:
              schema:
                $ref: "#/components/schemas/GenericRows"
        "400":
          $ref: "#/components/responses/Error400"
        "404":
          $ref: "#/components/responses/Error404"
        "406":
          $ref: "#/components/responses/Error406"
        "415":
          $ref: "#/components/responses/Error415"
        "416":
          $ref: "#/components/responses/Error416"

    head:
      tags: [TablesViews]
      summary: 行の取得（ヘッダのみ）
      description: GET同等だがレスポンスボディを返さない。
      parameters:
        - $ref: "#/components/parameters/Select"
        - $ref: "#/components/parameters/Order"
        - $ref: "#/components/parameters/Limit"
        - $ref: "#/components/parameters/Offset"
        - $ref: "#/components/parameters/Or"
        - $ref: "#/components/parameters/And"
        - $ref: "#/components/parameters/Prefer"
        - $ref: "#/components/parameters/RangeUnit"
        - $ref: "#/components/parameters/Range"
      x-dynamicQueryParameters:
        description: GETと同様（列フィルタ）
      responses:
        "200":
          description: OK（ボディなし）
          headers:
            Range-Unit:
              $ref: "#/components/headers/RangeUnit"
            Content-Range:
              $ref: "#/components/headers/ContentRange"
            Preference-Applied:
              $ref: "#/components/headers/PreferenceApplied"
        "206":
          description: Partial Content（ボディなし）
          headers:
            Range-Unit:
              $ref: "#/components/headers/RangeUnit"
            Content-Range:
              $ref: "#/components/headers/ContentRange"
            Preference-Applied:
              $ref: "#/components/headers/PreferenceApplied"
        "400":
          $ref: "#/components/responses/Error400"
        "404":
          $ref: "#/components/responses/Error404"
        "415":
          $ref: "#/components/responses/Error415"
        "416":
          $ref: "#/components/responses/Error416"

    post:
      tags: [TablesViews]
      summary: INSERT / UPSERT（Preferにより切替）
      description: |
        - INSERT: 通常のPOST
        - UPSERT: Prefer: resolution=merge-duplicates（または ignore-duplicates）で有効化
        - columns クエリで投入対象キーを制限可能
      parameters:
        - $ref: "#/components/parameters/Columns"
        - $ref: "#/components/parameters/OnConflict"
        - $ref: "#/components/parameters/Prefer"
        - $ref: "#/components/parameters/Select"
      requestBody:
        required: true
        content:
          application/json:
            schema:
              oneOf:
                - $ref: "#/components/schemas/GenericRow"
                - $ref: "#/components/schemas/GenericRows"
            examples:
              single:
                summary: 単件
                value: { "id": 33, "name": "x" }
              bulk:
                summary: 複数件
                value:
                  - { "name": "J Doe", "age": 62, "height": 70 }
                  - { "name": "Jonas", "age": 10, "height": 55 }
          application/x-www-form-urlencoded:
            schema:
              $ref: "#/components/schemas/GenericRow"
          text/csv:
            schema:
              type: string
              description: |
                先頭行が列名のCSV。例:
                name,age
                J Doe,62
                Jonas,10
      responses:
        "201":
          description: Created（return=representation時は作成結果を返す）
          headers:
            Location:
              schema:
                type: string
              description: return=headers-only かつ主キーがある場合に返すことがある
            Preference-Applied:
              $ref: "#/components/headers/PreferenceApplied"
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/GenericRows"
            application/vnd.pgrst.array+json:
              schema:
                $ref: "#/components/schemas/GenericRows"
            application/vnd.pgrst.object+json:
              schema:
                $ref: "#/components/schemas/GenericRow"
        "400":
          $ref: "#/components/responses/Error400"
        "404":
          $ref: "#/components/responses/Error404"
        "415":
          $ref: "#/components/responses/Error415"

    patch:
      tags: [TablesViews]
      summary: UPDATE（フィルタ指定）
      description: |
        水平フィルタ（列フィルタ/OR/NOT等）で更新対象を指定し、ボディで更新列を指定する。
        Prefer: return=representation で更新結果を返せる。
      parameters:
        - $ref: "#/components/parameters/Select"
        - $ref: "#/components/parameters/Columns"
        - $ref: "#/components/parameters/Prefer"
        - $ref: "#/components/parameters/Or"
        - $ref: "#/components/parameters/And"
      x-dynamicQueryParameters:
        description: 更新対象の列フィルタ（例: age=lt.13）
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/GenericRow"
      responses:
        "200":
          description: OK（return=representation の場合）
          headers:
            Preference-Applied:
              $ref: "#/components/headers/PreferenceApplied"
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/GenericRows"
            application/vnd.pgrst.array+json:
              schema:
                $ref: "#/components/schemas/GenericRows"
            application/vnd.pgrst.object+json:
              schema:
                $ref: "#/components/schemas/GenericRow"
        "204":
          description: No Content（return=minimal の場合）
          headers:
            Preference-Applied:
              $ref: "#/components/headers/PreferenceApplied"
        "400":
          $ref: "#/components/responses/Error400"
        "404":
          $ref: "#/components/responses/Error404"
        "415":
          $ref: "#/components/responses/Error415"

    put:
      tags: [TablesViews]
      summary: 単一行 UPSERT（PKをeqで指定、全列必須）
      description: |
        単一行upsertはPUTで行う。主キー列をクエリで eq 指定し、ボディには全列（主キー含む）を指定する。
        - limit/offset を付けた場合は PGRST114
        - クエリPKとボディPKが不一致の場合は PGRST115
      parameters:
        - $ref: "#/components/parameters/Prefer"
        - $ref: "#/components/parameters/Select"
      x-dynamicQueryParameters:
        description: |
          主キー列を eq で指定する（例: id=eq.4）。
          ※ 本PUTでは limit/offset は禁止。
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/GenericRow"
      responses:
        "200":
          description: OK（return=representation の場合）
          headers:
            Preference-Applied:
              $ref: "#/components/headers/PreferenceApplied"
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/GenericRows"
            application/vnd.pgrst.object+json:
              schema:
                $ref: "#/components/schemas/GenericRow"
        "201":
          description: Created（挿入となった場合に返すことがある）
        "204":
          description: No Content（return=minimal の場合）
        "400":
          $ref: "#/components/responses/Error400"
        "404":
          $ref: "#/components/responses/Error404"
        "415":
          $ref: "#/components/responses/Error415"

    delete:
      tags: [TablesViews]
      summary: DELETE（フィルタ指定）
      description: |
        水平フィルタ（列フィルタ/OR/NOT等）で削除対象を指定する。
        Prefer: return=representation で削除結果を返せる。
      parameters:
        - $ref: "#/components/parameters/Select"
        - $ref: "#/components/parameters/Prefer"
        - $ref: "#/components/parameters/Or"
        - $ref: "#/components/parameters/And"
      x-dynamicQueryParameters:
        description: 削除対象の列フィルタ（例: active=is.false）
      responses:
        "200":
          description: OK（return=representation の場合）
          headers:
            Preference-Applied:
              $ref: "#/components/headers/PreferenceApplied"
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/GenericRows"
            application/vnd.pgrst.array+json:
              schema:
                $ref: "#/components/schemas/GenericRows"
            application/vnd.pgrst.object+json:
              schema:
                $ref: "#/components/schemas/GenericRow"
        "204":
          description: No Content（return=minimal の場合）
          headers:
            Preference-Applied:
              $ref: "#/components/headers/PreferenceApplied"
        "400":
          $ref: "#/components/responses/Error400"
        "404":
          $ref: "#/components/responses/Error404"

components:
  schemas:
    GenericRow:
      type: object
      additionalProperties: true
      description: 動的スキーマの1行（列はresourceに依存）
    GenericRows:
      type: array
      items:
        $ref: "#/components/schemas/GenericRow"
    Error:
      type: object
      required: [code, message]
      properties:
        code:
          type: string
          description: PGRSTxxx または SQLSTATE
        message:
          type: string
        details:
          type: string
          nullable: true
        hint:
          type: string
          nullable: true

  headers:
    RangeUnit:
      schema:
        type: string
        example: items
      description: Range単位。items固定。
    ContentRange:
      schema:
        type: string
        example: 0-19/*
      description: RFC7233互換の範囲/総件数表現。
    PreferenceApplied:
      schema:
        type: string
      description: 適用されたPrefer（サーバが返す場合）

  parameters:
    Resource:
      name: resource
      in: path
      required: true
      schema:
        type: string
      description: テーブル名またはビュー名（URLエンコード済みを許容）

    Select:
      name: select
      in: query
      required: false
      schema:
        type: string
      description: |
        垂直フィルタ（射影）。例: select=first_name,age / select=fullName:full_name / select=salary::text

    Order:
      name: order
      in: query
      required: false
      schema:
        type: string
      description: |
        ソート。例: order=age.desc,height.asc / order=age.nullsfirst / order=age.desc.nullslast

    Limit:
      name: limit
      in: query
      required: false
      schema:
        type: integer
        minimum: 0
      description: 最大取得件数

    Offset:
      name: offset
      in: query
      required: false
      schema:
        type: integer
        minimum: 0
      description: 開始オフセット

    Columns:
      name: columns
      in: query
      required: false
      schema:
        type: string
      description: |
        挿入/更新対象にするpayloadキーをカンマ区切りで指定（それ以外のキーは無視）

    OnConflict:
      name: on_conflict
      in: query
      required: false
      schema:
        type: string
      description: |
        Upsertの衝突判定列（UNIQUE列名等）を指定する

    Or:
      name: or
      in: query
      required: false
      schema:
        type: string
      description: |
        OR条件。例: or=(age.lt.18,age.gt.21)

    And:
      name: and
      in: query
      required: false
      schema:
        type: string
      description: |
        AND条件（複合論理用）。例: and=(a.eq.1,b.eq.2)
        NOTは not.and=(...) のようにパラメータ名に not. を付与して表現可能。

    Prefer:
      name: Prefer
      in: header
      required: false
      schema:
        type: string
      description: |
        RFC7240のPrefer互換。例:
        - Prefer: return=representation
        - Prefer: resolution=merge-duplicates, missing=default
        - Prefer: handling=strict, max-affected=10
        - Prefer: count=exact
        注意: count=planned / count=estimated は本APIではPGRST127で拒否。

    RangeUnit:
      name: Range-Unit
      in: header
      required: false
      schema:
        type: string
        enum: [items]
      description: Range単位。items固定。

    Range:
      name: Range
      in: header
      required: false
      schema:
        type: string
        pattern: '^[0-9]+-[0-9]*$'
        examples:
          first20:
            value: "0-19"
          openEnded:
            value: "10-"
      description: itemsレンジ。例: 0-19, 10-

  responses:
    Error400:
      description: Bad Request（PGRST100/102/114/115/122/124/127 等）
      content:
        application/json:
          schema:
            $ref: "#/components/schemas/Error"
    Error404:
      description: Not Found（PGRST205 等）
      content:
        application/json:
          schema:
            $ref: "#/components/schemas/Error"
    Error406:
      description: Not Acceptable（PGRST116 等）
      content:
        application/json:
          schema:
            $ref: "#/components/schemas/Error"
    Error415:
      description: Unsupported Media Type（PGRST107 等）
      content:
        application/json:
          schema:
            $ref: "#/components/schemas/Error"
    Error416:
      description: Range Not Satisfiable（PGRST103）
      content:
        application/json:
          schema:
            $ref: "#/components/schemas/Error"
```

---

## 付録：実装上の「PGRST127」発生条件（本仕様で固定）

* 以下の演算子がクエリに現れた場合：`match/imatch/fts/plfts/phfts/wfts/cs/cd/ov/sl/sr/nxr/nxl/adj` → 400 `PGRST127`（details に未実装機能名）([PostgREST 14][4])
* `Prefer: count=planned` または `Prefer: count=estimated` → 400 `PGRST127`（details に `count=planned` 等）([PostgREST 14][3])


[1]: https://docs.postgrest.org/en/latest/references/api/tables_views.html "Tables and Views — PostgREST devel  documentation"
[2]: https://docs.postgrest.org/en/v14/references/errors.html "Errors — PostgREST 14  documentation"
[3]: https://docs.postgrest.org/en/latest/references/api/pagination_count.html "Pagination and Count — PostgREST devel  documentation"
[4]: https://docs.postgrest.org/en/stable/references/api/tables_views.html "Tables and Views — PostgREST 14  documentation"
[5]: https://docs.postgrest.org/en/stable/references/api/resource_representation.html "Resource Representation — PostgREST 14  documentation"
[6]: https://docs.postgrest.org/en/stable/references/api/preferences.html "Prefer Header — PostgREST 14  documentation"
