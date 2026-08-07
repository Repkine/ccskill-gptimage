# ccskill-gptimage — генерация изображений для Claude Code

[English README](README.en.md) · [日本語 README](README.ja.md)

Скилл Claude Code для генерации изображений на базе OpenAI **gpt-image-2** (ChatGPT Images 2.0). Работает и как самостоятельный скрипт генерации.

> **Это форк.** Оригинал — [feedtailor/ccskill-gptimage](https://github.com/feedtailor/ccskill-gptimage).
> Здесь добавлено то, чего нет в апстриме:
> - **работоспособность под Windows** — пять багов, из-за которых backend `codex` не запускался вовсе (подробности в истории коммитов);
> - **`--codex-resume`** — наследование визуального стиля между слайдами серии;
> - **вся документация и сообщения переведены на русский**.
>
> Апстрим написан на японском и английском; оригинальные тексты сохранены в файлах с суффиксами `.en` и `.ja`.

## Возможности

Промпт писать не нужно: скилл сам собирает его из контекста проекта и генерирует изображения через ChatGPT Images 2.0 прямо в сессии Claude Code.

- **Без ключа API** — работает по подписке ChatGPT. Ключ нужен только для 4K и строго точного размера
- **Текст на любых языках** — модель уверенно рисует кириллицу, японский (иероглифы, кана, вертикальный набор), корейский и китайский
- **Редактирование по референсу** — через `--reference` можно собирать композиции и править готовые изображения
- **Метаданные рядом с картинкой** — промпт и параметры каждой генерации сохраняются в JSON

## Примеры

Работы, сделанные этим скиллом. Полная галерея — в [`docs/gallery.md`](docs/gallery.md).

<table>
<tr>
  <td align="center" width="33%"><img src="assets/capability-survey/categories/01_photorealistic_portrait_woman.png" width="260" alt="Фотореалистичный портрет"></td>
  <td align="center" width="33%"><img src="assets/capability-survey/categories/19_urban_tokyo_rainy_night_v3.png" width="260" alt="Перекрёсток Сибуя в Токио дождливой ночью"></td>
  <td align="center" width="33%"><a href="docs/gallery.md"><img src="assets/capability-survey/categories/18_nature_volcanic_coast_dawn.png" width="260" alt="Открыть полную галерею"></a></td>
</tr>
<tr>
  <td align="center" width="33%"><img src="assets/capability-survey/categories/24_line_drawing_fashion_sketch.png" width="260" alt="Модный скетч линией"></td>
  <td align="center" width="33%"><img src="assets/capability-survey/categories/14_japanese_poster_vertical_tategaki.png" width="260" alt="Японский плакат с вертикальным набором"></td>
  <td align="center" width="33%"><img src="assets/capability-survey/categories/06_ui_mockup_settings_japanese.png" width="260" alt="Макет экрана настроек iOS"></td>
</tr>
</table>

## Что потребуется

Скилл работает двумя способами, требования у них разные. Переключаться между ними можно параметром `--backend`. Для 4K и точного контроля размера обязателен вариант Б, поэтому удобнее держать оба сразу.

**Вариант А: подписка ChatGPT + Codex CLI**
- Python 3.10+
- подписка ChatGPT (Plus или выше)
- установленный [Codex CLI](https://github.com/openai/codex) со входом через `codex login`

**Вариант Б: ключ OpenAI API**
- Python 3.10+
- ключ OpenAI API
- пройденная верификация организации (Organization Verification)

## Установка

### 1. Клонирование репозитория

Клонировать можно куда угодно.

```bash
cd /path/to/projects
git clone https://github.com/Repkine/ccskill-gptimage.git
```

### 2. Подготовка генерации

Нужно сделать ChatGPT Images 2.0 доступным. Выберите подходящий вариант — рекомендуется А.

#### Вариант А: подписка ChatGPT + Codex CLI

Если вы уже пользуетесь Codex CLI по подписке, шаг можно пропустить.

```bash
# Установка Codex CLI (Homebrew)
brew install codex
# Вход под аккаунтом ChatGPT
codex login
```

На Windows Codex CLI ставится через npm:

```bash
npm install -g @openai/codex
```

#### Вариант Б: ключ OpenAI API

На [OpenAI Platform](https://platform.openai.com/) нужно сделать две вещи:

- (а) выпустить ключ в разделе [API keys](https://platform.openai.com/api-keys);
- (б) пройти верификацию: [Organization Settings](https://platform.openai.com/settings/organization/general) → General → Verification.

Затем записать ключ в файл `.env`:

```bash
cp .env.example .env
```

И добавить туда ключ из пункта (а):

```
OPENAI_API_KEY=sk-...
```

### 3. Запуск установщика

Перейдите в каталог, куда клонировали репозиторий, и выполните:

```bash
cd /path/to/ccskill-gptimage
./install.sh
```

Установщик делает всё сам:

- создаёт venv и ставит зависимости;
- кладёт команду `ccskill-gptimage` в `~/.local/bin` и подсказывает, что дописать в PATH, если его там нет;
- регистрирует скилл на уровне пользователя (`~/.claude/skills/ccskill-gptimage`), после чего он доступен во **всех** проектах Claude Code без отдельной настройки;
- показывает, какие backend сейчас доступны — Codex CLI или ключ API.

> `install.sh` — bash-скрипт и рассчитан на macOS и Linux. На Windows он работает из Git Bash или WSL; при запуске из PowerShell создайте venv вручную (`python -m venv venv`, затем `pip install -r requirements.txt`) и вызывайте `generate_image.py` напрямую.

## Использование

В любом проекте Claude Code достаточно попросить сгенерировать изображение через ChatGPT Images 2.0 — например, «сделай через gptimage…» — или написать в промпте `/ccskill-gptimage`. Описывать задачу можно **на любом языке**: Claude Code сам соберёт оптимальный промпт по контексту и подберёт размер, качество и backend.

- Генерация по контексту проекта:
  ```
  Посмотри вёрстку лендинга @lp.html и предложи три варианта главной картинки под его содержание
  ```
- Генерация на основе готового изображения:
  ```
  На основе фото товара @product.jpg сделай версии с погодой «пасмурно» и временем суток «сумерки»
  ```

### Полезное

- При первом запуске Claude Code может спросить разрешение на выполнение `ccskill-gptimage`. Чтобы не спрашивал, добавьте `Bash(ccskill-gptimage:*)` в `permissions.allow` файла `~/.claude/settings.json`.

## Обновление

Выполните `git pull` в каталоге клона. И регистрация скилла, и команда — это symlink на клон, поэтому обновление подхватывается само:

```bash
cd /path/to/ccskill-gptimage
git pull
```

## Удаление

```bash
ccskill-gptimage uninstall
```

Команда убирает symlink-и (`~/.local/bin/ccskill-gptimage` и `~/.claude/skills/ccskill-gptimage`), сам склонированный репозиторий остаётся на месте.

## Работа из командной строки

Скилл можно использовать и как обычную команду генерации, из любого каталога:

```bash
ccskill-gptimage generate "закат на побережье"
```

### Параметры

| Параметр | Описание | По умолчанию |
|---|---|---|
| `--size` | Размер: `auto` или произвольный `WxH` (ограничения ниже). Готовые варианты: `1024x1024`, `1024x1536`, `1536x1024`; максимум `3840x2160` (4K) | `1024x1024` |
| `--quality` | Качество: `auto`, `low`, `medium`, `high` | `auto` |
| `--background` | Фон: `auto`, `opaque`. Значение `transparent` gpt-image-2 не поддерживает — нужна `gpt-image-1.5` | `auto` |
| `--output-format` | Формат: `png`, `jpeg`, `webp` | `png` |
| `--output-compression` | Сжатие для jpeg и webp, 0–100 | нет |
| `--output` | Каталог вывода | `./generated_images` |
| `--reference` | Референсное изображение, можно указывать несколько раз | нет |
| `--mask` | Маска: прозрачная область — редактируемая | нет |
| `--input-fidelity` | Для gpt-image-2 не нужен, точность всегда максимальная. Имеет смысл только для `gpt-image-1.5` | нет |
| `--moderation` | Модерация: `auto`, `low` | `auto` |
| `--backend` | Backend генерации: `auto`, `codex`, `api`. При `auto` сначала пробуется Codex, при неудаче — откат на API | `auto` |
| `--codex-resume` | ID сессии Codex для продолжения: серия слайдов наследует стиль. Только с `--backend codex`. Есть только в этом форке | нет |

Подробнее о каждом параметре — в [руководстве по параметрам](docs/options.md).

### Примеры

```bash
# Базовый вызов
ccskill-gptimage generate "A minimalist fox logo, flat vector, navy and gold"

# Плакат с текстом
ccskill-gptimage generate 'Минималистичный плакат с крупным заголовком "ГЛАВНОЕ" рубленым шрифтом, тёмно-синий фон' --size 1024x1536 --quality high

# Редактирование по референсу — замена фона
ccskill-gptimage generate "Помести тот же логотип лисы на глубокий тёмно-синий фон с мелкими золотыми искрами. Позу и пропорции лисы с референса сохрани." --reference ./logo.png --quality medium

# Композиция из нескольких референсов
ccskill-gptimage generate "Photorealistic gift basket on white" --reference ./a.png --reference ./b.png --reference ./c.png

# Редактирование по маске (требует --backend api)
ccskill-gptimage generate "A sunlit indoor lounge with a pool" --reference ./lounge.png --mask ./mask.png --backend api

# Серия слайдов в одном стиле (только в этом форке)
ccskill-gptimage generate "Слайд 1: обложка" --backend codex
# из вывода берём строку [Session] <id> и передаём её дальше
ccskill-gptimage generate "Слайд 2: состав" --backend codex --codex-resume <id>
```

### Файлы на выходе

Рядом с каждым изображением сохраняется **JSON с метаданными** (`{имя}.{расширение}.json`) — чтобы можно было воспроизвести и доработать результат:

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

## Просмотр созданных изображений

Каждое изображение копируется в общее хранилище (`~/.ccskill-gptimage/gallery`), поэтому оказывается рядом с результатами `ccskill-nanobanana` и `ccskill-omniflash`. Для просмотра поставьте [ccskill-gallery](https://github.com/feedtailor/ccskill-gallery) и выполните:

```bash
ccskill-gptimage browse
```

Без установленного ccskill-gallery команда просто напечатает, где лежат изображения.

## Характеристики

- **Модель**: `gpt-image-2` (снапшот `gpt-image-2-2026-04-21`)
- **Вход**: текст и изображения
- **Выход**: только изображение (`b64_json`, ссылка не возвращается)
- **Максимальное разрешение**: до 4K, длинная сторона не больше 3840px. `--size` принимает произвольный `WxH`, который проверяется по ограничениям модели: каждая сторона кратна 16, длинная сторона до 3840px, соотношение сторон до 3:1, общее число пикселей от 655,360 до 8,294,400. `--backend api` соблюдает размер точно (например, `3840x2160`), `--backend codex` недетерминирован и размер не гарантирует
- **Эндпоинты**: `/v1/images/generations`, `/v1/images/edits`
- **Имя файла**: метка времени, например `20260423_153045.png`
- **Модерация**: `auto` по умолчанию или `low`

## Время генерации, ориентировочно

Медиана трёх запусков для каждой пары backend × качество при `1024x1024` и одном и том же промпте, в скобках разброс. Значения приблизительные и зависят от сети и нагрузки.

| Качество | api | codex |
|---|---|---|
| low | ~16 с (15–18) | ~30 с (22–52) |
| medium | ~46 с (45–49) | ~25 с (23–52) |
| high | ~138 с (137–140) | ~24 с (22–90) |

- **У api время растёт вместе с качеством** — на `high` уходит больше двух минут, зато результат стабилен.
- **codex укладывается в 20–90 секунд с большим разбросом и от качества почти не зависит.** Качество для него — это недетерминированная подсказка, проходящая через слой агента, поэтому запрос `high` не гарантирует такую же тяжёлую генерацию, как `high` у api: если codex отработал быстро, качество, скорее всего, применилось не полностью. **Когда нужен строгий контроль качества и размера или воспроизводимость, используйте api.**
- Большие размеры вроде 4K занимают пропорционально больше времени.

## Если что-то не работает

Быстрая диагностика окружения и backend:

```bash
ccskill-gptimage doctor
```

Команда никогда не читает содержимое секретных файлов — ни `.env`, ни учётные данные Codex. Она проверяет только наличие файлов и переменных, а окончательный ответ даёт реальный запуск генерации.

| Симптом | Что делать |
|---|---|
| `403 Forbidden` | Не пройдена верификация организации OpenAI — завершите её в Organization Settings |
| Непонятно, в чём дело | Запустите `ccskill-gptimage doctor` |
| На Windows backend codex не работает | В этом форке уже починено. Если вы взяли код из апстрима, перенесите сюда коммит `fix: make the codex backend work on Windows` |

## Лицензия

MIT. Copyright (c) 2026 feedtailor Inc. — см. [LICENSE](LICENSE).
