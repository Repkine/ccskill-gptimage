# ccskill-gptimage Options Guide

## Options at a glance

| Option | What it does | Example |
|---|---|---|
| `--size` | Output size — `auto` or exact `WxH` (each side ×16, longest ≤ 3840, aspect ≤ 3:1) | `--size 1024x1536` |
| `--quality` | `low` / `medium` / `high` / `auto` — detail & text crispness | `--quality high` |
| `--output-format` | `png` / `jpeg` / `webp` | `--output-format webp` |
| `--output-compression` | 0–100 for jpeg/webp (higher = better quality, larger file) | `--output-compression 80` |
| `--background` | `auto` / `opaque` (transparent needs `gpt-image-1.5`) | `--background opaque` |
| `--reference` | Reference image — switches to edit mode (repeatable) | `--reference base.png` |
| `--mask` | Alpha-PNG mask for local editing (needs `--reference`) | `--mask mask.png` |
| `--output` | Output directory (created if missing) | `--output ./out` |
| `--output-name` | Output filename stem (extension from format) | `--output-name hero` |
| `--model` | Model ID | `--model gpt-image-1.5` |
| `--moderation` | `auto` / `low` | `--moderation low` |
| `--input-fidelity` | Only for `gpt-image-1.5` (gpt-image-2 is always max fidelity) | `--input-fidelity high` |
| `--backend` | `auto` / `codex` / `api` | `--backend api` |

---

## `--size` — output size
### Example
```bash
ccskill-gptimage generate "A serene Japanese zen garden with raked gravel, a single red maple tree, soft morning light" \
  --backend api --size 1536x512
```

The output size must satisfy all of the following:

- Each side: a multiple of 16
- Longest side ≤ 3840 px
- Aspect ratio ≤ 3:1
- Total pixels 655,360–8,294,400

<table>
<tr>
<td colspan="2"><img src="../assets/options/size-panorama.jpg" width="720" alt="3:1 panorama zen garden"><br><code>1536x512</code>
</td>
</tr>
<tr>
<td align="center"><img src="../assets/options/size-portrait.jpg" width="240" alt="portrait 1024x1536"><br><code>1024x1536</code></td>
<td align="center"><img src="../assets/options/size-4k.jpg" width="430" alt="4K 3840x2160"><br><code>3840x2160</code> (4K, shown downscaled)</td>
</tr>
</table>

---

## `--quality` — detail & text crispness
### Example
```bash
ccskill-gptimage generate 'A rustic cafe chalkboard sign, the title "本日のおすすめ" in white chalk at the top, three menu lines below, warm lighting' \
  --backend api --quality high
```

<table>
<tr>
<td align="center"><img src="../assets/options/quality-low.jpg" width="340" alt="quality low"><br><code>--quality low</code></td>
<td align="center"><img src="../assets/options/quality-high.jpg" width="340" alt="quality high"><br><code>--quality high</code></td>
</tr>
</table>

---

## `--output-format` / `--output-compression`

Choose the file format; for jpeg/webp, trade quality for size. A higher `--output-compression` means higher quality and a larger file.

### Example

```bash
ccskill-gptimage generate "A colorful bowl of fresh fruit salad, top-down view" \
  --backend api --output-format jpeg --output-compression 80
```

| Format / compression | Typical file size (1024×1024) |
|---|---|
| `png` | ~2.0 MB (lossless) |
| `jpeg` `--output-compression 90` | ~290 KB |
| `jpeg` `--output-compression 10` | ~75 KB |
| `webp` `--output-compression 80` | ~260 KB |

---

## `--background` — transparency
`gpt-image-2` does not support transparent backgrounds. For a transparent PNG, use `--model gpt-image-1.5`.
### Example

```bash
ccskill-gptimage generate "A simple flat vector icon of a red apple, centered, on a transparent background" \
  --backend api --model gpt-image-1.5 --background transparent
```
<img src="../assets/options/transparent-apple.png" width="280" alt="transparent apple icon">

---

## `--reference` — edit an existing image
### Example

```bash
ccskill-gptimage generate "Replace only the background with a sunny green meadow under a blue sky. Keep the red apple exactly as in the reference." \
  --backend api --reference apple.png
```

<table>
<tr>
<td align="center"><img src="../assets/options/ref-apple.jpg" width="300" alt="reference apple"><br>reference</td>
<td align="center"><img src="../assets/options/edit-background.jpg" width="300" alt="background replaced"><br>result</td>
</tr>
</table>

---

## `--reference` (repeat) — multi-image composite
### Example
```bash
ccskill-gptimage generate "Image 1 is a red apple. Image 2 is a Japanese zen garden. Place the apple from Image 1 on the raked gravel of the garden from Image 2, with a soft shadow." \
  --backend api --size 1536x1024 \
  --reference apple.png --reference zen-garden.png
```

<table>
<tr>
<td align="center"><img src="../assets/options/ref-apple.jpg" width="220" alt="Image 1: red apple"><br>Image 1 (apple)</td>
<td align="center"><img src="../assets/options/ref-zen-garden.jpg" width="330" alt="Image 2: zen garden"><br>Image 2 (zen garden)</td>
</tr>
<tr><td colspan="2"><img src="../assets/options/edit-composite.jpg" width="640" alt="apple composited into the zen garden"><br>Result</td></tr>
</table>

---

## `--mask` — local editing
Pass a mask image (PNG) that guides editing to the transparent pixels only. The mask must be prepared separately and must be the same size as the reference.

### Example
An example: pass a mask covering only the upper-right region to add a butterfly there while keeping the apple unchanged.
```bash
ccskill-gptimage generate "Add a small yellow butterfly in the upper-right area. Keep the apple and background exactly the same." \
  --backend api --reference apple.png --mask mask.png
```

<table>
<tr>
<td align="center"><img src="../assets/options/ref-apple.jpg" width="230" alt="reference"><br>reference</td>
<td align="center"><img src="../assets/options/mask-region.jpg" width="230" alt="mask editable region (checkerboard = transparent)"><br>mask — editable region</td>
<td align="center"><img src="../assets/options/edit-mask.jpg" width="230" alt="masked edit result"><br>result (butterfly added)</td>
</tr>
</table>

---

## Other options

| Option | Notes |
|---|---|
| `--output` | Output directory; created automatically. Default `./generated_images`. |
| `--output-name` | Filename stem; the extension follows `--output-format`. Default is a timestamp. |
| `--model` | Defaults to `gpt-image-2`. Use `gpt-image-1.5` for transparent backgrounds or `--input-fidelity`. |
| `--moderation` | `low` relaxes the content filter; `auto` is the default. |
| `--input-fidelity` | Not needed for `gpt-image-2` (always maximum fidelity, so it's auto-dropped). Only meaningful for `gpt-image-1.5`. |
| `--backend` | `auto` prefers the Codex CLI (no API key, uses your ChatGPT subscription) and falls back to the API. Force `api` for exact `--size` or `--mask`. |
