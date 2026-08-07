---
name: ccskill-gptimage
description: |
  Skill for image generation needs.
  Generate and edit high-quality images via OpenAI gpt-image-2 (ChatGPT Images 2.0).
  Strong at multilingual text rendering (Japanese included), complex instruction following,
  reference-image fidelity, and dense-text infographics.
---

# ccskill-gptimage Image Generation Skill

## Overview

Generates and edits images via OpenAI gpt-image-2. **The user only describes intent** — Claude composes the structured prompt, parameters, and cost-optimized choices from conversation and project context. Sister skill: `ccskill-nanobanana` (Gemini 3 Pro Image) — see the comparison table below.

## Prerequisites

- The repo's `./install.sh` has been run — it deploys the `ccskill-gptimage` command to `~/.local/bin` (PATH) and registers this skill at the user level. If the command is not found, fall back to direct invocation: `$CCSKILL_GPTIMAGE_DIR/venv/bin/python $CCSKILL_GPTIMAGE_DIR/generate_image.py ...` (requires the `CCSKILL_GPTIMAGE_DIR` env var pointing at the repo).
- **At least one backend must be available:**
  - **Codex CLI** (recommended for ChatGPT subscribers): `brew install codex` + `codex login`. No API key, no extra billing.
  - **OpenAI API key**: set `OPENAI_API_KEY` (env or `.env` in the repo). Your **Organization must be Verified** (unverified orgs get 403).
- Default `--backend auto` prefers Codex, falls back to API on failure. Force a specific path with `--backend codex` or `--backend api`.

## Usage

```bash
ccskill-gptimage generate "prompt"
```

### Options

| Option | Description | Default | Values |
|---|---|---|---|
| `--size` | Output size (`auto` or free `WxH`; see Resolution constraints) | `1024x1024` | `auto` / `1024x1024` / `1024x1536` / `1536x1024` / up to `3840x2160` (4K) |
| `--quality` | Quality | `auto` | `auto` / `low` / `medium` / `high` |
| `--background` | Background | `auto` | `auto` / `opaque` (for `transparent` use `--model gpt-image-1.5`) |
| `--output-format` | Output format | `png` | `png` / `jpeg` / `webp` |
| `--output-compression` | Compression (jpeg/webp) | none | 0-100 |
| `--output` | Output directory | `./generated_images` | any path |
| `--output-name` | Output filename stem (extension auto) | timestamp | any string |
| `--reference` | Reference image (repeatable) | none | image file path |
| `--mask` | Mask image (transparent area editable; requires `--reference`) | none | image file path |
| `--input-fidelity` | Not needed for gpt-image-2 (auto max). Only for `gpt-image-1.5` | none | `high` / `low` |
| `--moderation` | Moderation level | `auto` | `auto` / `low` |
| `--model` | Model ID | `gpt-image-2` | any model ID |
| `--backend` | Generation backend | `auto` | `auto` (Codex preferred, API fallback) / `codex` (force Codex CLI) / `api` (force OpenAI API) |

### Quick examples

```bash
# text-to-image (generation)
ccskill-gptimage generate \
  "A minimalist editorial poster with the exact title \"腹落ちDMARC\" in large serif Japanese font at the top, dark navy background" \
  --size 1024x1536 --quality high

# reference editing
ccskill-gptimage generate \
  "Replace only the background with a neon Tokyo street at night. Preserve the person's face and pose exactly as in the reference." \
  --reference ./portrait.png --quality high
```

For **use-case–specific prompt patterns and complete examples**, see the [Use Case Index](#use-case-index) below — each use case points to a file under `prompts/` with Cookbook-sourced prompts you can reuse.

---

## Prompt Design — 10 Principles (OpenAI Cookbook Section 2)

Source: [GPT Image Generation Models Prompting Guide](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide) (retrieved 2026-04-23). Each principle below is a direct Cookbook recommendation; details and example prompts are in `prompts/*.md`.

1. **Structure + Goal** — order as `background/scene → subject → key details → constraints`. Include the intended use (ad, UI mock, infographic) to set mode and polish.
2. **Prompt Format** — paragraph / JSON / tag / bullets all work. Pick what's easiest to maintain.
3. **Specificity + Quality Cues** — be concrete about materials, shapes, textures, medium. For photorealism, put `photorealistic` directly in the prompt. Specify **physical scale / aspect ratio numerically** (`about 8–9 inches tall`, `A4 size`, `portrait 3:1`, `smartphone-sized`) — concrete dimensions stabilize proportions far better than vague `tall`/`small` (verified in macaroni-package composite dogfooding).
4. **Latency vs Fidelity** — start with `quality='low'` while iterating. For small text, infographics, close-up portraits, compare `medium`/`high` before shipping.
5. **Composition** — specify framing (close-up, wide, top-down), angle (eye-level, low-angle), lighting (soft diffuse, golden hour), and placement (`logo top-right`, `subject centered`).
6. **People, Pose, and Action** — describe scale, body framing, gaze, object interactions (e.g. `full body visible, feet included`, `looking down at the book, not at the camera`).
7. **Constraints — what to change vs preserve** — state exclusions explicitly (`no watermark`, `no extra text`). For edits, say `change only X` + `keep everything else the same`, and repeat the preserve list each iteration.
8. **Text in Images** — put literal strings in **quotes** or **ALL CAPS** + specify typography (font style, size, color, placement). For tricky words, spell letter-by-letter. Use `medium`/`high` for small text.
9. **Multi-Image Inputs** — reference each input by **index + description** (`Image 1: product photo…, Image 2: style reference…`) and describe interaction (`apply Image 2's style to Image 1`).
10. **Iterate Instead of Overloading** — start clean, refine with **small single-change follow-ups** (`make lighting warmer`, `remove the extra tree`) instead of mega-prompts.

---

## Use Case Index

When the user's intent matches a row below, **read the linked file under `prompts/`** to get the Cookbook-sourced prompt pattern, parameters, and gpt-image-2-specific notes. Progressive disclosure: load only what you need.

### Generation (text → image)

| Intent | Prompt guide | Recommended params |
|---|---|---|
| Infographic / diagram / pitch deck slide / chart | [`prompts/infographics-and-diagrams.md`](prompts/infographics-and-diagrams.md) | `1024x1536` or `1536x1024`, `high` |
| Photorealistic candid / historical scene | [`prompts/photorealism.md`](prompts/photorealism.md) | `1024x1536`, `medium`–`high` |
| Logo / brand mark | [`prompts/logo.md`](prompts/logo.md) | `1024x1024`, `high` |
| Ad / marketing visual / text-in-image | [`prompts/ads-and-marketing.md`](prompts/ads-and-marketing.md) | `1024x1536`, `high` |
| Comic strip / storyboard | [`prompts/comic-and-storyboard.md`](prompts/comic-and-storyboard.md) | `1024x1536`, `high` |
| Mobile / Web UI mockup | [`prompts/ui-mockups.md`](prompts/ui-mockups.md) | portrait for mobile, landscape for web, `high` |
| Character consistency / concept art / keepsake | [`prompts/character-and-concept.md`](prompts/character-and-concept.md) | `1024x1536`, `medium`–`high` |
| Cultural atmosphere (Japanese signage, streetscapes) | [`prompts/cultural-atmosphere.md`](prompts/cultural-atmosphere.md) | `1024x1536` or `1536x1024`, `high` |

### Editing (text + image → image)

| Intent | Prompt guide | Notes |
|---|---|---|
| Translate in-image text to another language | [`prompts/image-translation.md`](prompts/image-translation.md) | Preserves layout/typography |
| Apply style from a reference to new content | [`prompts/style-transfer.md`](prompts/style-transfer.md) | 1 reference |
| Virtual clothing try-on (identity preserved) | [`prompts/try-on.md`](prompts/try-on.md) | Up to 5 references |
| Sketch → photorealistic render | [`prompts/sketch-to-render.md`](prompts/sketch-to-render.md) | 1 reference |
| Product extraction / interior object swap | [`prompts/product-mockup.md`](prompts/product-mockup.md) | `--background opaque` |
| Weather/lighting transform / object removal | [`prompts/scene-transform.md`](prompts/scene-transform.md) | 1 reference |
| Insert person / multi-image composite | [`prompts/scene-composite.md`](prompts/scene-composite.md) | 1–5 references |

See [`prompts/README.md`](prompts/README.md) for the full catalog and cross-references.

---

## gpt-image-2 specific constraints (memorize these)

These apply to **every** use case and are critical context when composing prompts.

### No transparent background

`--background transparent` returns 400. To produce transparent PNG, pick one of:

1. **Post-process with `rembg`** (recommended — preserves gpt-image-2's text-rendering and layout strengths):
   ```bash
   ccskill-gptimage generate "... on plain white background"
   rembg i generated_images/<image>.png generated_images/<image>_alpha.png
   ```
2. **Switch to `gpt-image-1.5`** (supports `--background transparent` natively)
3. **Use `ccskill-nanobanana`**

### `input_fidelity` is unnecessary (auto max fidelity)

gpt-image-2 **always processes input images at maximum fidelity automatically**. Specifying `--input-fidelity` returns 400. This is a feature, not a missing parameter — reference preservation is in fact strong. Just write explicit `Preserve …` clauses in the prompt.

> **Note**: The Cookbook's edit-chapter examples (5.6, 5.7, 5.8, 5.9) show `input_fidelity="high"` in their parameter blocks. **Do not carry this parameter over when using gpt-image-2** — this skill's CLI validator strips it automatically if provided, but cleaner to omit it from prompts/scripts altogether.

Trade-off: input-image tokens grow with auto-max-fidelity, so **don't pass unnecessary references** — it costs more.

### Edit API always regenerates the full canvas

Even with a mask, gpt-image-2's edit endpoint re-renders every pixel. Cookbook quote:

> "Masking with GPT Image is entirely prompt-based. The model uses the mask as guidance, but may not follow its exact shape with complete precision."

The auto-max-fidelity typically preserves non-target regions down to UI text and serial numbers — but it's not pixel-perfect. See [Local editing strategy](#local-editing-strategy) below for when this matters.

### Other constraints

- **Organization Verification required** (unverified → 403)
- **Rate limits**: Tier 1 = 5 IPM (production needs Tier 3+)
- **Timeout**: up to 2 min for high-quality/complex prompts — set SDK timeout ≥ 120 s
- **Response**: `b64_json` only (no URLs)
- **Not supported**: function calling, structured outputs
- **Resolution**: `--size` accepts `auto` or any `WxH`, validated against gpt-image-2's constraints — **each side a multiple of 16**, **longest side ≤ 3840px** (up to 4K, e.g. `3840x2160`), **aspect ratio ≤ 3:1**, **total pixels 655,360–8,294,400**. Violations are rejected with a specific error *before* any API call. `--backend api` honors the exact size; `--backend codex` is non-deterministic and only warns. Common presets: `1024x1024 / 1024x1536 / 1536x1024`. (Verified 2026-06-11: `3840x2160` generated at exact resolution via `--backend api`.)

---

## Local editing strategy

When the user wants to edit only a small region of an existing image (e.g. anonymize a map inside a UI screenshot), choose based on how strictly the surroundings must stay:

| Goal | Recommended approach |
|---|---|
| Replace one region; surroundings redrawn at very high fidelity but not pixel-identical (UI text usually survives) | `--reference` + strong `Preserve absolutely everything else exactly as in the reference: …` prompt that **enumerates** the surrounding elements (headers, dates, button labels, logos, quoted text). Often good enough for blogs / docs. |
| Re-render only one small area; other areas should be left as-is, but the model has a strong visual bias on the target area | `--reference` + `--mask` (see "Mask edit" below). Mask shape is **soft guidance**, not strict — but localizing the model's attention often improves the chance of overriding interpretation bias on small ambiguous objects. |
| **Pixel-perfect** preservation outside the edited region (legal evidence, regulated screenshots) | **Hybrid: crop → edit → paste back** with Pillow / ImageMagick. gpt-image-2 only edits the cropped tile; the rest is untouched bit-for-bit. |
| Composite from multiple images | `--reference a.png --reference b.png …` (no mask) + goal-oriented prompt. See `prompts/scene-composite.md`. |

Two prompt patterns for approach 1:

- **Enumerate what to preserve** — list every visible element by name and quoted text. The more you name, the stronger the preservation.
- **Replace only X** — `"Replace ONLY the map area with [fictional content]. Do not change any layout, font, color, or text outside the map rectangle."`

Real-world validation: single `--reference --quality high` call has been observed to replace a map area inside an Apple Business "lost mode location" screenshot with fictional content while preserving surrounding UI down to device serial numbers — small UI text at output resolution remains readable.

### Mask edit — focused regeneration of a small region

Pass an alpha-channel PNG with `--mask`. Transparent pixels (`alpha = 0`) are the **editable region**, opaque pixels are protected. Per the OpenAI Cookbook:

> "Masking with GPT Image is entirely prompt-based. The model uses the mask as guidance, but may not follow its exact shape with complete precision."

This means:
- The mask **does not strictly protect** pixels outside the transparent region — but in practice, opaque areas are kept very close to the input
- The mask **does help focus** the model's attention to the editable region, often overriding visual interpretation bias on the target area
- Effects are **not guaranteed** — masks may improve a stubborn small-region issue, or may not

#### Workflow recommendation

Mask creation is **outside this skill's scope** — produce the mask using your favorite image editor (Pixelmator / Photoshop / GIMP / Preview is generally too limited). Iterate with cheap quality first:

1. **Mask creation** — open the base image in an image editor, fill the editable area with full transparency (alpha = 0), keep the rest fully opaque, export as PNG with the same dimensions as the base
2. **Try cheaply** — run `--mask <mask.png> --reference <base.png> --quality low` (or `medium`) a few times with different prompts. Cost ¥1–¥12 per try
3. **Promote winners to high** — when an iteration looks promising, re-run with `--quality high` for the final asset, or pass the chosen iteration as a new `--reference` for further refinement

#### Real-world validation

Replacing a small ambiguous foreground object (a Japanese ceramic chopstick rest that gpt-image-2 kept misinterpreting as fork prongs in 4 successive `--reference`-only edits) was visibly improved by adding `--mask` over that region. Result was not perfect but moved clearly toward the intended ceramic shape — confirming masks are useful for **breaking through stubborn interpretation bias on small regions**, even if not pixel-precise.

---

## Backend selection (`--backend`)

Two transports reach the same `gpt-image-2` model. Pick automatically (`auto`) or pin one.

| Backend | When to use | Cost | Caveats |
|---|---|---|---|
| `codex` | ChatGPT subscriber with Codex CLI installed | Subscription quota (no extra billing) | Pixel-exact `--size` not guaranteed (agent-mediated); `--mask` not supported |
| `api` | Has `OPENAI_API_KEY` + Verified Organization | Pay-as-you-go ($0.006–$0.211/image) | All parameters honored exactly |
| `auto` (default) | Either or both | Codex first, then API | Falls back to API if Codex fails *and* `OPENAI_API_KEY` is present |

When the user has *both* available, prefer `auto` — Codex saves money, API catches anything Codex can't do.

**Force `--backend api` when**:
- `--mask` is needed (Codex can't pass masks)
- Pixel-exact `--size` is required (Codex's image_gen tool may return slightly different dimensions)
- Strict reproducibility is needed (Codex's agentic layer adds non-determinism)

Cost optimization advice (below) applies to **both** backends — the pricing difference is *who pays* (you per-image vs. ChatGPT subscription quota), not the model behavior.

---

## Cost optimization

Iterate with `--quality low` ($0.006/image). Ship with `medium` ($0.053) or `high` ($0.211).

**Counter-intuitive**: portrait `1024×1536` at `high` is **$0.165** — *cheaper* than square `1024×1024` at `high` ($0.211). Prefer portrait whenever the use case allows.

| Quality | 1024×1024 | 1024×1536 | 1536×1024 |
|---|---|---|---|
| low | $0.006 | $0.011 | $0.011 |
| medium | $0.053 | $0.080 | $0.079 |
| high | $0.211 | **$0.165** | $0.210 |

---

## Sister skill comparison

| Use case | First choice | Reason |
|---|---|---|
| Posters with Japanese/kanji text | **ccskill-gptimage** | Strongest text rendering |
| Business infographics / pitch slides | **ccskill-gptimage** | Strong instruction following + text layout |
| Editing / partial modification | **ccskill-gptimage** | Auto max input fidelity |
| Photo / illustration single visuals | Either | Comparable cost |
| Transparent PNG (logos, icons, sprites) | Either | gpt-image-2 can't natively, but (a) `--model gpt-image-1.5`, (b) `rembg` post-processing, (c) ccskill-nanobanana all work |
| 4K output | Either | gpt-image-2 supports up to 4K (`3840x2160`, longest side ≤ 3840px) via `--backend api`; nanobanana also works |

---

## Output

Each image is saved alongside a **metadata JSON sidecar** (`{name}.{ext}.json`) containing the prompt, `revised_prompt`, parameters, and timestamp — useful for reproduction and refinement.

`revised_prompt`: gpt-image-2 may return a paraphrased prompt. This skill prints it as `[Revised] ...` and saves it to the sidecar. Use it as a signal to refine follow-up prompts.

## Browsing generated images

Every image is also copied into a shared gallery store (`~/.ccskill-gptimage/gallery`, override with `CCSKILL_GPTIMAGE_GALLERY_DIR`) alongside `ccskill-nanobanana` and `ccskill-omniflash` output. Install [ccskill-gallery](https://github.com/feedtailor/ccskill-gallery) and run:

```bash
ccskill-gptimage browse
```

This delegates to `ccskill-gallery browse` (`--port`/`--bind`/`--no-open` pass through). Without ccskill-gallery installed, it just prints where the images are stored.

## Troubleshooting

- **Not sure what's wrong?** → run `ccskill-gptimage doctor` for a quick environment + backend diagnosis (it never reads secret files; reports are presence-based)
- **Claude Code keeps asking permission to run `ccskill-gptimage`** → add `Bash(ccskill-gptimage:*)` to `permissions.allow` in `~/.claude/settings.json` (the installer intentionally does not modify your settings)
- **403 Forbidden** → check Org Verification
- **Rate limit** → upgrade tier or use `--quality low` while iterating
- **Timeout** → check network; set SDK timeout ≥ 120 s
- **Japanese text broken** → wrap in quotes; specify font (`serif Japanese font`); use `quality=high`
- **400 on `--input-fidelity`** → omit it (gpt-image-2 auto max fidelity); only valid for `--model gpt-image-1.5`
- **400 on `--background transparent`** → see [transparent section](#no-transparent-background)
- **"Image not found" with Codex backend** → newer Codex CLI (v0.141.0+) returns the image in the session log instead of writing a file, so older versions of this skill fail to recover it. Run `git pull` in the repo to update.
