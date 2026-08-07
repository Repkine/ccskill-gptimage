# ccskill-gptimage Image Generation Skill

[Русский README](README.md) · [日本語 README](README.ja.md)

A Claude Code image-generation skill powered by OpenAI **gpt-image-2** (ChatGPT Images 2.0). Also usable as a standalone image-generation script.

## Features

You don't need to write prompts explicitly: the skill composes an optimal prompt from your project information and context, and generates images with ChatGPT Images 2.0 inside a Claude Code session.

- **No API key needed** — works in association with your ChatGPT subscription (an API key is required for 4K / strict exact-size generation)
- **Multilingual text rendering** — strong at non-Latin scripts like Japanese (kanji/kana/vertical), Korean, and Chinese
- **Reference-image editing** — composite and partially edit existing images via `--reference`
- **Auto metadata sidecar** — the prompt and parameters used for each generation, saved as JSON

## Examples

Examples generated with this skill. See the full gallery at [`docs/gallery.md`](docs/gallery.md).

<table>
<tr>
  <td align="center" width="33%"><img src="assets/capability-survey/categories/01_photorealistic_portrait_woman.png" width="260" alt="Photoreal portrait"></td>
  <td align="center" width="33%"><img src="assets/capability-survey/categories/19_urban_tokyo_rainy_night_v3.png" width="260" alt="Tokyo Shibuya scramble crossing at rainy night"></td>
  <td align="center" width="33%"><a href="docs/gallery.md"><img src="assets/capability-survey/categories/18_nature_volcanic_coast_dawn.png" width="260" alt="See the full gallery"></a></td>
</tr>
<tr>
  <td align="center" width="33%"><img src="assets/capability-survey/categories/24_line_drawing_fashion_sketch.png" width="260" alt="Fashion line drawing"></td>
  <td align="center" width="33%"><img src="assets/capability-survey/categories/14_japanese_poster_vertical_tategaki.png" width="260" alt="Vertical Japanese poster"></td>
  <td align="center" width="33%"><img src="assets/capability-survey/categories/06_ui_mockup_settings_japanese.png" width="260" alt="iOS Settings UI in Japanese"></td>
</tr>
</table>

## Requirements

This skill can be used in two ways, each with different requirements. You can also switch between the two backends with the `--backend` parameter. For 4K generation or strict size control, Option B (API key) is required, so using both together is recommended.

**Option A: ChatGPT subscription + Codex CLI**
- Python 3.10+
- ChatGPT subscription (Plus or higher)
- [Codex CLI](https://github.com/openai/codex) installed and logged in via `codex login`

**Option B: OpenAI API key**
- Python 3.10+
- OpenAI API key
- Organization Verification

## Setup
### 1. Clone the repository
Clone anywhere you prefer.

```bash
cd /path/to/projects
git clone https://github.com/feedtailor/ccskill-gptimage.git
```

### 2. Prepare image generation

Make ChatGPT Images 2.0 available. The preparation differs by usage, so pick the one that fits — Option A is recommended.

#### Option A: ChatGPT subscription + Codex CLI
(Skip this if you already use the Codex CLI linked to your subscription.)

```bash
# Install Codex CLI (Homebrew)
brew install codex
# Log in with your ChatGPT account
codex login
```

#### Option B: OpenAI API key
Configure the following on the [OpenAI Platform](https://platform.openai.com/):

- (a) Issue an API key at [API keys](https://platform.openai.com/api-keys)
- (b) Complete verification at [Organization Settings](https://platform.openai.com/settings/organization/general) → General → Verification

Once configured, write the API key into a `.env` file.

```bash
cp .env.example .env
```

Add the API key from (a) to `.env`:
```
OPENAI_API_KEY=sk-...
```

### 3. Run the installer

Move into the directory where you cloned ccskill-gptimage and run:

```bash
cd /path/to/ccskill-gptimage
./install.sh
```

The installer takes care of everything:

- Creates the Python venv and installs dependencies
- Deploys the `ccskill-gptimage` command to `~/.local/bin` (tells you what to add if it's not in your PATH)
- Registers the skill at the user level (`~/.claude/skills/ccskill-gptimage`), so it's available in **every** Claude Code project — no per-project setup needed
- Diagnoses which backends (Codex CLI / API key) are currently available

## Usage

In any Claude Code project, just ask it to generate images with ChatGPT Images 2.0 (e.g. `use gptimage to ...`), or type `/ccskill-gptimage` in your prompt. Describe what you want **in any language** — Claude Code builds the optimal prompt from context and auto-selects size, quality, and backend for the task.

- Generate from project context
  ```
  Look at the LP HTML @lp.html and generate 3 hero-image options that fit its content
  ```
- Generate based on an existing image
  ```
  Based on the product photo @product.jpg, make versions with the weather/time changed to "overcast" and "dusk"
  ```

### Tips
- On first use, Claude Code may ask for permission to run `ccskill-gptimage`. To skip it, add `Bash(ccskill-gptimage:*)` to `permissions.allow` in `~/.claude/settings.json`.


## Updating
Run `git pull` where you cloned this skill. Both the skill registration and the command are symlinks to the clone, so they pick up the update automatically:

```bash
cd /path/to/ccskill-gptimage
git pull
```

## Uninstalling

```bash
ccskill-gptimage uninstall
```

This removes the symlinks (`~/.local/bin/ccskill-gptimage` and `~/.claude/skills/ccskill-gptimage`); the cloned repository itself is kept.

## Using the CLI standalone

You can also use it as an image-generation command, from any directory:

```bash
ccskill-gptimage generate "a coastal sunset"
```

### Options

| Option | Description | Default |
|---|---|---|
| `--size` | Output size: `auto` or free `WxH` (constraints below). Presets: `1024x1024`/`1024x1536`/`1536x1024`; up to `3840x2160` (4K) | `1024x1024` |
| `--quality` | Quality (`auto`/`low`/`medium`/`high`) | `auto` |
| `--background` | Background (`auto`/`opaque`). `transparent` is unsupported by gpt-image-2 (use `gpt-image-1.5`) | `auto` |
| `--output-format` | Output format (`png`/`jpeg`/`webp`) | `png` |
| `--output-compression` | Compression for jpeg/webp (0-100) | none |
| `--output` | Output directory | `./generated_images` |
| `--reference` | Reference image (repeatable) | none |
| `--mask` | Mask image (transparent area = editable) | none |
| `--input-fidelity` | Not needed for gpt-image-2 (always max fidelity). For `gpt-image-1.5` | none |
| `--moderation` | Moderation (`auto`/`low`) | `auto` |
| `--backend` | Generation backend (`auto`/`codex`/`api`). `auto` prefers Codex, falls back to API on failure | `auto` |

For details on each option, see the [Options Guide](docs/options.md).

### Examples

```bash
# Basic
ccskill-gptimage generate "A minimalist fox logo, flat vector, navy and gold"

# Japanese poster
ccskill-gptimage generate 'A minimalist editorial poster with the exact title "腹落ちDMARC" in large serif Japanese font, dark navy background' --size 1024x1536 --quality high

# Edit using a reference (background swap)
ccskill-gptimage generate "Place the same fox logo on a deep navy background with subtle gold sparkles. Preserve the fox's pose and proportions from the reference." --reference ./logo.png --quality medium

# Multi-reference composition
ccskill-gptimage generate "Photorealistic gift basket on white" --reference ./a.png --reference ./b.png --reference ./c.png

# Mask-guided editing (requires --backend api)
ccskill-gptimage generate "A sunlit indoor lounge with a pool" --reference ./lounge.png --mask ./mask.png --backend api
```

### Output files

Each image is saved with a **metadata JSON** sidecar (`{name}.{ext}.json`) for reproduction and refinement:
```json
{
  "model": "gpt-image-2",
  "prompt": "...",
  "revised_prompt": "...",
  "size": "1024x1024",
  "quality": "high",
  "timestamp": "2026-04-23T10:00:00"
}
```

## Browsing your generated images

Every image is also copied into a shared gallery store (`~/.ccskill-gptimage/gallery`), so it shows up alongside images from `ccskill-nanobanana` and `ccskill-omniflash`. To browse it, install [ccskill-gallery](https://github.com/feedtailor/ccskill-gallery) and run:

```bash
ccskill-gptimage browse
```

Without ccskill-gallery installed, this just prints where your images are stored.

## Specs

- **Model**: `gpt-image-2` (snapshot `gpt-image-2-2026-04-21`)
- **Input**: text / images
- **Output**: image only (`b64_json`, no URL is returned)
- **Max resolution**: up to 4K (longest side ≤ 3840px). `--size` accepts free `WxH` validated against the model's constraints — each side a multiple of 16, longest side ≤ 3840px, aspect ratio ≤ 3:1, total pixels 655,360–8,294,400. `--backend api` honors the exact size (e.g. `3840x2160`); `--backend codex` is non-deterministic (size not guaranteed)
- **Endpoints**: `/v1/images/generations`, `/v1/images/edits`
- **Filename**: timestamp form (e.g. `20260423_153045.png`)
- **Moderation**: `auto` (default) / `low`

## Generation time (rough guide)

Median of 3 runs per backend × quality at `1024x1024`, same prompt (range in parentheses). Approximate — varies with network and load.

| quality | api | codex |
|---|---|---|
| low | ~16s (15–18) | ~30s (22–52) |
| medium | ~46s (45–49) | ~25s (23–52) |
| high | ~138s (137–140) | ~24s (22–90) |

- **api latency scales with quality** (high takes ~2+ minutes), and timings are stable.
- **codex runs ~20–90s with high variance and does not scale with quality** — its quality is a non-deterministic hint passed through an agent layer, so a `high` request is not guaranteed to do the same heavy generation as api `high` (codex `high` being fast may mean the quality isn't fully applied). **Use api when you need strict quality/size control or reproducibility.**
- Larger sizes (e.g. 4K) take proportionally longer.

## Troubleshooting

Run `ccskill-gptimage doctor` for a quick diagnosis of your environment and backends. It never reads secret files (`.env` / Codex credentials) — checks are presence-based, and the definitive test is running an actual generation.

| Symptom | Fix |
|---|---|
| `403 Forbidden` | OpenAI Organization Verification is incomplete → complete it in Organization Settings |
| Not sure what's wrong | Run `ccskill-gptimage doctor` |

## License

MIT
