# フロントエンドをビルドしたときに、ビルドされたファイルをバックエンドに配置する

現在、フロントエンド ( frontend/ ) をビルドしたときに、ビルドされたファイル群は `frontend/dist/` に配置される。これを `backend/static/` に配置するようにしたい。

## 追加計画（2026-01-12）

### 背景
- バックエンドは `backend/static` を `/` にマウントしており、フロントの成果物をここに置くのが最も自然。
- 現状の `frontend/dist` では FastAPI から配信されず、配置先のズレが運用上の手間になっている。

### 方針とその理由
- Vite の出力先を `backend/static` に直接向ける（`build.outDir` を `../backend/static` に設定）。
  - 理由: 余計なコピー工程をなくし、成果物の正本を1箇所に統一できるため。
- `emptyOutDir` を明示してビルド前に静的ファイルを整理する。
  - 理由: 古いハッシュ付きアセットの残存による参照ミスを防ぐため。
- コミット方針（`backend/static` をリポジトリに含めるか）を明確化し、必要なら `.gitignore` とドキュメントを更新する。
  - 理由: CI/CD でのビルド有無や配布形態によって扱いが変わるため。

### 具体的なタスク
- [ ] 現状確認: `backend/app/bootstrap/route.py` の `StaticFiles` マウント先が `backend/static` であることを再確認する。
- [ ] 現状確認: `frontend/vite.config.ts` のビルド設定と `frontend/package.json` の `build` スクリプトを確認し、影響範囲を把握する。
- [ ] 設計決定: ビルド成果物の配置方針を「Vite 出力先を直接 `backend/static`」に統一するか、コピー方式にするかを決定する（本計画では前者を前提）。
- [ ] 実装: `frontend/vite.config.ts` に `build.outDir = '../backend/static'` と `emptyOutDir = true` を追加する。
- [ ] 実装: 必要に応じて `frontend/package.json` に `build:backend` などの補助スクリプトを追加し、運用時のコマンドを明確化する。
- [ ] 実装: `backend/static` をコミット対象にするかを決め、必要なら `.gitignore` を調整する。
- [ ] 検証: `npm run build` 後に `backend/static/index.html` と `backend/static/assets/` が最新に更新されていることを確認する。
- [ ] 検証: バックエンド起動後に `/` でフロントが配信されること、`/api` が従来通り動作することを確認する。
- [ ] 記録: 変更した手順や方針を `frontend/README.md` もしくは `documents/` 配下の手順書に追記する。


