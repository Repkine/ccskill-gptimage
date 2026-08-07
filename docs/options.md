# Руководство по параметрам ccskill-gptimage

[English version](options.en.md) · [日本語版](options.ja.md)

## Все параметры коротко

| Параметр | Что делает | Пример |
|---|---|---|
| `--size` | Размер вывода: `auto` или точный `WxH` — каждая сторона кратна 16, длинная до 3840, пропорция до 3:1 | `--size 1024x1536` |
| `--quality` | `low` / `medium` / `high` / `auto` — детализация и чёткость текста | `--quality high` |
| `--output-format` | `png` / `jpeg` / `webp` | `--output-format webp` |
| `--output-compression` | 0–100 для jpeg и webp: больше значение — выше качество и крупнее файл | `--output-compression 80` |
| `--background` | `auto` / `opaque`; для прозрачного нужна `gpt-image-1.5` | `--background opaque` |
| `--reference` | Референсное изображение, переключает в режим редактирования; можно указывать несколько раз | `--reference base.png` |
| `--mask` | PNG-маска с альфа-каналом для локального редактирования, требует `--reference` | `--mask mask.png` |
| `--output` | Каталог вывода, создаётся при отсутствии | `--output ./out` |
| `--output-name` | Имя файла без расширения, расширение берётся из формата | `--output-name hero` |
| `--model` | ID модели | `--model gpt-image-1.5` |
| `--moderation` | `auto` / `low` | `--moderation low` |
| `--input-fidelity` | Только для `gpt-image-1.5`; у gpt-image-2 точность всегда максимальная | `--input-fidelity high` |
| `--backend` | `auto` / `codex` / `api` | `--backend api` |
| `--codex-resume` | ID сессии Codex — серия слайдов наследует стиль. Есть только в этом форке | `--codex-resume <id>` |

---

## `--size` — размер вывода

### Пример

```bash
ccskill-gptimage generate "A serene Japanese zen garden with raked gravel, a single red maple tree, soft morning light" \
  --backend api --size 1536x512
```

Размер должен удовлетворять всем условиям сразу:

- каждая сторона кратна 16;
- длинная сторона не больше 3840 px;
- соотношение сторон не больше 3:1;
- общее число пикселей от 655 360 до 8 294 400.

<table>
<tr>
<td colspan="2"><img src="../assets/options/size-panorama.jpg" width="720" alt="Панорама 3:1 с садом камней"><br><code>1536x512</code>
</td>
</tr>
<tr>
<td align="center"><img src="../assets/options/size-portrait.jpg" width="240" alt="Вертикальный формат 1024x1536"><br><code>1024x1536</code></td>
<td align="center"><img src="../assets/options/size-4k.jpg" width="430" alt="4K 3840x2160"><br><code>3840x2160</code> — 4K, показан уменьшенным</td>
</tr>
</table>

---

## `--quality` — детализация и чёткость текста

### Пример

```bash
ccskill-gptimage generate 'A rustic cafe chalkboard sign, the title "СЕГОДНЯ В МЕНЮ" in white chalk at the top, three menu lines below, warm lighting' \
  --backend api --quality high
```

<table>
<tr>
<td align="center"><img src="../assets/options/quality-low.jpg" width="340" alt="Качество low"><br><code>--quality low</code></td>
<td align="center"><img src="../assets/options/quality-high.jpg" width="340" alt="Качество high"><br><code>--quality high</code></td>
</tr>
</table>

---

## `--output-format` и `--output-compression`

Выбор формата файла; для jpeg и webp — размен качества на размер. Чем выше `--output-compression`, тем выше качество и больше файл.

### Пример

```bash
ccskill-gptimage generate "A colorful bowl of fresh fruit salad, top-down view" \
  --backend api --output-format jpeg --output-compression 80
```

| Формат и сжатие | Типичный размер файла при 1024×1024 |
|---|---|
| `png` | ~2,0 МБ, без потерь |
| `jpeg` `--output-compression 90` | ~290 КБ |
| `jpeg` `--output-compression 10` | ~75 КБ |
| `webp` `--output-compression 80` | ~260 КБ |

---

## `--background` — прозрачность

`gpt-image-2` прозрачный фон не поддерживает. Если нужен прозрачный PNG, используйте `--model gpt-image-1.5`.

### Пример

```bash
ccskill-gptimage generate "A simple flat vector icon of a red apple, centered, on a transparent background" \
  --backend api --model gpt-image-1.5 --background transparent
```

<img src="../assets/options/transparent-apple.png" width="280" alt="Иконка яблока на прозрачном фоне">

---

## `--reference` — редактирование готового изображения

### Пример

```bash
ccskill-gptimage generate "Replace only the background with a sunny green meadow under a blue sky. Keep the red apple exactly as in the reference." \
  --backend api --reference apple.png
```

<table>
<tr>
<td align="center"><img src="../assets/options/ref-apple.jpg" width="300" alt="Референс с яблоком"><br>референс</td>
<td align="center"><img src="../assets/options/edit-background.jpg" width="300" alt="Фон заменён"><br>результат</td>
</tr>
</table>

---

## Несколько `--reference` — композиция из изображений

### Пример

```bash
ccskill-gptimage generate "Image 1 is a red apple. Image 2 is a Japanese zen garden. Place the apple from Image 1 on the raked gravel of the garden from Image 2, with a soft shadow." \
  --backend api --size 1536x1024 \
  --reference apple.png --reference zen-garden.png
```

<table>
<tr>
<td align="center"><img src="../assets/options/ref-apple.jpg" width="220" alt="Изображение 1: красное яблоко"><br>изображение 1 — яблоко</td>
<td align="center"><img src="../assets/options/ref-zen-garden.jpg" width="330" alt="Изображение 2: сад камней"><br>изображение 2 — сад камней</td>
</tr>
<tr><td colspan="2"><img src="../assets/options/edit-composite.jpg" width="640" alt="Яблоко вписано в сад камней"><br>результат</td></tr>
</table>

---

## `--mask` — локальное редактирование

Маска — это PNG, который направляет редактирование только в прозрачные пиксели. Готовить её нужно отдельно, и размер обязан совпадать с референсом.

### Пример

Маска закрывает всё, кроме области справа сверху, — туда добавляется бабочка, а яблоко остаётся нетронутым.

```bash
ccskill-gptimage generate "Add a small yellow butterfly in the upper-right area. Keep the apple and background exactly the same." \
  --backend api --reference apple.png --mask mask.png
```

<table>
<tr>
<td align="center"><img src="../assets/options/ref-apple.jpg" width="230" alt="Референс"><br>референс</td>
<td align="center"><img src="../assets/options/mask-region.jpg" width="230" alt="Редактируемая область маски, шахматка — прозрачность"><br>маска — редактируемая область</td>
<td align="center"><img src="../assets/options/edit-mask.jpg" width="230" alt="Результат редактирования по маске"><br>результат — бабочка добавлена</td>
</tr>
</table>

---

## Остальные параметры

| Параметр | Примечания |
|---|---|
| `--output` | Каталог вывода, создаётся автоматически. По умолчанию `./generated_images`. |
| `--output-name` | Имя файла без расширения; расширение следует за `--output-format`. По умолчанию — метка времени. |
| `--model` | По умолчанию `gpt-image-2`. Модель `gpt-image-1.5` нужна для прозрачного фона и для `--input-fidelity`. |
| `--moderation` | Значение `low` ослабляет фильтр содержимого, по умолчанию `auto`. |
| `--input-fidelity` | Для `gpt-image-2` не нужен: точность всегда максимальная, параметр отбрасывается автоматически. Имеет смысл только для `gpt-image-1.5`. |
| `--backend` | При `auto` приоритет у Codex CLI — без ключа API, по подписке ChatGPT — с откатом на API. Принудительный `api` нужен для точного `--size` и для `--mask`. |
| `--codex-resume` | Продолжает существующую сессию Codex, чтобы серия слайдов держала единый стиль. Работает только с `--backend codex`. ID берётся из строки `[Session] <id>` в выводе предыдущего запуска. Возможность есть только в этом форке. |
