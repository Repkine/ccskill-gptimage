# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

ccskill-gptimage は Claude Code 用の画像生成スキル。OpenAI `gpt-image-2` (ChatGPT Images 2.0) を使用して、Agentic な画像推論・多言語テキスト描画・反復編集を実現する。姉妹スキル `ccskill-nanobanana` (Gemini 3 Pro Image) と並ぶ ccskill シリーズの 2 枚目の画像生成スキル。

**設計原則**:
- 最小構成スタート(Phase 0 は `generate_image.py` 1 ファイルがコア)
- ccskill-gmail 型のディスパッチャ + commands/ + registry へ段階移行(Phase 1)
- ベストプラクティス(プロンプト構造化・テキスト描画コツ等)は SKILL.md 側に集約。CLAUDE.md は開発者向け
- ユーザはプロンプトを書かない — Claude Code が会話文脈/プロジェクトコンテキストからプロンプトを構成する体験を SKILL.md で成立させる

## アーキテクチャ

```
Claude Code (Skill: SKILL.md / SKILL.ja.md)
  ↓ プロンプト・パラメータ指定
generate_image.py
  ├─ Codex CLI 経路 (--backend codex; サブスク認証, API キー不要)
  │    └─ codex exec → built-in image_gen tool → gpt-image-2
  ├─ Image API 経路 (--backend api; OPENAI_API_KEY 必須, 従量課金)
  │    └─ openai SDK → /v1/images/generations, /v1/images/edits
  └─ Responses API 経路 (Phase 0.5 で追加, previous_response_id で反復編集)
  ↓
generated_images/ に保存 + メタデータ JSON サイドカー
```

デフォルトは `--backend auto` で、Codex CLI(ChatGPT サブスク認証あり)を優先し、失敗時は OPENAI_API_KEY あれば API へフォールバック。issue #017 参照。

`ccskill-nanobanana` のスクリプト構造を踏襲し、Phase 1 で `ccskill-gmail` の CLI ディスパッチャ/registry/doctor 型へ格上げする。

## 参照

- **インストーラー**: @install.sh(venv 構築 + `~/.local/bin` への symlink 配備 + ユーザレベルスキル登録。issue #020)
- **CLI ディスパッチャ**: @ccskill-gptimage(自己位置解決。`generate` / `uninstall` / `version` / `help`)
- **画像生成スクリプト**: @generate_image.py
- **スキル定義 + プロンプトベストプラクティス + ユースケース別プロンプト集**: @.claude/skills/ccskill-gptimage/SKILL.md / SKILL.ja.md / prompts/
- **テスト**: @tests/test_generate_image.py
- **環境変数テンプレート**: @.env.example
- **ロードマップ**: @.claude/issues/

## テスト手順

```bash
# リポジトリルートで実行
python -m pytest tests/ -v
```

**注意事項**:
- テストは必ずリポジトリルートから実行する
- API 呼び出しは全てモックされている(実際の OpenAI API キーは不要)
- `unittest.mock` で OpenAI クライアント・`b64_json` レスポンスをモック

## gpt-image-2 固有の運用注意

- **Organization Verification が必須**(未検証 Org では API キーがあっても 403。`--backend codex` ならサブスク認証なので不要)
- **`background: transparent` は非対応**(指定すると 400)。透過 PNG が必要なら (a) 生成後に rembg 等で背景除去、(b) `--model gpt-image-1.5` に切替、(c) `ccskill-nanobanana` を使用
- **`input_fidelity` は非対応(常に自動で最大忠実度)**。gpt-image-2 は入力画像を常に最大忠実度で処理するためパラメータ指定が不要 — 構図保持の精度はむしろ強い。トレードオフは編集時の入力画像トークンが多くなる(コスト増)
- レート制限: Tier 1 は 5 IPM(本番バッチは Tier 3 以上が現実的)
- タイムアウト: 高品質・複雑プロンプトで最大 2 分。SDK のタイムアウトは ≥120 秒に設定
- レスポンスは常に `b64_json` のみ(URL は返らない)
- Function calling / Structured outputs 非対応
- `partial_images` は 1 枚あたり +100 tok 追加コスト

### 画像サイズの厳密制約

`--size` は `auto` または任意の `WxH` を受け付け、`validate_size()`(issue #018)が以下の制約で検証する。違反は API 呼び出し**前**に具体的な日本語エラーで弾く(出典: note.com/mauekusa 記事 + 本プロジェクトで実証):

- 各辺は **16 の倍数**
- 最大辺長 **3840 px**
- アスペクト比は **3:1 以下**(極端な縦長/横長は不可)
- 総ピクセル数は **655,360〜8,294,400** の範囲

backend 別: `--backend api` は厳密にサイズを守る。`--backend codex` は agent 経由で非決定的なため、バリデーションは通すが「サイズ非保証」を警告する。`auto / 1024x1024 / 1024x1536 / 1536x1024` は「よく使うプリセット」として残しているが enum 強制ではない。**2026-06-11 実証**: `--backend api` で上限ちょうどの `3840x2160`(= 8,294,400px)を実解像度どおり生成できることを確認(initial commit 以来 4 値固定だった enum を撤廃)。

### コスト表(出力トークンと 1 枚あたりの目安)

per image トークン数(出力単価 $30 / 1M tok):

| quality | 1024×1024 | 1024×1536 | 1536×1024 |
|---------|----------|----------|----------|
| low     | 272 tok ($0.006) | 408 tok ($0.011) | 400 tok ($0.011) |
| medium  | 1,056 tok ($0.053) | 1,584 tok ($0.080) | 1,568 tok ($0.079) |
| high    | 4,160 tok ($0.211) | 6,240 tok (**$0.165**) | 6,208 tok ($0.210) |

**コスト罠**: `1024×1536` (縦長) の `high` は **$0.165** で、`1024×1024` の `high` ($0.211) より安い。ポートレート用途は意図的に縦長を選ぶ。

(出典: [OpenAI Image generation guide](https://developers.openai.com/api/docs/guides/image-generation) — 2026-04-23 確認)

### Responses API(Phase 0.5 で追加予定)

マルチターン編集向けのもう 1 つの経路。`previous_response_id` で前ターンを継承するため、毎回画像を再アップロードする必要がない:

```python
resp = client.responses.create(
    model="gpt-5",
    input="Generate an image of a gray tabby cat hugging an otter with an orange scarf",
    tools=[{"type": "image_generation"}],
)

resp2 = client.responses.create(
    model="gpt-5",
    previous_response_id=resp.id,
    input="Now make it look photorealistic, golden hour lighting",
    tools=[{"type": "image_generation"}],
)
```

Responses API 限定で `action` パラメータ(`auto` / `generate` / `edit`)で生成と編集を明示制御可能。Phase 0.5 で `--continue <response_id>` モードを `generate_image.py` に追加予定。

### 運用上の落とし穴

- **レイテンシ**: 高品質・複雑プロンプトは最大 2 分かかる。SDK タイムアウトは 120 秒以上に
- **一貫性**: キャラクターやブランド要素の同一性は seed 機構が無いため微妙に揺れる。**参照画像 + プロンプトで明示** が必須(Cookbook 6.4 パターン、SKILL の `prompts/character-and-concept.md`)
- **レイアウト制御**: 厳密な座標指定は苦手。マスク併用か、構造化プロンプトで段階的に
- **Tier 制限**: Tier 1 は 5 IPM。本番バッチ投入は Tier 3 以上が現実的
- **`gpt-image-1.5` はデフォルトから降格したが API では利用可能**。透過 PNG のための旧モデルとして残されている

## Codex CLI backend(`--backend codex` / 自動)

ChatGPT サブスク + Codex CLI が利用可能なら、API キー不要で gpt-image-2 を呼べる。`generate_image.py` は `--backend {auto,codex,api}` で切替可能(デフォルト `auto`)。

### auto モードの判定ロジック

1. `shutil.which("codex")` が PATH 上で見つかる
2. `~/.codex/auth.json` が存在し、`tokens.access_token` が非空(= ChatGPT サブスクで `codex login` 済み)

両方満たせば Codex 経路、それ以外は API 経路。Codex 経路で失敗(timeout / exit ≠ 0 / 画像未生成)した場合、`auto` モードかつ `OPENAI_API_KEY` があれば API へフォールバックする。`--backend codex` 明示時はフォールバックしない(意図尊重)。

### Codex 経路の実装上の制約(必ず守ること)

1. **CLI 引数順序**: `codex exec ... 'PROMPT' -i ref.png` の順を厳守。`-i` は variadic で後続の positional prompt まで画像として食う罠がある(検証済み 2026-04-25)
2. **保存パス指定不可**: agent に「特定パスへ保存して」は通らない。スクリプトが出力を自動回収して指定パスへコピーする。回収方法は Codex のバージョンで異なり、両対応している(出典: PR #1 / マージコミット `6bb46b2`、issue #023):
   - 旧 Codex(2026-06-17 まで確認): `~/.codex/generated_images/<session-id>/ig_*.png` にファイル出力。`_find_latest_codex_image()` で mtime 最新を回収
   - 新 Codex(codex-cli v0.141.0 で確認): ファイルを書かず、セッションログ `~/.codex/sessions/.../rollout-*.jsonl` の `image_generation_call.result` に inline base64 で返す。`_recover_codex_image_from_session()` が `_extract_codex_session_id()` / `_find_codex_session_log()` 経由で base64 を回収する
   - ファイル出力があればそちらを優先し、無ければログ回収にフォールバックするため、新旧どちらの Codex でも動作する
3. **`image_gen` 直接使用を必ず明記**: プロンプトに「API キーやスクリプトを書かず、組み込みの image_gen ツールを直接使ってください」を入れないと、Codex は curl/Python で API 直叩きルート(従量課金化)を取る
4. **`size` / `quality` 厳密制御不可**: プロンプトで指示は通るが agent 経由のため非決定的(検証で 1024×1536 指定が 1254×1254 になる事例あり)。ピクセル単位の精度が必須なら `--backend api`
5. **`--mask` 非対応**: Codex 経由では mask 受け渡し API 露出なし。auto なら API へフォールバック、`--backend codex` 明示時はエラー
6. **サンドボックス**: `--sandbox workspace-write` で動作確認済み。問題が出たら `--dangerously-bypass-approvals-and-sandbox` 採用検討(理由: OpenAI への HTTPS 通信許可のため。ローカル危害ではない)

### Codex 公式 imagegen skill との関係

Codex 自身が `~/.codex/skills/.system/imagegen/` に公式の image generation skill を持っている(`scripts/image_gen.py` CLI fallback 含む)。本スキルとは **ターゲット層が異なる**:

- **Codex 公式 imagegen**: Codex CLI ユーザ向け
- **ccskill-gptimage**: Claude Code ユーザ向け、Codex を transport として使う

機能被りではなく、別ターゲットへの提供。本スキルの差別化は (a) Claude Code 統合、(b) `--backend` 抽象化、(c) フォールバックロジック、(d) メタデータ JSON サイドカー、(e) prompts/ 14 ファイルの Cookbook 集約知見。

## コミットメッセージ規約

1行目は `type: 概要 (#issue番号)` 形式(Conventional Commits)。

| type | 用途 | update 時の履歴表示 |
|------|------|-------------------|
| `feat` | 新機能 | 表示される |
| `fix` | バグ修正 | 表示される |
| `docs` | ドキュメントのみ | 表示されない |
| `refactor` | リファクタ | 表示されない |
| `chore` | 雑務(CI、依存更新等) | 表示されない |
| `test` | テスト | 表示されない |

将来 `ccskill-gptimage update` の履歴表示を実装する際は、`feat:` と `fix:` のみ抽出する(マージコミットは除外)。ユーザーに影響する変更だけ見せる。

## コード規約

### Python
- Python 3.10+(型ヒントに `list[str]` 等の新構文を使用)
- `pathlib.Path` を使用(文字列パスではなく)
- `.env` の読み込みは `python-dotenv` 経由
- OpenAI SDK は `openai>=2.0`

### デフォルト値
- 解像度: `1024x1024`(`auto` を使う場合はモデル任せ)
- 品質: `auto`
- 出力形式: `png`
- 出力先: `./generated_images`
- ファイル名形式: `YYYYMMDD_HHMMSS.{ext}`(出力形式から拡張子を決定)

### 依存パッケージ
- `openai>=2.0` — OpenAI API クライアント
- `python-dotenv>=1.0.0` — 環境変数読み込み
- `pytest>=8.0.0` — テストフレームワーク

### Bash / シェルスクリプト(Phase 1 以降)
- `cp` ではなく `/bin/cp` を使用(macOS alias 対策)
- 環境変数 `CCSKILL_GPTIMAGE_DIR` はディスパッチャが設定
- `$()` によるサブシェルは sandbox の確認プロンプトを発生させるためパイプで代替

## 関連ドキュメント

- 公式: [OpenAI Image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
- 公式: [gpt-image-2 model page](https://developers.openai.com/api/docs/models/gpt-image-2)
- 公式: [GPT Image Generation Models Prompting Guide (Cookbook)](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide)
- 姉妹スキル: [ccskill-nanobanana](https://github.com/feedtailor/ccskill-nanobanana)
