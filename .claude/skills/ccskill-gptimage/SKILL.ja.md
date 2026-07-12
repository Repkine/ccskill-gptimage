---
name: ccskill-gptimage
description: |
  画像生成が必要な時に使用するスキル。
  OpenAI gpt-image-2 (ChatGPT Images 2.0) で高品質な画像を生成・編集します。
  日本語/多言語テキスト描画、複雑指示の解釈、参照画像保持、密なテキストを含むインフォグラフィックに強い。
---

# ccskill-gptimage 画像生成スキル

## 概要

OpenAI gpt-image-2 を使って画像を生成・編集します。**ユーザーは「こんな画像が欲しい」と意図を伝えるだけで十分** で、プロンプトの構造化・パラメータ選択・コスト最適化は Claude が会話履歴とプロジェクト文脈から自動で組み立てます。姉妹スキル `ccskill-nanobanana` (Gemini 3 Pro Image) とは用途で使い分けます(下表参照)。

## 前提条件

- リポジトリの `./install.sh` が実行済みであること — `ccskill-gptimage` コマンドが `~/.local/bin`(PATH)に配備され、本スキルがユーザレベル登録される。コマンドが見つからない場合は直接呼び出しにフォールバック: `$CCSKILL_GPTIMAGE_DIR/venv/bin/python $CCSKILL_GPTIMAGE_DIR/generate_image.py ...`(環境変数 `CCSKILL_GPTIMAGE_DIR` がリポジトリを指している必要あり)
- **以下のうち少なくとも 1 つが利用可能であること:**
  - **Codex CLI**(ChatGPT サブスク勢推奨): `brew install codex` + `codex login`。API キー不要・追加課金なし
  - **OpenAI API キー**: `OPENAI_API_KEY` を環境変数またはリポジトリの `.env` に設定。**Organization が Verified 状態**であること(未検証 Org は 403)
- デフォルト `--backend auto` は Codex を優先し、失敗時に API へフォールバック。明示指定は `--backend codex` / `--backend api`

## 使い方

```bash
ccskill-gptimage generate "プロンプト"
```

### オプション

| オプション | 説明 | デフォルト | 値 |
|---|---|---|---|
| `--size` | 出力サイズ(`auto` または自由な `WxH`。下の解像度制約参照) | `1024x1024` | `auto` / `1024x1024` / `1024x1536` / `1536x1024` / 最大 `3840x2160`(4K) |
| `--quality` | 品質 | `auto` | `auto` / `low` / `medium` / `high` |
| `--background` | 背景 | `auto` | `auto` / `opaque`(`transparent` には `--model gpt-image-1.5`) |
| `--output-format` | 出力形式 | `png` | `png` / `jpeg` / `webp` |
| `--output-compression` | 圧縮率 (jpeg/webp) | なし | 0-100 |
| `--output` | 出力ディレクトリ | `./generated_images` | 任意のパス |
| `--output-name` | 出力ファイル名(拡張子は output-format から) | タイムスタンプ | 任意の文字列 |
| `--reference` | 参照画像(複数指定可) | なし | 画像ファイルパス |
| `--mask` | マスク画像(透明部分が編集対象、`--reference` 必須) | なし | 画像ファイルパス |
| `--input-fidelity` | gpt-image-2 では指定不要(常に最大忠実度)。`--model gpt-image-1.5` 用 | なし | `high` / `low` |
| `--moderation` | モデレーション | `auto` | `auto` / `low` |
| `--model` | モデル ID | `gpt-image-2` | 任意のモデル ID |
| `--backend` | 画像生成 backend | `auto` | `auto`(Codex 優先・API フォールバック)/ `codex`(Codex CLI 強制)/ `api`(OpenAI API 強制) |

### クイック例

```bash
# テキストから画像生成
ccskill-gptimage generate \
  "A minimalist editorial poster with the exact title \"腹落ちDMARC\" in large serif Japanese font at the top, dark navy background" \
  --size 1024x1536 --quality high

# 参照画像で編集
ccskill-gptimage generate \
  "Replace only the background with a neon Tokyo street at night. Preserve the person's face and pose exactly as in the reference." \
  --reference ./portrait.png --quality high
```

**ユースケース別の完成プロンプト例とパターン**は下の [Use Case Index](#use-case-index) を参照。各ユースケースごとに `prompts/` 配下のファイルに分かれており、Cookbook 原文ベースの再利用可能なプロンプトが載っています。

---

## プロンプト設計 10 原則(OpenAI Cookbook Section 2)

出典: [GPT Image Generation Models Prompting Guide](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide)(2026-04-23 取得)。各原則は公式 Cookbook の推奨事項そのもの。詳細と具体プロンプト例は `prompts/*.md` にある。

1. **Structure + Goal** — `背景/シーン → 被写体 → 細部 → Constraints` の順序で書く。用途(広告 / UI / インフォ)を明示してモードと仕上げレベルを伝える
2. **Prompt Format** — 段落 / JSON / tag / 箇条書き、どれでも良い。維持しやすいものを選ぶ
3. **Specificity + Quality Cues** — 素材・形状・テクスチャ・媒体を具体化。フォトリアルには `photorealistic` をプロンプトに直接入れる。**物理スケール / アスペクト比は数値で明示**(`about 8–9 inches tall`、`A4 size`、`portrait 3:1`、`smartphone-sized`)— 曖昧な `tall`/`small` より具体寸法のほうが比率が圧倒的に安定する(マカロニ・パッケージ合成の dogfooding で実証)
4. **Latency vs Fidelity** — 試行は `quality='low'`、小さいテキスト / インフォ / 近接ポートレートは `medium`〜`high` を事前比較
5. **Composition** — 構図(close-up / wide / top-down)、アングル(eye-level / low-angle)、光(soft diffuse / golden hour)、配置(`logo top-right` 等)を指定
6. **People, Pose, and Action** — スケール、フレーミング、視線、物との相互作用を記述(例: `full body visible, feet included`、`looking down at the book, not at the camera`)
7. **Constraints — 変える/保持する** — 除外したいものを明示(`no watermark`、`no extra text`)。編集時は `change only X` + `keep everything else the same` を毎回書く
8. **Text in Images** — 文字列は **quotes** または **ALL CAPS** + タイポ詳細(font style, size, color, placement)。難語は一文字ずつ綴る。小さな文字は `quality=medium` 以上
9. **Multi-Image Inputs** — 入力を **index + description** で参照(`Image 1: product photo…, Image 2: style reference…`)し、相互作用を書く(`apply Image 2's style to Image 1`)
10. **Iterate Instead of Overloading** — 最初はシンプルなベースから、**1 変更ずつ**段階的に追い込む(`make lighting warmer`、`remove the extra tree`)

---

## Use Case Index

ユーザーの意図が以下のどれかに当てはまったら、**該当 `prompts/` ファイルを Read**して、Cookbook ベースのプロンプトパターン・パラメータ・gpt-image-2 固有の注意を取り込む。progressive disclosure — 必要な分だけロードする。

### 生成(text → image)

| ユーザー意図 | プロンプトガイド | 推奨パラメータ |
|---|---|---|
| インフォグラフィック / 概念図 / ピッチスライド / チャート | [`prompts/infographics-and-diagrams.md`](prompts/infographics-and-diagrams.md) | `1024x1536` or `1536x1024`, `high` |
| フォトリアル / 歴史的場面 | [`prompts/photorealism.md`](prompts/photorealism.md) | `1024x1536`, `medium`–`high` |
| ロゴ / ブランドマーク | [`prompts/logo.md`](prompts/logo.md) | `1024x1024`, `high` |
| 広告 / マーケ / 画像内テキスト | [`prompts/ads-and-marketing.md`](prompts/ads-and-marketing.md) | `1024x1536`, `high` |
| コミック / ストーリーボード | [`prompts/comic-and-storyboard.md`](prompts/comic-and-storyboard.md) | `1024x1536`, `high` |
| モバイル / Web の UI モックアップ | [`prompts/ui-mockups.md`](prompts/ui-mockups.md) | モバイルは縦長、Web は横長、`high` |
| キャラ一貫性 / コンセプトアート / グリーティングカード | [`prompts/character-and-concept.md`](prompts/character-and-concept.md) | `1024x1536`, `medium`–`high` |
| 文化圏の雰囲気(日本語看板・街並み) | [`prompts/cultural-atmosphere.md`](prompts/cultural-atmosphere.md) | `1024x1536` or `1536x1024`, `high` |

### 編集(text + image → image)

| ユーザー意図 | プロンプトガイド | 備考 |
|---|---|---|
| 画像内テキストの多言語翻訳 | [`prompts/image-translation.md`](prompts/image-translation.md) | レイアウト/タイポを保持 |
| 参照画像のスタイルを別コンテンツへ | [`prompts/style-transfer.md`](prompts/style-transfer.md) | 参照 1 枚 |
| 人物の服装変更(アイデンティティ保持) | [`prompts/try-on.md`](prompts/try-on.md) | 最大 5 枚参照 |
| スケッチ → 写真リアル | [`prompts/sketch-to-render.md`](prompts/sketch-to-render.md) | 参照 1 枚 |
| 商品抽出 / インテリア精密置換 | [`prompts/product-mockup.md`](prompts/product-mockup.md) | `--background opaque` |
| 天候・時間帯変更 / オブジェクト削除 | [`prompts/scene-transform.md`](prompts/scene-transform.md) | 参照 1 枚 |
| 人物を新シーンへ / 複数画像合成 | [`prompts/scene-composite.md`](prompts/scene-composite.md) | 参照 1〜5 枚 |

全カタログ・横断参照は [`prompts/README.md`](prompts/README.md) 参照。

---

## gpt-image-2 固有の制約(必ず押さえる)

全ユースケース共通。プロンプト組み立てのたびに留意すべき文脈。

### 透過背景は非対応

`--background transparent` は 400 エラー。透過 PNG が必要なら:

1. **`rembg` 後処理(推奨)** — gpt-image-2 のテキスト描画・レイアウトの強みを活かせる:
   ```bash
   ccskill-gptimage generate "... on plain white background"
   rembg i generated_images/<画像>.png generated_images/<画像>_alpha.png
   ```
2. **`gpt-image-1.5` に切替**(旧モデルだが透過対応)
3. **姉妹スキル `ccskill-nanobanana` に切替**

### `input_fidelity` は指定不要(自動最大)

gpt-image-2 は**常に自動で最大忠実度**で入力画像を処理する。`--input-fidelity` を指定すると 400。これは「欠落」ではなく「自動で常時有効」で、構図保持はむしろ強い。プロンプト内に明示的な `Preserve …` を書くだけで良い。

> **注意**: Cookbook の edit 章の例(5.6, 5.7, 5.8, 5.9)は `input_fidelity="high"` を明記しているが、**gpt-image-2 では持ち込まない**。本スキルの CLI バリデータが自動で外すが、プロンプト/スクリプトでも最初から書かない方が綺麗。

トレードオフとして入力画像トークンが増えてコスト増になるので、**不要な参照画像は渡さない**。

### edit API は常に全画面再描画

マスクを付けても gpt-image-2 の edit エンドポイントは全ピクセル再生成する。Cookbook 原文:

> "Masking with GPT Image is entirely prompt-based. The model uses the mask as guidance, but may not follow its exact shape with complete precision."

自動最大忠実度のおかげで非対象領域は UI テキスト・シリアル番号レベルまで保持されるが、**ピクセル単位完全一致ではない**。厳密保持が必要なケースは次節参照。

### その他の制約

- **Organization Verification 必須**(未検証 → 403)
- **レート制限**: Tier 1 = 5 IPM(本番は Tier 3+ 推奨)
- **タイムアウト**: 高品質・複雑プロンプトで最大 2 分 — SDK タイムアウトは 120 秒以上に
- **レスポンス**: `b64_json` のみ(URL は返らない)
- **非対応**: function calling、structured outputs
- **解像度**: `--size` は `auto` または任意の `WxH` を受け付け、gpt-image-2 の制約で検証する — **各辺が 16 の倍数**、**最大辺 ≤ 3840px**(4K まで、例 `3840x2160`)、**アスペクト比 ≤ 3:1**、**総ピクセル 655,360〜8,294,400**。違反は API 呼び出し**前**に具体的なエラーで弾く。`--backend api` は厳密にサイズを守り、`--backend codex` は非決定的なため警告のみ。よく使うプリセット: `1024x1024 / 1024x1536 / 1536x1024`。(2026-06-11 実証: `--backend api` で `3840x2160` を実解像度どおり生成)

---

## 局所編集戦略

既存画像の**一部だけ**差し替えたいとき(例: UI スクリーンショットの地図部分を匿名化)、周囲をどれだけ厳格に保持したいかで戦略を選ぶ。

| 目的 | 推奨アプローチ |
|---|---|
| 対象領域だけ差し替えたく、**周囲は非常に高い忠実度で再描画されるがピクセル同一ではない**のを許容(UI テキストはほぼ保持される) | `--reference` + 強い `Preserve absolutely everything else exactly as in the reference: …` プロンプト。**保持要素を列挙**(ヘッダ、日付、ボタンラベル、ロゴ、引用テキスト)。ブログ・ドキュメント用途ならこれで十分 |
| 小さな 1 領域だけ再描画したい / モデルが対象オブジェクトに強い解釈バイアスを持っていてプロンプトで上書きしきれない | `--reference` + `--mask`(下記「マスク edit」参照)。マスク形状は **soft guidance** であって厳密保護ではないが、モデルの注意を空間的に集中させることで小さな曖昧オブジェクトの解釈バイアスを破る助けになる |
| 編集領域外を**ピクセル単位で完全保持**(法的証拠、規制対象スクショ) | **クロップ → 編集 → 貼り戻しのハイブリッド**(Pillow / ImageMagick)。gpt-image-2 はクロップしたタイルだけ編集、その他は元画像のビット列がそのまま残る |
| 複数画像からの合成 | `--reference a.png --reference b.png …`(マスクなし)+ ゴール志向プロンプト。`prompts/scene-composite.md` 参照 |

アプローチ 1 で効くプロンプトパターン:

- **保持要素を列挙** — すべての可視要素を引用符付きで名指す。列挙が多いほど保持が強くなる
- **「X だけ差し替えろ」** — `"Replace ONLY the map area with [架空内容]. Do not change any layout, font, color, or text outside the map rectangle."`

実証: Apple Business「紛失モード位置確認」スクリーンショットの地図部分を `--reference --quality high` 一発で匿名化(街路・河川・実在 POI を架空の住宅地に差し替え)しつつ、周辺 UI をデバイスシリアル番号レベルで保持した実例がある。

### マスク edit — 小領域の集中再描画

アルファチャンネル付き PNG を `--mask` で渡す。透明ピクセル(`alpha = 0`)が**編集対象**、不透明ピクセルは保護領域。OpenAI Cookbook 原文:

> "Masking with GPT Image is entirely prompt-based. The model uses the mask as guidance, but may not follow its exact shape with complete precision."

つまり:
- マスクは**ピクセル単位の厳密保護を保証しない**が、実用上は不透明領域は入力に非常に近く保たれる
- マスクは **モデルの注意を編集領域に集中させる効果**があり、対象領域での視覚的解釈バイアスを上書きするのに役立つことが多い
- 効果は**確約されない** — 頑固な小領域問題に効くこともあれば、効かないこともある

#### 推奨ワークフロー

マスク作成は**本スキルの範囲外** — Pixelmator / Photoshop / GIMP 等の画像編集ツールで作る(macOS Preview は機能不足)。低コスト品質で反復してから本番へ:

1. **マスク作成** — ベース画像と同じサイズの PNG を作り、編集したい領域を完全透明(alpha = 0)、それ以外を完全不透明にして保存
2. **安く試す** — `--mask <mask.png> --reference <base.png> --quality low`(または `medium`)で複数プロンプトを試行。1 回 ¥1〜¥12
3. **当たりを high で本番** — 良さそうな結果が出たら `--quality high` で再生成、または当たりを `--reference` として渡して更に磨く

#### 実証

`--reference` のみで 4 ターン編集してもモデルが「フォークの歯」と一貫して誤解釈していた小さな日本陶器(箸置き)を、`--mask` でその領域を指定したところ、明確に陶器寄りに改善した(完璧ではないが意図に近づいた)。**マスクは小領域の頑固な解釈バイアスを破るのに有効**、ただし pixel-precise ではないことを再確認。

---

## Backend 選択(`--backend`)

同じ `gpt-image-2` モデルへの 2 つの transport がある。`auto` で自動選択、または明示固定可能。

| Backend | 使用場面 | コスト | 制約 |
|---|---|---|---|
| `codex` | ChatGPT サブスク + Codex CLI 導入済み | サブスク枠内(追加課金なし) | `--size` のピクセル厳密制御不可(agent 経由)、`--mask` 非対応 |
| `api` | `OPENAI_API_KEY` + Verified Org あり | 従量課金($0.006〜$0.211/枚) | 全パラメータが厳密に効く |
| `auto` (デフォルト) | どちらか or 両方 | Codex 優先 → API フォールバック | Codex 失敗時 + `OPENAI_API_KEY` あれば API へ自動 |

両方利用可能なら `auto` 推奨 — Codex でコストを抑え、できないことだけ API でカバー。

**`--backend api` を強制すべきケース**:
- `--mask` を使う(Codex は mask を渡せない)
- ピクセル厳密 `--size` が必要(Codex の image_gen は若干サイズが揺れることがある)
- 厳密な再現性が必要(Codex の agent 層が非決定性を加える)

下記のコスト最適化アドバイスは **両 backend 共通** — 価格差は「誰が支払うか」(従量課金 vs サブスク枠)であって、モデル挙動の差ではない。

---

## コスト最適化

試行時は `--quality low`($0.006/枚)、本番は `medium`($0.053) または `high`($0.211)。

**非自明なコスト罠**: 縦長 `1024×1536` の `high` は **$0.165** で、正方形 `1024×1024` の `high`($0.211) より安い。縦長で成立する用途はあえて縦長を選ぶ。

| 品質 | 1024×1024 | 1024×1536 | 1536×1024 |
|---|---|---|---|
| low | $0.006 | $0.011 | $0.011 |
| medium | $0.053 | $0.080 | $0.079 |
| high | $0.211 | **$0.165** | $0.210 |

---

## 姉妹スキルとの使い分け

| 用途 | 第一選択 | 理由 |
|---|---|---|
| 日本語/漢字テキスト入りポスター | **ccskill-gptimage** | テキスト描画が最強 |
| 業務系インフォグラフィック / ピッチスライド | **ccskill-gptimage** | 強い指示追従 + テキストレイアウト |
| 既存画像の編集・部分修正 | **ccskill-gptimage** | 入力を自動で最大忠実度処理 |
| 写真風/イラスト風の単体ビジュアル | どちらでも | コスト感は近い |
| 透過 PNG(ロゴ・アイコン・スプライト) | どちらでも | gpt-image-2 は不可だが (a) `--model gpt-image-1.5`、(b) `rembg` 後処理、(c) ccskill-nanobanana のいずれも実用 |
| 4K 出力 | どちらでも | gpt-image-2 は 4K(`3840x2160`、最大辺 ≤ 3840px)まで `--backend api` で対応。nanobanana も可 |

---

## 出力

各画像と並列に **メタデータ JSON サイドカー**(`{名前}.{ext}.json`)が保存される。プロンプト・`revised_prompt`・パラメータ・タイムスタンプを含み、再現・微調整に使える。

`revised_prompt`: gpt-image-2 がパラフレーズしたプロンプトを返すことがある。本スキルは `[Revised] ...` として stdout に表示 + サイドカーに保存する。次ターンのプロンプト精緻化のヒントとして使える。

## 生成画像の閲覧

生成した画像は共有ギャラリーストア(`~/.ccskill-gptimage/gallery`、`CCSKILL_GPTIMAGE_GALLERY_DIR` で上書き可)にも保存され、`ccskill-nanobanana` や `ccskill-omniflash` の生成物と一緒に閲覧できる。[ccskill-gallery](https://github.com/feedtailor/ccskill-gallery) をインストールし以下を実行:

```bash
ccskill-gptimage browse
```

`ccskill-gallery browse` に委譲する(`--port`/`--bind`/`--no-open` はそのまま渡る)。ccskill-gallery が未インストールなら、画像の保存先を表示するだけ。

## トラブルシューティング

- **原因が分からない時** → `ccskill-gptimage doctor` で環境 + backend を一括診断(秘密ファイルの中身は読まない。presence ベースで報告)
- **`ccskill-gptimage` の実行で毎回許可を聞かれる** → `~/.claude/settings.json` の `permissions.allow` に `Bash(ccskill-gptimage:*)` を追加(インストーラは設定を変更しません)
- **403 Forbidden** → Org Verification を確認
- **レート超過** → Tier を上げる、または `--quality low` で間引く
- **タイムアウト** → ネットワーク確認、SDK タイムアウトを 120 秒以上に
- **日本語が崩れる** → 引用符で囲う、フォント指定(`serif Japanese font`)、`quality=high`
- **`--input-fidelity` で 400** → 指定を外す(gpt-image-2 は自動最大)。`--model gpt-image-1.5` でのみ有効
- **`--background transparent` で 400** → [透過背景の節](#透過背景は非対応)参照
- **「画像が見つかりません」のエラー表示** → リポジトリで `git pull` して最新化する。Codex の新仕様による影響。
