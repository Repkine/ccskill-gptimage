#!/usr/bin/env python3
"""ccskill-gptimage 画像生成スクリプト

OpenAI gpt-image-2 (ChatGPT Images 2.0) を使用して画像を生成・編集する。

使用例:
    python generate_image.py "a minimalist fox logo, flat vector, navy and gold"
    python generate_image.py "背景を夕焼けに" --reference original.png --input-fidelity high
    python generate_image.py "gift basket on white" --background transparent --output-format png

環境変数:
    OPENAI_API_KEY: OpenAI API キー(.env でも可)
"""

import argparse
import base64
import contextlib
import json
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

# ギャラリーストア(全 ccskill 横断の生成物蓄積先。issue #024 / ccskill-gallery store-spec v1.0)
GALLERY_DIR_ENV = "CCSKILL_GPTIMAGE_GALLERY_DIR"
DEFAULT_GALLERY_DIR = Path.home() / ".ccskill-gptimage" / "gallery"

SIZE_CHOICES = ["auto", "1024x1024", "1024x1536", "1536x1024"]  # よく使う例(enum 強制ではない)

# gpt-image-2 のサイズ制約(出典: gpt-image-2 サイズ仕様 / issue #018 で実証)
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


def validate_size(size: str) -> tuple[int, int]:
    """`WxH` 文字列を gpt-image-2 のサイズ制約で検証し (幅, 高さ) を返す。

    違反時は具体的な日本語メッセージ付きの ValueError を送出する。
    `auto` は呼び出し側で別扱いする前提(本関数には渡さない)。

    制約(出典: gpt-image-2 サイズ仕様、issue #018 で実証):
      1. 各辺が 16 の倍数
      2. 最大辺 <= 3840px
      3. アスペクト比(長辺/短辺) <= 3:1
      4. 総ピクセル数が 655,360 <= W*H <= 8,294,400
    """
    m = re.fullmatch(r"(\d+)x(\d+)", size.strip())
    if not m:
        raise ValueError(
            f"--size は 'WxH'(例: 1024x1024)または 'auto' で指定してください: {size!r} は不正な形式です"
        )
    w, h = int(m.group(1)), int(m.group(2))
    if w % SIZE_MULTIPLE != 0 or h % SIZE_MULTIPLE != 0:
        bad = w if w % SIZE_MULTIPLE != 0 else h
        raise ValueError(
            f"各辺は {SIZE_MULTIPLE} の倍数にしてください: {bad} は {SIZE_MULTIPLE} の倍数ではありません(指定: {w}x{h})"
        )
    if max(w, h) > SIZE_MAX_SIDE:
        raise ValueError(
            f"最大辺は {SIZE_MAX_SIDE}px 以下にしてください: {max(w, h)} は上限を超えています(指定: {w}x{h})"
        )
    long_side, short_side = max(w, h), min(w, h)
    aspect = long_side / short_side
    if aspect > SIZE_MAX_ASPECT:
        raise ValueError(
            f"アスペクト比は 3:1 以下にしてください: {w}x{h} は {aspect:.2f}:1 です"
        )
    total = w * h
    if total < SIZE_MIN_PIXELS:
        raise ValueError(
            f"総ピクセル数は {SIZE_MIN_PIXELS:,} 以上にしてください: {w}x{h} = {total:,} は下限を下回ります"
        )
    if total > SIZE_MAX_PIXELS:
        raise ValueError(
            f"総ピクセル数は {SIZE_MAX_PIXELS:,} 以下にしてください: {w}x{h} = {total:,} は上限を超えています"
        )
    return (w, h)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OpenAI gpt-image-2 で画像を生成・編集します"
    )
    parser.add_argument("prompt", type=str, help="画像生成のプロンプト")
    parser.add_argument(
        "--size",
        type=str,
        default=DEFAULT_SIZE,
        help=(
            f"出力サイズ。'auto' または 'WxH'(例: {DEFAULT_SIZE}, 3840x2160)。"
            f" 制約: 各辺 {SIZE_MULTIPLE} の倍数 / 最大辺 {SIZE_MAX_SIDE}px /"
            f" アスペクト比 3:1 以下 / 総ピクセル {SIZE_MIN_PIXELS:,}〜{SIZE_MAX_PIXELS:,}。"
            " よく使う例: " + " ".join(s for s in SIZE_CHOICES if s != "auto")
        ),
    )
    parser.add_argument(
        "--quality",
        type=str,
        default=DEFAULT_QUALITY,
        choices=QUALITY_CHOICES,
        help=f"品質 (デフォルト: {DEFAULT_QUALITY})",
    )
    parser.add_argument(
        "--background",
        type=str,
        default=DEFAULT_BACKGROUND,
        choices=BACKGROUND_CHOICES,
        help=(
            f"背景 (デフォルト: {DEFAULT_BACKGROUND})。"
            " 注意: gpt-image-2 は transparent 非対応(400 になります)。"
            " 透過 PNG が必要な場合は ccskill-nanobanana を使ってください。"
        ),
    )
    parser.add_argument(
        "--output-format",
        dest="output_format",
        type=str,
        default=DEFAULT_OUTPUT_FORMAT,
        choices=OUTPUT_FORMAT_CHOICES,
        help=f"出力形式 (デフォルト: {DEFAULT_OUTPUT_FORMAT})",
    )
    parser.add_argument(
        "--output-compression",
        dest="output_compression",
        type=int,
        default=None,
        help="出力圧縮率 (jpeg/webp 時、0-100)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"出力ディレクトリ (デフォルト: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--reference",
        type=str,
        action="append",
        default=[],
        help="参照画像のパス (複数指定可)。指定すると edits API に切替",
    )
    parser.add_argument(
        "--mask",
        type=str,
        default=None,
        help="マスク画像 (透明部分が編集対象。--reference 必須)",
    )
    parser.add_argument(
        "--input-fidelity",
        dest="input_fidelity",
        type=str,
        default=None,
        choices=INPUT_FIDELITY_CHOICES,
        help=(
            "参照画像の保持忠実度。"
            " 注意: gpt-image-2 は **常に自動で最大忠実度** で入力画像を処理するため、"
            " 本パラメータの指定は不要です(指定すると 400 エラー)。"
            " 旧モデル `gpt-image-1.5` を `--model` で指定する場合は high/low が指定可能です。"
        ),
    )
    parser.add_argument(
        "--moderation",
        type=str,
        default=DEFAULT_MODERATION,
        choices=MODERATION_CHOICES,
        help=f"モデレーション (デフォルト: {DEFAULT_MODERATION})",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"モデル ID (デフォルト: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--output-name",
        dest="output_name",
        type=str,
        default=None,
        help="出力ファイル名(拡張子は output_format から決定)。未指定時はタイムスタンプ",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default=DEFAULT_BACKEND,
        choices=BACKEND_CHOICES,
        help=(
            f"画像生成 backend (デフォルト: {DEFAULT_BACKEND})。"
            " auto = Codex CLI(ChatGPT サブスク認証あり)があれば codex、"
            " 失敗時は OPENAI_API_KEY があれば api にフォールバック。"
        ),
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Backend detection / dispatch (issue #017: Codex CLI integration)
# ---------------------------------------------------------------------------


def _codex_subscription_available() -> bool:
    """Codex CLI が PATH にあり、ChatGPT サブスク認証されているか判定。

    判定根拠は `~/.codex/auth.json` の `tokens.access_token` の存在。
    `auth_mode` フィールド名は古い版のものらしく、現行版では tokens 構造のみ。
    """
    if shutil.which("codex") is None:
        return False
    if not CODEX_AUTH_FILE.exists():
        return False
    try:
        data = json.loads(CODEX_AUTH_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    tokens = data.get("tokens") or {}
    return bool(tokens.get("access_token"))


def _resolve_backend(requested: str) -> str:
    """`auto` を実 backend に解決する。明示指定はそのまま返す。

    auto の場合: codex 利用可能 → codex / それ以外 → api(api キー無くても api を返し
    後段の OpenAI() で native エラーに任せる)。
    """
    if requested != "auto":
        return requested
    if _codex_subscription_available():
        return "codex"
    return "api"


def _find_latest_codex_image(since_mtime: float) -> Path | None:
    """`since_mtime` より後に生成された最新の `ig_*.png` を返す(旧 Codex 経路)。

    ~2026-04 頃の Codex CLI は出力先指定を受け付けず、画像を
    `~/.codex/generated_images/<session-id>/ig_*.png` にファイル出力していた。
    新しい Codex (codex exec) はファイル化せずセッションログに inline base64 で返すため、
    こちらが None のときは `_recover_codex_image_from_session()` をフォールバックに使う。
    """
    if not CODEX_GENERATED_DIR.exists():
        return None
    latest_mtime = -1.0
    latest_path: Path | None = None
    for p in CODEX_GENERATED_DIR.rglob("ig_*.png"):
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if m > since_mtime and m > latest_mtime:
            latest_mtime = m
            latest_path = p
    return latest_path


def _extract_codex_session_id(stdout: str) -> str | None:
    """codex exec のヘッダ出力 (`session id: <uuid>`) から session id を抽出する。"""
    if not stdout:
        return None
    m = re.search(r"session id:\s*([0-9a-fA-F][0-9a-fA-F-]{7,})", stdout)
    return m.group(1) if m else None


def _find_codex_session_log(session_id: str | None, since_mtime: float) -> Path | None:
    """この実行に対応する Codex セッションログ (`rollout-*.jsonl`) を特定する。

    session_id が分かればそれを含むファイル名を優先。分からなければ since_mtime より後に
    更新された最新の jsonl を採用する(本番では codex exec 実行中にログが書かれるため成立)。
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
    """Codex セッションログから生成画像 (`image_generation_call.result` の base64) を回収する。

    新しい Codex (>= 2026-06 頃) は `codex exec` で画像をファイル化せず、セッションログ内に
    inline base64 で返す。`status == "completed"` を優先し、無ければ最後に出現した result を
    採用する(partial_images 対策)。`data:` URI 形式にも一応対応する。
    """
    try:
        text = log_path.read_text()
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
) -> str:
    """Codex agent への指示プロンプトを組み立てる。

    重要: 「image_gen を直接使え、API スクリプトは書くな」を必ず明記する。
    これがないと Codex は curl/Python で API 直叩きルートを取り、
    サブスク枠ではなく従量課金になる(note.com/mauekusa の知見)。
    """
    lines = [
        "OpenAI gpt-image-2 を built-in image_gen tool 経由で呼び出してください。",
        "重要: API キーやスクリプト (curl / python / node) は一切書かず、"
        "組み込みの image_gen ツールを直接使ってください。",
        f"size: {size}",
        f"quality: {quality}",
        f"output format: {output_format}",
    ]
    if background and background != "auto":
        lines.append(f"background: {background}")
    if reference_count > 0:
        lines.append(
            f"添付された {reference_count} 枚の参照画像をベースに edit モードで生成してください。"
            " 元画像の主要要素(人物の顔・構図・背景など)はできる限り保持してください。"
        )
    lines.append("")
    lines.append("プロンプト:")
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
) -> tuple[Path, str | None] | None:
    """Codex CLI 経由で画像生成。成功時は (output_path, revised_prompt) を返す。失敗時 None。

    失敗の原因は subprocess エラー / image_gen 出力なし / コピー失敗 など。
    呼び出し側はこれを見て auto モードなら API へフォールバックできる。
    """
    codex_prompt = _build_codex_prompt(
        prompt,
        size=size,
        quality=quality,
        output_format=output_format,
        background=background,
        reference_count=len(reference_images or []),
    )
    cmd: list[str] = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        codex_prompt,
    ]
    # `-i` は variadic なので必ず prompt の後に置く(逆だと prompt まで画像として食われる)
    for ref in reference_images or []:
        cmd.extend(["-i", ref])

    started_at = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CODEX_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print("[Error] Codex CLI が timeout しました")
        return None
    except FileNotFoundError:
        print("[Error] codex コマンドが PATH に見つかりません")
        return None

    if proc.returncode != 0:
        print(f"[Error] Codex CLI exit code {proc.returncode}: {proc.stderr.strip()[:200]}")
        return None

    revised = _extract_revised_prompt_from_codex_log(proc.stdout)

    # 旧 Codex: 画像は ~/.codex/generated_images/<session>/ig_*.png にファイル出力される
    image = _find_latest_codex_image(started_at)
    if image is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image, output_path)
        return (output_path, revised)

    # 新 Codex (>= 2026-06 頃): codex exec は画像をファイル化せず、セッションログ内に
    # inline base64 で返す。ログから回収してデコード保存する。
    session_id = _extract_codex_session_id(proc.stdout)
    log_path = _find_codex_session_log(session_id, started_at)
    if log_path is not None:
        data = _recover_codex_image_from_session(log_path)
        if data:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(data)
            return (output_path, revised)

    print("[Error] Codex 経由で生成された画像が見つかりませんでした")
    return None


def _extract_revised_prompt_from_codex_log(stdout: str) -> str | None:
    """Codex のログ末尾から agent の最終応答(revised_prompt 相当)を抽出。

    現状はベストエフォート: ログ末尾に `codex` 行があればその後ろの行を返す。
    取得できなくても致命的ではないので None で許容。
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
    """Image API /generations 用のパラメータを組み立てる。auto は省略する。"""
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
    """Image API 経路: テキスト→画像生成"""
    return client.images.generate(**kwargs)


def _call_image_edits(client: OpenAI, **kwargs):
    """Image API 経路: 参照画像/マスクありの編集"""
    return client.images.edit(**kwargs)


def _save_metadata(image_path: Path, meta: dict) -> Path:
    meta_path = image_path.with_suffix(image_path.suffix + ".json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta_path


def get_gallery_dir() -> Path:
    """ギャラリーストアのパスを解決する(環境変数 GALLERY_DIR_ENV で変更可能)。

    ccskill-gallery store-spec v1.0 準拠: デフォルトは ~/.ccskill-gptimage/gallery。
    """
    env = os.environ.get(GALLERY_DIR_ENV)
    if env:
        return Path(env).expanduser()
    return DEFAULT_GALLERY_DIR


def load_index(gallery_dir: Path) -> dict:
    """index.json を読み込む。不在・破損時はストア内のサイドカーから再構築する。"""
    index_path = gallery_dir / "index.json"
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(index, dict) and isinstance(index.get("entries"), list):
                return index
        except (json.JSONDecodeError, OSError):
            print("[Warning] index.json が破損しているため再構築します")

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
    """画像とメタデータをギャラリーストアへコピーし index.json に追記する(store-spec v1.0)。"""
    gallery_dir = get_gallery_dir()
    images_dir = gallery_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # 既存 index を先に読む(コピー後に読むと再構築時に自分自身を重複計上するため)
    index = load_index(gallery_dir)

    # 同名衝突時は連番サフィックスで一意化
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
) -> str | None:
    """gpt-image-2 で画像を生成し、ファイルパスを返す。失敗時は None。

    backend:
        - "auto"  (推奨): Codex CLI(ChatGPT サブスク)があればそれを使い、失敗時は API にフォールバック
        - "codex": Codex CLI を必ず使う(失敗時はフォールバックしない)
        - "api"  : OpenAI API を直接叩く(従来動作)
    """
    if reference_images:
        for p in reference_images:
            if not Path(p).exists():
                print(f"[Error] 参照画像が見つかりません: {p}")
                return None
    if mask and not Path(mask).exists():
        print(f"[Error] マスク画像が見つかりません: {mask}")
        return None

    if size != "auto":
        try:
            validate_size(size)
        except ValueError as e:
            print(f"[Error] {e}")
            return None

    effective_backend = _resolve_backend(backend)

    if effective_backend == "codex":
        # Codex は mask を渡せないので、auto モードでは API にフォールバック
        if mask:
            if backend == "auto" and os.environ.get("OPENAI_API_KEY"):
                print("[Info] mask は Codex 経由で渡せません。API backend にフォールバックします")
                effective_backend = "api"
            elif backend == "codex":
                print("[Error] --backend codex では --mask を使用できません")
                return None
            else:
                print("[Error] mask は Codex backend では非対応で API キーもありません")
                return None

    if effective_backend == "codex":
        if size != "auto":
            print(
                "[Warning] Codex backend ではサイズが保証されません(agent 経由で非決定的)。"
                " 厳密な --size が必要なら --backend api を使ってください"
            )
        output_path = get_output_path(output_dir, output_format, name=output_name)
        codex_result = _generate_via_codex(
            prompt,
            size=size,
            quality=quality,
            output_format=output_format,
            background=background,
            output_path=output_path,
            reference_images=reference_images,
        )
        if codex_result is not None:
            saved_path, revised = codex_result
            if revised:
                print(f"[Revised] {revised}")
            print(f"[Success] 画像を保存しました (backend=codex): {saved_path}")
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
            )
            _save_metadata(saved_path, meta)
            try:
                store_in_gallery(saved_path, meta)
            except Exception as e:
                print(f"[Warning] ギャラリーへの蓄積に失敗しました: {e}")
            return str(saved_path)

        # Codex 失敗時のフォールバック判定
        if backend == "auto" and os.environ.get("OPENAI_API_KEY"):
            print("[Info] Codex backend が失敗しました。API backend にフォールバックします")
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
        print("[Warning] レスポンスに画像が含まれていませんでした")
        return None

    datum = data[0]
    b64 = getattr(datum, "b64_json", None)
    if not b64:
        print("[Warning] レスポンスに b64_json が含まれていませんでした")
        return None

    revised = getattr(datum, "revised_prompt", None)
    if revised:
        print(f"[Revised] {revised}")

    output_path = get_output_path(output_dir, output_format, name=output_name)
    output_path.write_bytes(base64.b64decode(b64))
    print(f"[Success] 画像を保存しました: {output_path}")

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
        print(f"[Warning] ギャラリーへの蓄積に失敗しました: {e}")

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
        "timestamp": datetime.now().isoformat(),
    }


def main():
    args = parse_args()

    if args.mask and not args.reference:
        print("[Error] --mask は --reference と併用してください")
        sys.exit(1)
    if args.background == "transparent" and not args.model.startswith("gpt-image-1"):
        print(
            f"[Error] {args.model} は --background transparent をサポートしていません。"
            " 透過 PNG が必要な場合: (1) --model gpt-image-1.5 に切替、"
            " (2) 生成後に rembg 等で背景除去、"
            " (3) ccskill-nanobanana を使用"
        )
        sys.exit(2)
    if args.input_fidelity is not None and args.model.startswith("gpt-image-2"):
        print(
            "[Info] gpt-image-2 は常に自動で最大忠実度で入力画像を処理します。"
            " --input-fidelity の指定は不要なため省略します(API エラーを回避)"
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
        )
        if result is None:
            sys.exit(1)
    except Exception as e:
        print(f"[Error] 画像生成に失敗しました: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
