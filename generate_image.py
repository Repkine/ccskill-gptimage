#!/usr/bin/env python3
"""ccskill-gptimage — скрипт генерации изображений

Генерирует и редактирует изображения через OpenAI gpt-image-2 (ChatGPT Images 2.0).

Примеры использования:
    python generate_image.py "a minimalist fox logo, flat vector, navy and gold"
    python generate_image.py "замени фон на закат" --reference original.png --input-fidelity high
    python generate_image.py "gift basket on white" --background transparent --output-format png

Переменные окружения:
    OPENAI_API_KEY: ключ OpenAI API (можно задать в .env)
"""

import argparse
import base64
import contextlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

_script_dir = Path(__file__).parent
load_dotenv(_script_dir / ".env")

DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "auto"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_OUTPUT_DIR = "./generated_images"
DEFAULT_BACKGROUND = "auto"
DEFAULT_MODERATION = "auto"
DEFAULT_BACKEND = "auto"

OUTPUT_FORMAT_TO_EXT = {
    "png": ".png",
    "jpeg": ".jpg",
    "webp": ".webp",
}

OUTPUT_FORMAT_TO_MIME = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

# Галерея — общее хранилище результатов всех скиллов ccskill
# (issue #024 / ccskill-gallery store-spec v1.0)
GALLERY_DIR_ENV = "CCSKILL_GPTIMAGE_GALLERY_DIR"
DEFAULT_GALLERY_DIR = Path.home() / ".ccskill-gptimage" / "gallery"

SIZE_CHOICES = ["auto", "1024x1024", "1024x1536", "1536x1024"]  # частые варианты, не жёсткий enum

# Ограничения на размер у gpt-image-2 (источник: спецификация gpt-image-2, проверено в issue #018)
SIZE_MULTIPLE = 16
SIZE_MAX_SIDE = 3840
SIZE_MAX_ASPECT = 3.0
SIZE_MIN_PIXELS = 655_360
SIZE_MAX_PIXELS = 8_294_400

QUALITY_CHOICES = ["auto", "low", "medium", "high"]
BACKGROUND_CHOICES = ["auto", "transparent", "opaque"]
OUTPUT_FORMAT_CHOICES = ["png", "jpeg", "webp"]
MODERATION_CHOICES = ["auto", "low"]
INPUT_FIDELITY_CHOICES = ["high", "low"]
BACKEND_CHOICES = ["auto", "codex", "api"]

CODEX_HOME = Path.home() / ".codex"
CODEX_AUTH_FILE = CODEX_HOME / "auth.json"
CODEX_GENERATED_DIR = CODEX_HOME / "generated_images"
CODEX_SESSIONS_DIR = CODEX_HOME / "sessions"
CODEX_SUBPROCESS_TIMEOUT = 300
# Модель агента Codex для этого вызова, мимо ~/.codex/config.toml. Конфиг общий
# с Codex Desktop, и 26.10.2026 приложение (0.164) прописало туда gpt-6.1-sol,
# которую codex-cli 0.146.1 с ChatGPT-аккаунтом не принимает: 400 model_not_found,
# и exec завершается без единого ответа. Переменная задаёт `-m` только нашему
# вызову, настройки приложения остаются как есть.
CODEX_MODEL_ENV = "CCSKILL_GPTIMAGE_CODEX_MODEL"

# Пропорция на бэкенде codex: у встроенного инструмента image_gen нет параметра
# размера (схема — только prompt / num_last_images_to_include /
# referenced_image_paths), поэтому запрошенный --size доезжает до модели просто
# текстом и соблюдается не всегда. Замер 7 августа 2026: из 19 генераций 17 дали
# ровно 3:4, две ушли в 1,563. Площадь при этом постоянна (~1,57 Мпикс) —
# сервер держит бюджет пикселей и выбирает пропорцию из своего набора.
# Отсюда стратегия: проверить пропорцию по факту и перегенерировать при промахе.
CODEX_ASPECT_TOLERANCE = 0.01  # относительное отклонение H/W, при котором кадр считается верным
DEFAULT_ASPECT_RETRIES = 2


def validate_size(size: str) -> tuple[int, int]:
    """Проверяет строку `WxH` по ограничениям gpt-image-2 и возвращает (ширина, высота).

    При нарушении бросает ValueError с конкретным описанием проблемы.
    Значение `auto` обрабатывается вызывающей стороной и сюда не передаётся.

    Ограничения (источник: спецификация gpt-image-2, проверено в issue #018):
      1. каждая сторона кратна 16
      2. максимальная сторона <= 3840px
      3. соотношение сторон (длинная/короткая) <= 3:1
      4. общее число пикселей 655,360 <= W*H <= 8,294,400
    """
    m = re.fullmatch(r"(\d+)x(\d+)", size.strip())
    if not m:
        raise ValueError(
            f"--size задаётся как 'WxH' (например 1024x1024) или 'auto': {size!r} — неверный формат"
        )
    w, h = int(m.group(1)), int(m.group(2))
    if w % SIZE_MULTIPLE != 0 or h % SIZE_MULTIPLE != 0:
        bad = w if w % SIZE_MULTIPLE != 0 else h
        raise ValueError(
            f"каждая сторона должна быть кратна {SIZE_MULTIPLE}: {bad} не кратно {SIZE_MULTIPLE} (указано: {w}x{h})"
        )
    if max(w, h) > SIZE_MAX_SIDE:
        raise ValueError(
            f"максимальная сторона — не больше {SIZE_MAX_SIDE}px: {max(w, h)} превышает предел (указано: {w}x{h})"
        )
    long_side, short_side = max(w, h), min(w, h)
    aspect = long_side / short_side
    if aspect > SIZE_MAX_ASPECT:
        raise ValueError(
            f"соотношение сторон — не больше 3:1: у {w}x{h} оно {aspect:.2f}:1"
        )
    total = w * h
    if total < SIZE_MIN_PIXELS:
        raise ValueError(
            f"общее число пикселей — не меньше {SIZE_MIN_PIXELS:,}: {w}x{h} = {total:,} ниже нижней границы"
        )
    if total > SIZE_MAX_PIXELS:
        raise ValueError(
            f"общее число пикселей — не больше {SIZE_MAX_PIXELS:,}: {w}x{h} = {total:,} превышает верхнюю границу"
        )
    return (w, h)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Генерация и редактирование изображений через OpenAI gpt-image-2"
    )
    parser.add_argument("prompt", type=str, help="промпт для генерации изображения")
    parser.add_argument(
        "--size",
        type=str,
        default=DEFAULT_SIZE,
        help=(
            f"размер вывода: 'auto' или 'WxH' (например {DEFAULT_SIZE}, 3840x2160)."
            f" Ограничения: каждая сторона кратна {SIZE_MULTIPLE} / максимальная сторона {SIZE_MAX_SIDE}px /"
            f" соотношение сторон до 3:1 / всего пикселей {SIZE_MIN_PIXELS:,}—{SIZE_MAX_PIXELS:,}."
            " Частые варианты: " + " ".join(s for s in SIZE_CHOICES if s != "auto")
        ),
    )
    parser.add_argument(
        "--quality",
        type=str,
        default=DEFAULT_QUALITY,
        choices=QUALITY_CHOICES,
        help=f"качество (по умолчанию: {DEFAULT_QUALITY})",
    )
    parser.add_argument(
        "--background",
        type=str,
        default=DEFAULT_BACKGROUND,
        choices=BACKGROUND_CHOICES,
        help=(
            f"фон (по умолчанию: {DEFAULT_BACKGROUND})."
            " Внимание: gpt-image-2 не поддерживает transparent (вернёт 400)."
            " Если нужен прозрачный PNG, используйте ccskill-nanobanana."
        ),
    )
    parser.add_argument(
        "--output-format",
        dest="output_format",
        type=str,
        default=DEFAULT_OUTPUT_FORMAT,
        choices=OUTPUT_FORMAT_CHOICES,
        help=f"формат вывода (по умолчанию: {DEFAULT_OUTPUT_FORMAT})",
    )
    parser.add_argument(
        "--output-compression",
        dest="output_compression",
        type=int,
        default=None,
        help="степень сжатия (для jpeg/webp, 0-100)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"каталог вывода (по умолчанию: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--reference",
        type=str,
        action="append",
        default=[],
        help="путь к референсному изображению (можно указывать несколько). Переключает вызов на edits API",
    )
    parser.add_argument(
        "--mask",
        type=str,
        default=None,
        help="маска (прозрачная область — редактируемая; требует --reference)",
    )
    parser.add_argument(
        "--input-fidelity",
        dest="input_fidelity",
        type=str,
        default=None,
        choices=INPUT_FIDELITY_CHOICES,
        help=(
            "точность сохранения референса."
            " Внимание: gpt-image-2 **всегда автоматически** обрабатывает входные изображения"
            " с максимальной точностью, поэтому параметр не нужен (при указании вернётся 400)."
            " Значения high/low имеют смысл только для старой модели `gpt-image-1.5` через `--model`."
        ),
    )
    parser.add_argument(
        "--moderation",
        type=str,
        default=DEFAULT_MODERATION,
        choices=MODERATION_CHOICES,
        help=f"уровень модерации (по умолчанию: {DEFAULT_MODERATION})",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"ID модели (по умолчанию: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--output-name",
        dest="output_name",
        type=str,
        default=None,
        help="имя файла без расширения (расширение берётся из output_format). По умолчанию — метка времени",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default=DEFAULT_BACKEND,
        choices=BACKEND_CHOICES,
        help=(
            f"backend генерации (по умолчанию: {DEFAULT_BACKEND})."
            " auto = codex, если есть Codex CLI с авторизацией по подписке ChatGPT;"
            " при неудаче — откат на api, если задан OPENAI_API_KEY."
        ),
    )
    parser.add_argument(
        "--codex-resume",
        dest="codex_resume",
        type=str,
        default=None,
        help=(
            "продолжить существующую сессию Codex через `codex exec resume` по её ID."
            " Ранее сгенерированное изображение остаётся в том же треде, поэтому серия"
            " наследует стиль. ID берётся из строки `[Session] <id>`, которую печатает"
            " каждый запуск. Работает только при backend=codex"
        ),
    )
    parser.add_argument(
        "--aspect-retries",
        dest="aspect_retries",
        type=int,
        default=DEFAULT_ASPECT_RETRIES,
        help=(
            f"сколько раз перегенерировать при промахе по пропорции (по умолчанию:"
            f" {DEFAULT_ASPECT_RETRIES}). У встроенного инструмента image_gen нет параметра"
            " размера, поэтому --size доезжает до модели текстом и соблюдается не всегда."
            " Скрипт сверяет пропорцию готового кадра с запрошенной и при расхождении"
            f" больше {CODEX_ASPECT_TOLERANCE:.0%} генерирует заново. 0 отключает проверку."
            " Только для backend=codex и при --size, отличном от auto"
        ),
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Backend detection / dispatch (issue #017: Codex CLI integration)
# ---------------------------------------------------------------------------


def _codex_subscription_available() -> bool:
    """Проверяет, что Codex CLI есть в PATH и выполнен вход по подписке ChatGPT.

    Признак входа — наличие `tokens.access_token` в `~/.codex/auth.json`.
    Поле `auth_mode` осталось от старых версий; в текущих есть только структура tokens.
    """
    if shutil.which("codex") is None:
        return False
    if not CODEX_AUTH_FILE.exists():
        return False
    try:
        data = json.loads(CODEX_AUTH_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    tokens = data.get("tokens") or {}
    return bool(tokens.get("access_token"))


def _resolve_backend(requested: str) -> str:
    """Разрешает `auto` в конкретный backend. Явно указанный возвращается как есть.

    Для auto: доступен codex — берём codex, иначе api. Даже без ключа возвращаем api,
    чтобы ошибку выдал сам OpenAI() на следующем шаге.
    """
    if requested != "auto":
        return requested
    if _codex_subscription_available():
        return "codex"
    return "api"


def _find_latest_codex_image(since_mtime: float) -> Path | None:
    """Возвращает самый свежий PNG, созданный позже `since_mtime` (путь старого Codex).

    Codex CLI примерно до апреля 2026 не принимал указание пути вывода и писал файл
    в `~/.codex/generated_images/<session-id>/ig_*.png`. Новый Codex (codex exec) файл
    не создаёт и возвращает картинку inline-base64 в логе сессии, поэтому при None
    вызывающая сторона откатывается на `_recover_codex_image_from_session()`.
    """
    if not CODEX_GENERATED_DIR.exists():
        return None
    latest_mtime = -1.0
    latest_path: Path | None = None
    # codex-cli 0.146.x пишет файл как `exec-<call-id>.png`, а не `ig_*.png`,
    # поэтому маска расширена до любых PNG в каталоге сессий
    for p in CODEX_GENERATED_DIR.rglob("*.png"):
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if m > since_mtime and m > latest_mtime:
            latest_mtime = m
            latest_path = p
    return latest_path


def _extract_codex_session_id(stdout: str) -> str | None:
    """Достаёт session id из шапки вывода codex exec (`session id: <uuid>`)."""
    if not stdout:
        return None
    m = re.search(r"session id:\s*([0-9a-fA-F][0-9a-fA-F-]{7,})", stdout)
    return m.group(1) if m else None


def _session_id_from_log_path(log_path: Path) -> str | None:
    """Достаёт session id из имени файла вида `rollout-<ts>-<uuid>.jsonl`.

    `codex exec` в codex-cli 0.146.1 не печатает шапку `session id:` в stdout
    (замерено 7 августа 2026). Фактически это единственный способ получить ID
    для продолжения, поэтому используется как запасной путь, когда
    `_extract_codex_session_id()` вернул пусто.
    """
    m = re.search(
        r"rollout-\d{4}-\d{2}-\d{2}T[\d-]+-([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})",
        log_path.name,
    )
    return m.group(1) if m else None


def _find_codex_session_log(session_id: str | None, since_mtime: float) -> Path | None:
    """Находит лог сессии Codex (`rollout-*.jsonl`), соответствующий этому запуску.

    Если session_id известен, приоритет у файла с ним в имени. Если нет — берём самый
    свежий jsonl, изменённый позже since_mtime (в реальной работе это надёжно, потому что
    лог пишется прямо во время выполнения codex exec).
    """
    if not CODEX_SESSIONS_DIR.exists():
        return None
    if session_id:
        matches = list(CODEX_SESSIONS_DIR.rglob(f"*{session_id}*.jsonl"))
        if matches:
            return max(matches, key=lambda p: p.stat().st_mtime)
    latest_mtime = since_mtime
    latest_path: Path | None = None
    for p in CODEX_SESSIONS_DIR.rglob("*.jsonl"):
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if m > latest_mtime:
            latest_mtime = m
            latest_path = p
    return latest_path


def _recover_codex_image_from_session(log_path: Path) -> bytes | None:
    """Забирает сгенерированную картинку из лога сессии Codex.

    Новый Codex (примерно с июня 2026) при `codex exec` не создаёт файл, а возвращает
    изображение inline-base64 в поле `image_generation_call.result` лога сессии.
    Приоритет у записи со `status == "completed"`; если её нет, берётся последний
    встреченный result — это защита от промежуточных partial_images.
    Формат `data:` URI тоже поддерживается.
    """
    try:
        # Windows читает в локальной кодовой странице и падает на первом же
        # не-ASCII байте лога; errors="replace" страхует от битых хвостов
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    last_b64: str | None = None
    completed_b64: str | None = None
    for line in text.splitlines():
        if "image_generation_call" not in line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            payload = obj
        if payload.get("type") != "image_generation_call":
            continue
        result = payload.get("result")
        if isinstance(result, str) and result:
            last_b64 = result
            if payload.get("status") == "completed":
                completed_b64 = result
    b64 = completed_b64 or last_b64
    if not b64:
        return None
    if b64.lstrip().startswith("data:") and "," in b64:
        b64 = b64.split(",", 1)[1]
    try:
        return base64.b64decode(b64)
    except (ValueError, TypeError):
        return None


def _build_codex_prompt(
    prompt: str,
    *,
    size: str,
    quality: str,
    output_format: str,
    background: str,
    reference_count: int,
    resume: bool = False,
    aspect_hint: str | None = None,
) -> str:
    """Собирает инструкцию для агента Codex.

    Важно: обязательно указать «используй image_gen напрямую, не пиши скрипты для API».
    Без этого Codex идёт в API через curl/Python, и генерация уходит в поштучную
    оплату вместо квоты подписки (наблюдение из note.com/mauekusa).
    """
    lines = [
        "Вызови OpenAI gpt-image-2 через встроенный инструмент image_gen.",
        "Важно: не пиши никаких ключей API и никаких скриптов (curl / python / node) — "
        "используй встроенный инструмент image_gen напрямую.",
        f"size: {size}",
        f"quality: {quality}",
        f"output format: {output_format}",
    ]
    if background and background != "auto":
        lines.append(f"background: {background}")
    if reference_count > 0:
        lines.append(
            f"Сгенерируй в режиме редактирования на основе приложенных референсов ({reference_count} шт.)."
            " Ключевые элементы исходника — лицо человека, композицию, фон — сохрани максимально точно."
        )
    if resume:
        # Наследовать нужно только стиль: если скопируется и композиция, серии не выйдет.
        # Формулировка «в том же духе» обычно приводит к перерисовке предыдущего слайда,
        # поэтому стиль и содержание разводятся явно.
        lines.append(
            "Сохрани тот же визуальный стиль, что и у изображения, сгенерированного"
            " в этом треде последним: палитру, градиенты, гарнитуру, фактуру декора,"
            " обработку рамки. Но композицию, объект и текст не копируй —"
            " нарисуй заново по промпту ниже."
        )
    if aspect_hint:
        lines.append(aspect_hint)
    lines.append("")
    lines.append("Промпт:")
    lines.append(prompt)
    return "\n".join(lines)


def _generate_via_codex(
    prompt: str,
    *,
    size: str,
    quality: str,
    output_format: str,
    background: str,
    output_path: Path,
    reference_images: list[str] | None,
    resume_session_id: str | None = None,
    aspect_hint: str | None = None,
) -> tuple[Path, str | None, str | None] | None:
    """Генерирует картинку через Codex CLI.

    При успехе возвращает (output_path, revised_prompt, session_id), при неудаче None.
    Неудача — это ошибка subprocess, отсутствие вывода image_gen, сбой копирования и т. п.
    Вызывающая сторона по None понимает, что в режиме auto пора откатываться на API.
    """
    codex_prompt = _build_codex_prompt(
        prompt,
        size=size,
        quality=quality,
        output_format=output_format,
        background=background,
        reference_count=len(reference_images or []),
        resume=bool(resume_session_id),
        aspect_hint=aspect_hint,
    )
    # Windows: npm ставит шим codex.CMD, а CreateProcess не подставляет
    # расширения из PATHEXT — голое "codex" даёт FileNotFoundError.
    # shutil.which находит .CMD корректно, поэтому резолвим путь заранее.
    codex_bin = shutil.which("codex") or "codex"
    # Windows: многострочный промпт, переданный позиционным аргументом,
    # обрезается на первом переносе строки — вызов идёт через batch-шим
    # codex.CMD, а cmd.exe трактует перенос как конец команды. В логе сессии
    # это видно как user_message из одной первой строки. `-` переключает
    # codex exec на чтение промпта из stdin, где переносы безопасны.
    if resume_session_id:
        # `codex exec resume [SESSION_ID] [PROMPT]` — у подкоманды resume нет
        # флага --sandbox (проверено на codex-cli 0.146.1), политика песочницы
        # наследуется из возобновляемой сессии. `--last` сознательно не
        # поддерживаем: первый позиционный аргумент — SESSION_ID, и `-` при
        # `--last` может быть съеден как id вместо промпта.
        cmd: list[str] = [
            codex_bin,
            "exec",
            "resume",
            "--skip-git-repo-check",
            resume_session_id,
            "-",
        ]
    else:
        cmd = [
            codex_bin,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "-",
        ]
    codex_model = os.environ.get(CODEX_MODEL_ENV)
    if codex_model:
        # `-m` есть и у `exec`, и у `exec resume`; ставим среди флагов, до
        # позиционных SESSION_ID и `-`, чтобы их порядок не менялся
        at = cmd.index("--skip-git-repo-check") + 1
        cmd[at:at] = ["-m", codex_model]
    # `-i` — variadic-флаг, поэтому его место строго после промпта:
    # в обратном порядке он съест и сам промпт, приняв его за путь к картинке
    for ref in reference_images or []:
        cmd.extend(["-i", ref])

    started_at = time.time()
    try:
        proc = subprocess.run(
            cmd,
            input=codex_prompt,
            capture_output=True,
            text=True,
            # без явной кодировки Windows возьмёт локальную кодовую страницу
            # и покалечит кириллицу в промпте
            encoding="utf-8",
            timeout=CODEX_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print("[Error] Codex CLI не ответил за отведённое время")
        return None
    except FileNotFoundError:
        print("[Error] команда codex не найдена в PATH")
        return None

    if proc.returncode != 0:
        print(f"[Error] Codex CLI exit code {proc.returncode}: {proc.stderr.strip()[:200]}")
        return None

    revised = _extract_revised_prompt_from_codex_log(proc.stdout)

    # ID сессии нужен независимо от того, как забрали картинку: вызывающая сторона
    # передаёт его в --codex-resume для следующего слайда, чтобы серия держала стиль.
    # В stdout версии 0.146.1 шапки нет, поэтому фактически достаём его из имени файла
    # лога. Если и там не вышло — при resume просто продолжаем с переданным ID.
    session_id = _extract_codex_session_id(proc.stdout)
    log_path = _find_codex_session_log(session_id, started_at)
    if session_id is None and log_path is not None:
        session_id = _session_id_from_log_path(log_path)
    if session_id is None:
        session_id = resume_session_id

    # Старый Codex: картинка попадает в файл ~/.codex/generated_images/<session>/ig_*.png
    image = _find_latest_codex_image(started_at)
    if image is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image, output_path)
        return (output_path, revised, session_id)

    # Новый Codex (примерно с июня 2026): codex exec не создаёт файл, а возвращает
    # картинку inline-base64 в логе сессии. Забираем оттуда, декодируем и сохраняем.
    if log_path is not None:
        data = _recover_codex_image_from_session(log_path)
        if data:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(data)
            return (output_path, revised, session_id)

    print("[Error] изображение, сгенерированное через Codex, не найдено")
    return None


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    """Читает ширину и высоту из заголовка IHDR у PNG.

    Своя реализация вместо Pillow: в зависимостях проекта только openai и dotenv,
    тянуть ради двух чисел целую библиотеку не нужно. Не-PNG и битые файлы дают
    None — вызывающая сторона тогда просто пропускает проверку пропорции.
    """
    try:
        head = path.read_bytes()[:24]
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    width = int.from_bytes(head[16:20], "big")
    height = int.from_bytes(head[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    return width, height


def _aspect_matches(path: Path, size: str) -> tuple[bool, str | None]:
    """Проверяет, попала ли готовая картинка в пропорцию запрошенного --size.

    Возвращает (совпало, "WxH" по факту). Если размер прочитать не удалось или
    --size задан как auto, считаем, что придираться не к чему.
    """
    if size == "auto":
        return True, None
    try:
        want_w, want_h = validate_size(size)
    except ValueError:
        return True, None
    dims = _png_dimensions(path)
    if dims is None:
        return True, None
    got_w, got_h = dims
    want_ratio = want_h / want_w
    got_ratio = got_h / got_w
    ok = abs(got_ratio - want_ratio) / want_ratio <= CODEX_ASPECT_TOLERANCE
    return ok, f"{got_w}x{got_h}"


def _aspect_retry_hint(size: str, got: str | None) -> str:
    """Подсказка агенту на повторной попытке: чем именно не устроил прошлый кадр."""
    want_w, want_h = validate_size(size)
    divisor = math.gcd(want_w, want_h)
    ratio = f"{want_w // divisor}:{want_h // divisor}"
    return (
        f"ВАЖНО: предыдущая попытка вернула кадр {got or 'неверной формы'},"
        f" а нужна пропорция ровно {ratio} (ширина к высоте)."
        f" Сгенерируй заново именно в этой пропорции — она важнее любых других соображений о кадре."
    )


def _extract_revised_prompt_from_codex_log(stdout: str) -> str | None:
    """Достаёт финальный ответ агента (аналог revised_prompt) из хвоста лога Codex.

    Сейчас это делается по возможности: если в конце лога есть строка `codex`,
    возвращается всё, что идёт после неё. Неудача не критична, поэтому None допустим.
    """
    if not stdout:
        return None
    lines = stdout.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "codex":
            tail = "\n".join(lines[i + 1 :]).strip()
            return tail or None
    return None


def get_output_path(
    output_dir: str,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    name: str | None = None,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ext = OUTPUT_FORMAT_TO_EXT.get(output_format, ".png")
    stem = name if name else datetime.now().strftime("%Y%m%d_%H%M%S")
    return out / f"{stem}{ext}"


def _build_generate_kwargs(
    *,
    model: str,
    prompt: str,
    size: str,
    quality: str,
    background: str,
    output_format: str,
    output_compression: int | None,
    moderation: str,
) -> dict:
    """Собирает параметры для Image API /generations. Значения auto не передаются."""
    kwargs: dict = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "output_format": output_format,
        "n": 1,
    }
    if background and background != "auto":
        kwargs["background"] = background
    if moderation and moderation != "auto":
        kwargs["moderation"] = moderation
    if output_compression is not None and output_format in ("jpeg", "webp"):
        kwargs["output_compression"] = output_compression
    return kwargs


def _call_image_generations(client: OpenAI, **kwargs):
    """Путь через Image API: генерация изображения по тексту"""
    return client.images.generate(**kwargs)


def _call_image_edits(client: OpenAI, **kwargs):
    """Путь через Image API: редактирование с референсом и/или маской"""
    return client.images.edit(**kwargs)


def _save_metadata(image_path: Path, meta: dict) -> Path:
    meta_path = image_path.with_suffix(image_path.suffix + ".json")
    # При ensure_ascii=False и без явной кодировки Windows пишет файл в локальной
    # кодовой странице (для ru-RU это cp1251). Сайдкар с русским промптом после этого
    # не читается как UTF-8, поэтому кодировку указываем явно — как и при записи галереи
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta_path


def get_gallery_dir() -> Path:
    """Определяет путь к галерее (меняется переменной окружения GALLERY_DIR_ENV).

    Соответствует ccskill-gallery store-spec v1.0: по умолчанию ~/.ccskill-gptimage/gallery.
    """
    env = os.environ.get(GALLERY_DIR_ENV)
    if env:
        return Path(env).expanduser()
    return DEFAULT_GALLERY_DIR


def load_index(gallery_dir: Path) -> dict:
    """Читает index.json. Если файла нет или он повреждён — пересобирает по сайдкарам."""
    index_path = gallery_dir / "index.json"
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(index, dict) and isinstance(index.get("entries"), list):
                return index
        except (json.JSONDecodeError, OSError):
            print("[Warning] index.json повреждён, пересобираю заново")

    entries = []
    images_dir = gallery_dir / "images"
    if images_dir.exists():
        for sidecar in sorted(images_dir.glob("*.json")):
            image_name = sidecar.name[: -len(".json")]
            if not (images_dir / image_name).exists():
                continue
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            entries.append({**meta, "file": f"images/{image_name}"})
        entries.sort(key=lambda e: e.get("timestamp", ""))
    return {"entries": entries}


def store_in_gallery(image_path: Path, metadata: dict) -> Path:
    """Копирует изображение и метаданные в галерею и дописывает index.json (store-spec v1.0)."""
    gallery_dir = get_gallery_dir()
    images_dir = gallery_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Существующий индекс читаем до копирования: если прочитать после,
    # при пересборке запись посчитается дважды
    index = load_index(gallery_dir)

    # При совпадении имён добавляем числовой суффикс
    dest = images_dir / image_path.name
    counter = 1
    while dest.exists():
        dest = images_dir / f"{image_path.stem}_{counter}{image_path.suffix}"
        counter += 1

    shutil.copy2(image_path, dest)
    sidecar_dest = images_dir / (dest.name + ".json")
    sidecar_dest.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    entry = {
        **metadata,
        "file": f"images/{dest.name}",
        "project_dir": str(Path.cwd()),
    }
    index["entries"].append(entry)
    index_path = gallery_dir / "index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return dest


def generate_image(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    size: str = DEFAULT_SIZE,
    quality: str = DEFAULT_QUALITY,
    background: str = DEFAULT_BACKGROUND,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    output_compression: int | None = None,
    moderation: str = DEFAULT_MODERATION,
    reference_images: list[str] | None = None,
    mask: str | None = None,
    input_fidelity: str | None = None,
    output_name: str | None = None,
    backend: str = DEFAULT_BACKEND,
    codex_resume: str | None = None,
    aspect_retries: int = DEFAULT_ASPECT_RETRIES,
) -> str | None:
    """Генерирует изображение через gpt-image-2 и возвращает путь к файлу (None при неудаче).

    backend:
        - "auto"  (рекомендуется): берёт Codex CLI по подписке ChatGPT, при неудаче
                  откатывается на API
        - "codex": всегда через Codex CLI, без отката
        - "api"  : напрямую в OpenAI API (исходное поведение)
    """
    if reference_images:
        for p in reference_images:
            if not Path(p).exists():
                print(f"[Error] референсное изображение не найдено: {p}")
                return None
    if mask and not Path(mask).exists():
        print(f"[Error] изображение маски не найдено: {mask}")
        return None

    if size != "auto":
        try:
            validate_size(size)
        except ValueError as e:
            print(f"[Error] {e}")
            return None

    effective_backend = _resolve_backend(backend)

    if effective_backend == "codex":
        # Codex не умеет принимать маску, поэтому в режиме auto откатываемся на API
        if mask:
            if backend == "auto" and os.environ.get("OPENAI_API_KEY"):
                print("[Info] маску нельзя передать через Codex, откатываюсь на backend api")
                effective_backend = "api"
            elif backend == "codex":
                print("[Error] --mask не работает вместе с --backend codex")
                return None
            else:
                print("[Error] backend codex не поддерживает маску, а ключа API нет")
                return None

    if effective_backend == "codex":
        if size != "auto":
            if aspect_retries > 0:
                print(
                    "[Warning] backend Codex не соблюдает размер в пикселях: у встроенного"
                    " инструмента нет такого параметра. Пропорция будет проверена по факту"
                    f" (до {aspect_retries} повтор(а/ов)). Если нужен точный размер — --backend api"
                )
            else:
                print(
                    "[Warning] backend Codex не соблюдает размер в пикселях, а проверка"
                    " пропорции отключена (--aspect-retries 0). Если нужен точный размер —"
                    " --backend api"
                )
        output_path = get_output_path(output_dir, output_format, name=output_name)
        # Пропорцию бэкенд соблюдает не всегда, поэтому проверяем её по факту и
        # при промахе генерируем заново, подсказав агенту, что вышло в прошлый раз.
        # Пиксель-в-пиксель это не даёт (площадь задаёт сервер), но пропорцию —
        # даёт, а дальше остаётся честное уменьшение без добивки краёв.
        attempts = max(0, aspect_retries) + 1
        codex_result = None
        aspect_hint = None
        for attempt in range(1, attempts + 1):
            codex_result = _generate_via_codex(
                prompt,
                size=size,
                quality=quality,
                output_format=output_format,
                background=background,
                output_path=output_path,
                reference_images=reference_images,
                resume_session_id=codex_resume,
                aspect_hint=aspect_hint,
            )
            if codex_result is None:
                break
            ok, got = _aspect_matches(codex_result[0], size)
            if ok:
                if attempt > 1:
                    print(f"[Info] пропорция получена с попытки {attempt}: {got}")
                break
            if attempt < attempts:
                print(
                    f"[Warning] попытка {attempt}: кадр {got} не в пропорции {size},"
                    " генерирую заново"
                )
                aspect_hint = _aspect_retry_hint(size, got)
            else:
                print(
                    f"[Warning] за {attempts} попыт(ку/ки) пропорция {size} не получена,"
                    f" оставляю последний кадр {got} — при сборке понадобится добивка (-Pad)"
                )
        if codex_result is not None:
            saved_path, revised, session_id = codex_result
            if revised:
                print(f"[Revised] {revised}")
            if session_id:
                # Этот ID передаётся в --codex-resume для следующего слайда серии
                print(f"[Session] {session_id}")
            print(f"[Success] изображение сохранено (backend=codex): {saved_path}")
            meta = _build_meta(
                model=model,
                prompt=prompt,
                size=size,
                quality=quality,
                background=background,
                output_format=output_format,
                moderation=moderation,
                reference_images=reference_images,
                mask=mask,
                input_fidelity=input_fidelity,
                revised=revised,
                backend="codex",
                codex_session_id=session_id,
            )
            _save_metadata(saved_path, meta)
            try:
                store_in_gallery(saved_path, meta)
            except Exception as e:
                print(f"[Warning] не удалось сохранить в галерею: {e}")
            return str(saved_path)

        # Решаем, откатываться ли на API после неудачи Codex
        if backend == "auto" and os.environ.get("OPENAI_API_KEY"):
            print("[Info] backend Codex не справился, откат (fallback) на backend api")
            effective_backend = "api"
        else:
            return None

    # API backend
    client = OpenAI()

    base_kwargs = _build_generate_kwargs(
        model=model,
        prompt=prompt,
        size=size,
        quality=quality,
        background=background,
        output_format=output_format,
        output_compression=output_compression,
        moderation=moderation,
    )

    if reference_images:
        with contextlib.ExitStack() as stack:
            files = [stack.enter_context(open(p, "rb")) for p in reference_images]
            edit_kwargs = dict(base_kwargs)
            edit_kwargs["image"] = files if len(files) > 1 else files[0]
            if mask:
                edit_kwargs["mask"] = stack.enter_context(open(mask, "rb"))
            if input_fidelity:
                edit_kwargs["input_fidelity"] = input_fidelity
            response = _call_image_edits(client, **edit_kwargs)
    else:
        response = _call_image_generations(client, **base_kwargs)

    data = getattr(response, "data", None) or []
    if not data:
        print("[Warning] в ответе не оказалось изображения")
        return None

    datum = data[0]
    b64 = getattr(datum, "b64_json", None)
    if not b64:
        print("[Warning] в ответе нет поля b64_json")
        return None

    revised = getattr(datum, "revised_prompt", None)
    if revised:
        print(f"[Revised] {revised}")

    output_path = get_output_path(output_dir, output_format, name=output_name)
    output_path.write_bytes(base64.b64decode(b64))
    print(f"[Success] изображение сохранено: {output_path}")

    meta = _build_meta(
        model=model,
        prompt=prompt,
        size=size,
        quality=quality,
        background=background,
        output_format=output_format,
        moderation=moderation,
        reference_images=reference_images,
        mask=mask,
        input_fidelity=input_fidelity,
        revised=revised,
        backend="api",
    )
    _save_metadata(output_path, meta)
    try:
        store_in_gallery(output_path, meta)
    except Exception as e:
        print(f"[Warning] не удалось сохранить в галерею: {e}")

    return str(output_path)


def _build_meta(
    *,
    model: str,
    prompt: str,
    size: str,
    quality: str,
    background: str,
    output_format: str,
    moderation: str,
    reference_images: list[str] | None,
    mask: str | None,
    input_fidelity: str | None,
    revised: str | None,
    backend: str,
    codex_session_id: str | None = None,
) -> dict:
    return {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "background": background,
        "output_format": output_format,
        "mime_type": OUTPUT_FORMAT_TO_MIME.get(output_format, "image/png"),
        "moderation": moderation,
        "reference_images": reference_images or [],
        "mask": mask,
        "input_fidelity": input_fidelity,
        "revised_prompt": revised,
        "backend": backend,
        "codex_session_id": codex_session_id,
        "timestamp": datetime.now().isoformat(),
    }


def main():
    args = parse_args()

    if args.mask and not args.reference:
        print("[Error] --mask используется только вместе с --reference")
        sys.exit(1)
    if args.codex_resume and args.backend == "api":
        print("[Error] --codex-resume не работает с --backend api: это возможность Codex")
        sys.exit(2)
    if args.background == "transparent" and not args.model.startswith("gpt-image-1"):
        print(
            f"[Error] модель {args.model} не поддерживает --background transparent."
            " Если нужен прозрачный PNG: (1) переключитесь на --model gpt-image-1.5,"
            " (2) уберите фон после генерации через rembg или аналог,"
            " (3) используйте ccskill-nanobanana"
        )
        sys.exit(2)
    if args.input_fidelity is not None and args.model.startswith("gpt-image-2"):
        print(
            "[Info] gpt-image-2 всегда обрабатывает входные изображения с максимальной"
            " точностью, поэтому --input-fidelity не нужен и будет пропущен"
            " (иначе API вернёт ошибку)"
        )
        args.input_fidelity = None

    if args.size != "auto":
        try:
            validate_size(args.size)
        except ValueError as e:
            print(f"[Error] {e}")
            sys.exit(2)

    try:
        result = generate_image(
            prompt=args.prompt,
            model=args.model,
            size=args.size,
            quality=args.quality,
            background=args.background,
            output_dir=args.output,
            output_format=args.output_format,
            output_compression=args.output_compression,
            moderation=args.moderation,
            reference_images=args.reference if args.reference else None,
            mask=args.mask,
            input_fidelity=args.input_fidelity,
            output_name=args.output_name,
            backend=args.backend,
            codex_resume=args.codex_resume,
            aspect_retries=args.aspect_retries,
        )
        if result is None:
            sys.exit(1)
    except Exception as e:
        print(f"[Error] не удалось сгенерировать изображение: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
