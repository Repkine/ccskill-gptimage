"""Тесты скрипта генерации изображений ccskill-gptimage"""

import base64
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from generate_image import (
    BACKEND_CHOICES,
    DEFAULT_BACKEND,
    DEFAULT_BACKGROUND,
    DEFAULT_MODEL,
    DEFAULT_MODERATION,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_QUALITY,
    DEFAULT_SIZE,
    GALLERY_DIR_ENV,
    OUTPUT_FORMAT_TO_EXT,
    OUTPUT_FORMAT_TO_MIME,
    _codex_subscription_available,
    _resolve_backend,
    generate_image,
    get_gallery_dir,
    get_output_path,
    load_index,
    main,
    parse_args,
    store_in_gallery,
    validate_size,
)


# base64 прозрачного PNG 1x1 — заглушка для моков
DUMMY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgAAIAAAUAAeImBZsAAAAASUVORK5CYII="
)


def _make_image_response(b64: str = DUMMY_PNG_B64, revised_prompt: str | None = None) -> Mock:
    """Собирает фиктивный ответ OpenAI Images API"""
    datum = Mock()
    datum.b64_json = b64
    datum.revised_prompt = revised_prompt
    response = Mock()
    response.data = [datum]
    return response


@pytest.fixture(autouse=True)
def _force_api_backend(request, monkeypatch):
    """Фиксирует существующие тесты на работу без Codex.
    Если тестируется сама логика выбора backend, отключается меткой
    @pytest.mark.no_force_api_backend."""
    if request.node.get_closest_marker("no_force_api_backend"):
        return
    monkeypatch.setattr("generate_image._codex_subscription_available", lambda: False)


@pytest.fixture(autouse=True)
def _isolate_gallery(tmp_path, monkeypatch):
    """Изолирует тесты от реальной галереи пользователя (~/.ccskill-gptimage/gallery)"""
    monkeypatch.setenv(GALLERY_DIR_ENV, str(tmp_path / "gallery"))


class TestParseArgs:
    def test_prompt_only_uses_defaults(self):
        args = parse_args(["a cat playing piano"])
        assert args.prompt == "a cat playing piano"
        assert args.size == DEFAULT_SIZE
        assert args.quality == DEFAULT_QUALITY
        assert args.output == DEFAULT_OUTPUT_DIR
        assert args.output_format == DEFAULT_OUTPUT_FORMAT
        assert args.background == DEFAULT_BACKGROUND
        assert args.moderation == DEFAULT_MODERATION
        assert args.reference == []
        assert args.mask is None
        assert args.input_fidelity is None

    def test_quality_choice(self):
        args = parse_args(["p", "--quality", "high"])
        assert args.quality == "high"

    def test_size(self):
        args = parse_args(["p", "--size", "1024x1536"])
        assert args.size == "1024x1536"

    def test_background_transparent(self):
        args = parse_args(["p", "--background", "transparent"])
        assert args.background == "transparent"

    def test_output_format(self):
        args = parse_args(["p", "--output-format", "jpeg"])
        assert args.output_format == "jpeg"

    def test_output_compression(self):
        args = parse_args(["p", "--output-format", "jpeg", "--output-compression", "80"])
        assert args.output_compression == 80

    def test_reference_multiple(self):
        args = parse_args([
            "p",
            "--reference", "a.png",
            "--reference", "b.png",
        ])
        assert args.reference == ["a.png", "b.png"]

    def test_mask(self):
        args = parse_args(["p", "--reference", "src.png", "--mask", "m.png"])
        assert args.mask == "m.png"

    def test_input_fidelity(self):
        args = parse_args(["p", "--reference", "a.png", "--input-fidelity", "high"])
        assert args.input_fidelity == "high"

    def test_moderation_low(self):
        args = parse_args(["p", "--moderation", "low"])
        assert args.moderation == "low"

    def test_output_name(self):
        args = parse_args(["p", "--output-name", "hero"])
        assert args.output_name == "hero"

    def test_output_name_default_none(self):
        args = parse_args(["p"])
        assert args.output_name is None


class TestGetOutputPath:
    def test_creates_directory_if_not_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "new_subdir"
            path = get_output_path(str(out))
            assert out.exists()
            assert path.parent == out

    def test_default_extension_is_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = get_output_path(tmp)
            assert path.suffix == ".png"

    def test_jpeg_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = get_output_path(tmp, output_format="jpeg")
            assert path.suffix == ".jpg"

    def test_webp_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = get_output_path(tmp, output_format="webp")
            assert path.suffix == ".webp"

    def test_unknown_format_falls_back_to_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = get_output_path(tmp, output_format="bmp")
            assert path.suffix == ".png"

    def test_filename_is_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = get_output_path(tmp)
            stem = path.stem
            assert len(stem) == 15  # YYYYMMDD_HHMMSS
            assert stem.replace("_", "").isdigit()

    def test_custom_name_overrides_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = get_output_path(tmp, output_format="png", name="my_image")
            assert path.name == "my_image.png"

    def test_custom_name_with_jpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = get_output_path(tmp, output_format="jpeg", name="cover")
            assert path.name == "cover.jpg"


class TestOutputFormatMapping:
    def test_png(self):
        assert OUTPUT_FORMAT_TO_EXT["png"] == ".png"

    def test_jpeg(self):
        assert OUTPUT_FORMAT_TO_EXT["jpeg"] == ".jpg"

    def test_webp(self):
        assert OUTPUT_FORMAT_TO_EXT["webp"] == ".webp"


class TestGenerateImageBasic:
    @patch("generate_image.OpenAI")
    def test_text_to_image_calls_generations(self, mock_openai_cls):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.return_value = _make_image_response()

        with tempfile.TemporaryDirectory() as tmp:
            result = generate_image(
                prompt="a fox logo",
                size="1024x1024",
                quality="high",
                output_dir=tmp,
                output_format="png",
                background="auto",
            )

            assert result is not None
            assert result.endswith(".png")
            client.images.generate.assert_called_once()
            kwargs = client.images.generate.call_args.kwargs
            assert kwargs["model"] == DEFAULT_MODEL
            assert kwargs["prompt"] == "a fox logo"
            assert kwargs["size"] == "1024x1024"
            assert kwargs["quality"] == "high"
            # При opaque/auto параметр background не отправляется
            assert "background" not in kwargs or kwargs["background"] != "transparent"
            # Файл действительно записан на диск
            assert Path(result).exists()
            assert Path(result).stat().st_size > 0

    @patch("generate_image.OpenAI")
    def test_transparent_background_passes_param(self, mock_openai_cls):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.return_value = _make_image_response()

        with tempfile.TemporaryDirectory() as tmp:
            generate_image(
                prompt="logo",
                size="1024x1024",
                quality="medium",
                output_dir=tmp,
                output_format="png",
                background="transparent",
            )

        kwargs = client.images.generate.call_args.kwargs
        assert kwargs["background"] == "transparent"

    @patch("generate_image.OpenAI")
    def test_output_format_passed_through(self, mock_openai_cls):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.return_value = _make_image_response()

        with tempfile.TemporaryDirectory() as tmp:
            result = generate_image(
                prompt="x",
                output_dir=tmp,
                output_format="jpeg",
                output_compression=70,
            )

        kwargs = client.images.generate.call_args.kwargs
        assert kwargs["output_format"] == "jpeg"
        assert kwargs["output_compression"] == 70
        assert result.endswith(".jpg")

    @patch("generate_image.OpenAI")
    def test_output_name_is_used_for_file(self, mock_openai_cls):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.return_value = _make_image_response()

        with tempfile.TemporaryDirectory() as tmp:
            result = generate_image(
                prompt="x",
                output_dir=tmp,
                output_format="png",
                output_name="my_hero",
            )
            assert result is not None
            assert Path(result).name == "my_hero.png"
            assert Path(result).exists()

    @patch("generate_image.OpenAI")
    def test_moderation_low_is_passed(self, mock_openai_cls):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.return_value = _make_image_response()

        with tempfile.TemporaryDirectory() as tmp:
            generate_image(prompt="x", output_dir=tmp, moderation="low")

        assert client.images.generate.call_args.kwargs["moderation"] == "low"

    @patch("generate_image.OpenAI")
    def test_no_data_in_response_returns_none(self, mock_openai_cls):
        client = Mock()
        mock_openai_cls.return_value = client
        empty = Mock()
        empty.data = []
        client.images.generate.return_value = empty

        with tempfile.TemporaryDirectory() as tmp:
            result = generate_image(prompt="x", output_dir=tmp)

        assert result is None

    @patch("generate_image.OpenAI")
    def test_api_exception_propagates(self, mock_openai_cls):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.side_effect = RuntimeError("boom")

        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(RuntimeError, match="boom"):
                generate_image(prompt="x", output_dir=tmp)


class TestGenerateImageWithReference:
    @patch("generate_image.OpenAI")
    def test_reference_routes_to_edits(self, mock_openai_cls):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.edit.return_value = _make_image_response()

        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "ref.png"
            ref.write_bytes(base64.b64decode(DUMMY_PNG_B64))
            result = generate_image(
                prompt="change background to sunset",
                output_dir=tmp,
                reference_images=[str(ref)],
                input_fidelity="high",
            )

        assert result is not None
        client.images.edit.assert_called_once()
        client.images.generate.assert_not_called()
        kwargs = client.images.edit.call_args.kwargs
        assert kwargs["model"] == DEFAULT_MODEL
        assert kwargs["prompt"] == "change background to sunset"
        assert kwargs["input_fidelity"] == "high"
        # image — это либо список file-like объектов, либо один объект
        assert "image" in kwargs

    @patch("generate_image.OpenAI")
    def test_multiple_references(self, mock_openai_cls):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.edit.return_value = _make_image_response()

        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name in ("a.png", "b.png", "c.png"):
                p = Path(tmp) / name
                p.write_bytes(base64.b64decode(DUMMY_PNG_B64))
                paths.append(str(p))
            generate_image(
                prompt="combine",
                output_dir=tmp,
                reference_images=paths,
            )

        kwargs = client.images.edit.call_args.kwargs
        # Несколько изображений передаются списком
        assert isinstance(kwargs["image"], list)
        assert len(kwargs["image"]) == 3

    @patch("generate_image.OpenAI")
    def test_mask_is_passed(self, mock_openai_cls):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.edit.return_value = _make_image_response()

        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "ref.png"
            ref.write_bytes(base64.b64decode(DUMMY_PNG_B64))
            mask = Path(tmp) / "mask.png"
            mask.write_bytes(base64.b64decode(DUMMY_PNG_B64))
            generate_image(
                prompt="inpaint",
                output_dir=tmp,
                reference_images=[str(ref)],
                mask=str(mask),
            )

        assert "mask" in client.images.edit.call_args.kwargs

    def test_nonexistent_reference_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_image(
                prompt="x",
                output_dir=tmp,
                reference_images=["/no/such/file.png"],
            )
            assert result is None

    def test_nonexistent_reference_prints_error(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            generate_image(
                prompt="x",
                output_dir=tmp,
                reference_images=["/no/such/file.png"],
            )
        captured = capsys.readouterr()
        assert "[Error]" in captured.out
        assert "референсное изображение не найдено" in captured.out


class TestRevisedPromptAndMetadata:
    @patch("generate_image.OpenAI")
    def test_revised_prompt_is_printed(self, mock_openai_cls, capsys):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.return_value = _make_image_response(
            revised_prompt="A cinematic neon Tokyo street at night, ..."
        )

        with tempfile.TemporaryDirectory() as tmp:
            generate_image(prompt="tokyo", output_dir=tmp)

        captured = capsys.readouterr()
        assert "[Revised]" in captured.out
        assert "cinematic neon Tokyo" in captured.out

    @patch("generate_image.OpenAI")
    def test_metadata_sidecar_is_written(self, mock_openai_cls):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.return_value = _make_image_response(
            revised_prompt="rev"
        )

        with tempfile.TemporaryDirectory() as tmp:
            result = generate_image(
                prompt="x",
                size="1024x1024",
                quality="medium",
                output_dir=tmp,
            )

            meta_path = Path(result).with_suffix(Path(result).suffix + ".json")
            assert meta_path.exists()
            meta = json.loads(meta_path.read_text())
            assert meta["prompt"] == "x"
            assert meta["size"] == "1024x1024"
            assert meta["quality"] == "medium"
            assert meta["model"] == DEFAULT_MODEL
            assert meta["revised_prompt"] == "rev"
            assert "timestamp" in meta


class TestDefaults:
    def test_default_model_is_gpt_image_2(self):
        assert DEFAULT_MODEL == "gpt-image-2"

    def test_default_size(self):
        assert DEFAULT_SIZE == "1024x1024"

    def test_default_quality(self):
        assert DEFAULT_QUALITY == "auto"

    def test_default_output_format(self):
        assert DEFAULT_OUTPUT_FORMAT == "png"

    def test_default_output_dir(self):
        assert DEFAULT_OUTPUT_DIR == "./generated_images"

    def test_default_background(self):
        assert DEFAULT_BACKGROUND == "auto"

    def test_default_moderation(self):
        assert DEFAULT_MODERATION == "auto"


class TestMainValidation:
    def _run_main(self, argv: list[str]) -> int | None:
        with patch.object(sys, "argv", ["generate_image.py", *argv]):
            try:
                main()
            except SystemExit as e:
                return e.code
        return None

    def test_transparent_with_gpt_image_2_exits(self, capsys):
        code = self._run_main(["p", "--background", "transparent"])
        assert code == 2
        out = capsys.readouterr().out
        assert "transparent" in out
        assert "gpt-image-1.5" in out

    def test_transparent_with_unknown_model_exits(self, capsys):
        code = self._run_main(["p", "--background", "transparent", "--model", "dall-e-3"])
        assert code == 2
        assert "transparent" in capsys.readouterr().out

    @patch("generate_image.generate_image")
    def test_transparent_with_gpt_image_1_5_passes_through(self, mock_gen):
        mock_gen.return_value = "/tmp/fake.png"
        code = self._run_main([
            "p",
            "--background", "transparent",
            "--model", "gpt-image-1.5",
        ])
        assert code is None
        mock_gen.assert_called_once()
        assert mock_gen.call_args.kwargs["background"] == "transparent"
        assert mock_gen.call_args.kwargs["model"] == "gpt-image-1.5"

    @patch("generate_image.generate_image")
    def test_transparent_with_gpt_image_1_passes_through(self, mock_gen):
        mock_gen.return_value = "/tmp/fake.png"
        code = self._run_main([
            "p",
            "--background", "transparent",
            "--model", "gpt-image-1",
        ])
        assert code is None
        mock_gen.assert_called_once()

    def test_input_fidelity_with_gpt_image_2_is_dropped(self, capsys):
        with patch("generate_image.generate_image") as mock_gen:
            mock_gen.return_value = "/tmp/fake.png"
            self._run_main(["p", "--reference", "ref.png", "--input-fidelity", "high"])
            assert mock_gen.call_args.kwargs["input_fidelity"] is None
        assert "[Info]" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Backend detection / dispatch (Codex CLI integration, issue #017)
# ---------------------------------------------------------------------------


class TestBackendChoices:
    def test_default_backend_is_auto(self):
        assert DEFAULT_BACKEND == "auto"

    def test_backend_choices_contains_three(self):
        assert set(BACKEND_CHOICES) == {"auto", "codex", "api"}

    def test_parse_args_default_backend(self):
        args = parse_args(["p"])
        assert args.backend == DEFAULT_BACKEND

    def test_parse_args_explicit_backend(self):
        args = parse_args(["p", "--backend", "codex"])
        assert args.backend == "codex"


@pytest.mark.no_force_api_backend
class TestCodexSubscriptionAvailable:
    """Поведение самой `_codex_subscription_available()`.
    Autouse-фикстура отключена, вызывается настоящая функция."""

    def test_returns_false_when_codex_not_in_path(self, monkeypatch):
        monkeypatch.setattr("generate_image.shutil.which", lambda name: None)
        assert _codex_subscription_available() is False

    def test_returns_false_when_auth_file_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr("generate_image.shutil.which", lambda name: "/usr/local/bin/codex")
        monkeypatch.setattr("generate_image.CODEX_AUTH_FILE", tmp_path / "missing.json")
        assert _codex_subscription_available() is False

    def test_returns_false_when_auth_file_invalid_json(self, monkeypatch, tmp_path):
        bad = tmp_path / "auth.json"
        bad.write_text("this is not json")
        monkeypatch.setattr("generate_image.shutil.which", lambda name: "/usr/local/bin/codex")
        monkeypatch.setattr("generate_image.CODEX_AUTH_FILE", bad)
        assert _codex_subscription_available() is False

    def test_returns_false_when_tokens_missing(self, monkeypatch, tmp_path):
        f = tmp_path / "auth.json"
        f.write_text(json.dumps({"OPENAI_API_KEY": "sk-foo"}))
        monkeypatch.setattr("generate_image.shutil.which", lambda name: "/usr/local/bin/codex")
        monkeypatch.setattr("generate_image.CODEX_AUTH_FILE", f)
        assert _codex_subscription_available() is False

    def test_returns_false_when_access_token_missing(self, monkeypatch, tmp_path):
        f = tmp_path / "auth.json"
        f.write_text(json.dumps({"tokens": {"refresh_token": "x"}}))
        monkeypatch.setattr("generate_image.shutil.which", lambda name: "/usr/local/bin/codex")
        monkeypatch.setattr("generate_image.CODEX_AUTH_FILE", f)
        assert _codex_subscription_available() is False

    def test_returns_true_when_chatgpt_subscription_logged_in(self, monkeypatch, tmp_path):
        f = tmp_path / "auth.json"
        f.write_text(json.dumps({"tokens": {"access_token": "ey...", "refresh_token": "rt"}}))
        monkeypatch.setattr("generate_image.shutil.which", lambda name: "/usr/local/bin/codex")
        monkeypatch.setattr("generate_image.CODEX_AUTH_FILE", f)
        assert _codex_subscription_available() is True


class TestResolveBackend:
    def test_explicit_codex_returns_codex(self):
        assert _resolve_backend("codex") == "codex"

    def test_explicit_api_returns_api(self):
        assert _resolve_backend("api") == "api"

    def test_auto_with_codex_available_returns_codex(self, monkeypatch):
        monkeypatch.setattr("generate_image._codex_subscription_available", lambda: True)
        assert _resolve_backend("auto") == "codex"

    def test_auto_without_codex_with_api_key_returns_api(self, monkeypatch):
        monkeypatch.setattr("generate_image._codex_subscription_available", lambda: False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert _resolve_backend("auto") == "api"

    def test_auto_without_codex_without_api_key_returns_api(self, monkeypatch):
        """Без codex и без ключа всё равно возвращаем api — ошибку выдаст сам OpenAI()"""
        monkeypatch.setattr("generate_image._codex_subscription_available", lambda: False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert _resolve_backend("auto") == "api"


class TestGenerateViaCodex:
    """Логика генерации через backend codex. subprocess и поиск картинки замоканы"""

    @patch("generate_image.subprocess.run")
    def test_codex_subprocess_args_have_prompt_before_image(
        self, mock_run, monkeypatch, tmp_path
    ):
        """`-i` variadic и съедает следующие позиционные аргументы, поэтому промпт идёт раньше него"""
        # Подсовываем фиктивную сгенерированную картинку
        fake_image = tmp_path / "ig_fake.png"
        fake_image.write_bytes(base64.b64decode(DUMMY_PNG_B64))
        monkeypatch.setattr(
            "generate_image._find_latest_codex_image",
            lambda since: fake_image,
        )
        mock_run.return_value = Mock(returncode=0, stdout="ok", stderr="")

        ref = tmp_path / "ref.png"
        ref.write_bytes(base64.b64decode(DUMMY_PNG_B64))

        out_dir = tmp_path / "out"
        result = generate_image(
            prompt="add a red beret",
            backend="codex",
            output_dir=str(out_dir),
            reference_images=[str(ref)],
        )
        assert result is not None

        cmd = mock_run.call_args[0][0]
        assert "codex" in cmd[0]
        assert "exec" in cmd
        assert "-i" in cmd
        i_idx = cmd.index("-i")
        # Аргумент `-i` (абсолютный путь к ref.png) идёт сразу после самого флага
        assert cmd[i_idx + 1] == str(ref)
        # Промпт передаётся через stdin, а его место в argv занимает `-`,
        # и этот `-` обязан стоять раньше `-i`
        assert "-" in cmd
        assert cmd.index("-") < i_idx
        assert "add a red beret" in mock_run.call_args.kwargs["input"]

    @patch("generate_image.subprocess.run")
    def test_codex_includes_image_gen_directive_in_prompt(
        self, mock_run, monkeypatch, tmp_path
    ):
        """Указание «используй image_gen напрямую» обязано быть в промпте — иначе агент уйдёт в API"""
        fake = tmp_path / "ig_x.png"
        fake.write_bytes(base64.b64decode(DUMMY_PNG_B64))
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: fake)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        generate_image(
            prompt="hello",
            backend="codex",
            output_dir=str(tmp_path / "out"),
        )
        # Промпт для агента уходит в stdin, поэтому проверяем input, а не argv
        assert "image_gen" in mock_run.call_args.kwargs["input"]

    @patch("generate_image.subprocess.run")
    def test_codex_copies_latest_image_to_output_path(
        self, mock_run, monkeypatch, tmp_path
    ):
        fake = tmp_path / "ig_x.png"
        fake.write_bytes(base64.b64decode(DUMMY_PNG_B64))
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: fake)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        out_dir = tmp_path / "out"
        result = generate_image(
            prompt="hi",
            backend="codex",
            output_dir=str(out_dir),
            output_format="png",
            output_name="hero",
        )
        assert result is not None
        copied = out_dir / "hero.png"
        assert copied.exists()
        assert copied.read_bytes() == fake.read_bytes()
        assert str(copied) == result

    @patch("generate_image.subprocess.run")
    def test_codex_metadata_records_backend_codex(
        self, mock_run, monkeypatch, tmp_path
    ):
        fake = tmp_path / "ig_x.png"
        fake.write_bytes(base64.b64decode(DUMMY_PNG_B64))
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: fake)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        out_dir = tmp_path / "out"
        result = generate_image(
            prompt="x", backend="codex", output_dir=str(out_dir), output_name="z"
        )
        meta_path = Path(result + ".json")
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["backend"] == "codex"
        assert meta["prompt"] == "x"

    @patch("generate_image.subprocess.run")
    def test_codex_returns_none_when_no_image_found(
        self, mock_run, monkeypatch, tmp_path
    ):
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: None)
        # Запасной путь через лог сессии тоже глушим, чтобы не зацепить реальный ~/.codex/sessions
        monkeypatch.setattr(
            "generate_image.CODEX_SESSIONS_DIR", tmp_path / "no_sessions"
        )
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        result = generate_image(
            prompt="x", backend="codex", output_dir=str(tmp_path / "out")
        )
        assert result is None

    @patch("generate_image.subprocess.run")
    def test_codex_returns_none_when_subprocess_nonzero(
        self, mock_run, monkeypatch, tmp_path
    ):
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="boom")
        result = generate_image(
            prompt="x", backend="codex", output_dir=str(tmp_path / "out")
        )
        assert result is None


class TestCodexResume:
    """`--codex-resume` переключает вызов на `codex exec resume <ID>` — наследование стиля серии."""

    def _run_with_resume(self, mock_run, monkeypatch, tmp_path, resume):
        fake = tmp_path / "ig_x.png"
        fake.write_bytes(base64.b64decode(DUMMY_PNG_B64))
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: fake)
        mock_run.return_value = Mock(
            returncode=0, stdout="session id: 019eeffd-ca63-7d00-b64e-2dacdd420385\n", stderr=""
        )
        result = generate_image(
            prompt="slide 2",
            backend="codex",
            output_dir=str(tmp_path / "out"),
            output_name="s2",
            codex_resume=resume,
        )
        assert result is not None
        return mock_run.call_args[0][0], result

    @patch("generate_image.subprocess.run")
    def test_resume_uses_exec_resume_subcommand(self, mock_run, monkeypatch, tmp_path):
        sid = "019eeffd-ca63-7d00-b64e-2dacdd420385"
        cmd, _ = self._run_with_resume(mock_run, monkeypatch, tmp_path, sid)
        assert cmd[1] == "exec"
        assert cmd[2] == "resume"
        # SESSION_ID — позиционный аргумент перед промптом (`-`)
        assert cmd.index(sid) < cmd.index("-")

    @patch("generate_image.subprocess.run")
    def test_resume_does_not_pass_sandbox_flag(self, mock_run, monkeypatch, tmp_path):
        """У `codex exec resume` нет флага --sandbox (проверено на codex-cli 0.146.1).
        При передаче падает с unknown argument, поэтому добавлять его нельзя."""
        cmd, _ = self._run_with_resume(
            mock_run, monkeypatch, tmp_path, "019eeffd-ca63-7d00-b64e-2dacdd420385"
        )
        assert "--sandbox" not in cmd

    @patch("generate_image.subprocess.run")
    def test_without_resume_keeps_plain_exec_with_sandbox(self, mock_run, monkeypatch, tmp_path):
        cmd, _ = self._run_with_resume(mock_run, monkeypatch, tmp_path, None)
        assert "resume" not in cmd
        assert "--sandbox" in cmd

    @patch("generate_image.subprocess.run")
    def test_resume_adds_style_continuity_directive_to_prompt(
        self, mock_run, monkeypatch, tmp_path
    ):
        """В промпт на stdin попадает указание наследовать стиль, но не копировать композицию."""
        self._run_with_resume(
            mock_run, monkeypatch, tmp_path, "019eeffd-ca63-7d00-b64e-2dacdd420385"
        )
        sent = mock_run.call_args.kwargs["input"]
        assert "тот же визуальный стиль" in sent
        assert "композицию, объект и текст не копируй" in sent

    @patch("generate_image.subprocess.run")
    def test_session_id_recorded_in_metadata(self, mock_run, monkeypatch, tmp_path):
        sid = "019eeffd-ca63-7d00-b64e-2dacdd420385"
        _, result = self._run_with_resume(mock_run, monkeypatch, tmp_path, sid)
        meta = json.loads(Path(result + ".json").read_text(encoding="utf-8"))
        assert meta["codex_session_id"] == sid


class TestCodexAspectRetry:
    """Пропорция на бэкенде codex: у встроенного image_gen нет параметра размера,
    поэтому кадр сверяется по факту и при промахе генерируется заново."""

    @staticmethod
    def _png(w: int, h: int) -> bytes:
        """Собирает PNG-заголовок с заданными размерами.

        Полноценный PNG не нужен: код читает только IHDR, а тесты не открывают файл
        как изображение.
        """
        return (
            b"\x89PNG\r\n\x1a\n"
            + (13).to_bytes(4, "big")
            + b"IHDR"
            + w.to_bytes(4, "big")
            + h.to_bytes(4, "big")
            + b"\x08\x06\x00\x00\x00"
        )

    def _setup(self, monkeypatch, tmp_path, *sizes):
        """Подсовывает последовательность кадров: по одному на каждую попытку.
        Последний повторяется, если попыток окажется больше."""
        made = []

        def _fake(since):
            w, h = sizes[min(len(made), len(sizes) - 1)]
            p = tmp_path / f"ig_{len(made)}.png"
            p.write_bytes(self._png(w, h))
            made.append(p)
            return p

        monkeypatch.setattr("generate_image._find_latest_codex_image", _fake)
        return made

    def test_png_dimensions_reads_header(self, tmp_path):
        from generate_image import _png_dimensions

        p = tmp_path / "x.png"
        p.write_bytes(self._png(1086, 1448))
        assert _png_dimensions(p) == (1086, 1448)

    def test_png_dimensions_returns_none_for_non_png(self, tmp_path):
        from generate_image import _png_dimensions

        p = tmp_path / "x.png"
        p.write_bytes(b"not a png at all, just some bytes here")
        assert _png_dimensions(p) is None

    @patch("generate_image.subprocess.run")
    def test_correct_aspect_generates_once(self, mock_run, monkeypatch, tmp_path):
        """1086x1448 — это ровно 3:4, как и запрошенные 1200x1600. Повтора быть не должно."""
        self._setup(monkeypatch, tmp_path, (1086, 1448))
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        result = generate_image(
            prompt="x", backend="codex", size="1200x1600",
            output_dir=str(tmp_path / "out"), output_name="a",
        )
        assert result is not None
        assert mock_run.call_count == 1

    @patch("generate_image.subprocess.run")
    def test_wrong_aspect_retries_until_correct(self, mock_run, monkeypatch, tmp_path):
        """Первый кадр 1003x1568 (мимо), второй 1086x1448 (в цель) — двух вызовов достаточно."""
        self._setup(monkeypatch, tmp_path, (1003, 1568), (1086, 1448))
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        result = generate_image(
            prompt="x", backend="codex", size="1200x1600",
            output_dir=str(tmp_path / "out"), output_name="a",
        )
        assert result is not None
        assert mock_run.call_count == 2

    @patch("generate_image.subprocess.run")
    def test_retry_hint_reaches_agent_on_second_attempt(
        self, mock_run, monkeypatch, tmp_path
    ):
        """Во второй попытке агенту сообщается, что вышло в прошлый раз и что нужно."""
        self._setup(monkeypatch, tmp_path, (1003, 1568), (1086, 1448))
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        generate_image(
            prompt="x", backend="codex", size="1200x1600",
            output_dir=str(tmp_path / "out"), output_name="a",
        )
        first = mock_run.call_args_list[0].kwargs["input"]
        second = mock_run.call_args_list[1].kwargs["input"]
        assert "1003x1568" not in first
        assert "1003x1568" in second
        assert "3:4" in second

    @patch("generate_image.subprocess.run")
    def test_retries_are_bounded_and_last_frame_kept(
        self, mock_run, monkeypatch, tmp_path, capsys
    ):
        """Если пропорция так и не пришла, картинку не выбрасываем — её ещё можно добить."""
        self._setup(monkeypatch, tmp_path, (1003, 1568))
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        result = generate_image(
            prompt="x", backend="codex", size="1200x1600", aspect_retries=2,
            output_dir=str(tmp_path / "out"), output_name="a",
        )
        assert result is not None
        assert Path(result).exists()
        assert mock_run.call_count == 3  # первая попытка плюс два повтора
        assert "-Pad" in capsys.readouterr().out

    @patch("generate_image.subprocess.run")
    def test_zero_retries_disables_check(self, mock_run, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path, (1003, 1568))
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        generate_image(
            prompt="x", backend="codex", size="1200x1600", aspect_retries=0,
            output_dir=str(tmp_path / "out"), output_name="a",
        )
        assert mock_run.call_count == 1

    @patch("generate_image.subprocess.run")
    def test_size_auto_never_retries(self, mock_run, monkeypatch, tmp_path):
        """При --size auto придираться не к чему: пропорцию никто не заказывал."""
        self._setup(monkeypatch, tmp_path, (1003, 1568))
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        generate_image(
            prompt="x", backend="codex", size="auto",
            output_dir=str(tmp_path / "out"), output_name="a",
        )
        assert mock_run.call_count == 1

    def test_cli_default_and_override(self):
        from generate_image import DEFAULT_ASPECT_RETRIES

        assert parse_args(["p"]).aspect_retries == DEFAULT_ASPECT_RETRIES
        assert parse_args(["p", "--aspect-retries", "0"]).aspect_retries == 0


class TestCodexSessionLogRecovery:
    """Поддержка нового Codex: codex exec не создаёт файл, а возвращает картинку
    inline-base64 в логе сессии. Если файла нет, b64 забирается из лога, декодируется
    и сохраняется."""

    def test_extract_codex_session_id(self):
        from generate_image import _extract_codex_session_id

        sid = "019eeffd-ca63-7d00-b64e-2dacdd420385"
        header = f"model: gpt-5.5\nsession id: {sid}\n--------"
        assert _extract_codex_session_id(header) == sid
        assert _extract_codex_session_id("no id here") is None
        assert _extract_codex_session_id("") is None

    def _write_session_log(self, sessions_root: Path, sid: str, *entries: dict) -> Path:
        d = sessions_root / "2026" / "06" / "23"
        d.mkdir(parents=True, exist_ok=True)
        log = d / f"rollout-2026-06-23T00-40-47-{sid}.jsonl"
        log.write_text(
            "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8"
        )
        return log

    @patch("generate_image.subprocess.run")
    def test_recovers_image_from_session_log_when_no_file(
        self, mock_run, monkeypatch, tmp_path
    ):
        sid = "019eeffd-ca63-7d00-b64e-2dacdd420385"
        sessions = tmp_path / "sessions"
        self._write_session_log(
            sessions,
            sid,
            {
                "type": "response_item",
                "payload": {
                    "type": "image_generation_call",
                    "result": DUMMY_PNG_B64,
                    "status": "generating",
                },
            },
        )
        monkeypatch.setattr("generate_image.CODEX_SESSIONS_DIR", sessions)
        # Старый путь с записью файла ничего не находит
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: None)
        mock_run.return_value = Mock(
            returncode=0, stdout=f"session id: {sid}\n", stderr=""
        )

        out_dir = tmp_path / "out"
        result = generate_image(
            prompt="a red circle",
            backend="codex",
            output_dir=str(out_dir),
            output_name="hero",
        )
        assert result is not None
        out = out_dir / "hero.png"
        assert out.exists()
        assert out.read_bytes() == base64.b64decode(DUMMY_PNG_B64)

    @patch("generate_image.subprocess.run")
    def test_prefers_completed_result_over_partial(
        self, mock_run, monkeypatch, tmp_path
    ):
        sid = "0190000d-ca63-7d00-b64e-2dacdd420999"
        partial_b64 = base64.b64encode(b"PARTIAL-not-final").decode()
        sessions = tmp_path / "sessions"
        self._write_session_log(
            sessions,
            sid,
            {"payload": {"type": "image_generation_call", "result": partial_b64,
                         "status": "generating"}},
            {"payload": {"type": "image_generation_call", "result": DUMMY_PNG_B64,
                         "status": "completed"}},
        )
        monkeypatch.setattr("generate_image.CODEX_SESSIONS_DIR", sessions)
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: None)
        mock_run.return_value = Mock(
            returncode=0, stdout=f"session id: {sid}\n", stderr=""
        )
        out_dir = tmp_path / "out"
        result = generate_image(
            prompt="x", backend="codex", output_dir=str(out_dir), output_name="z"
        )
        assert result is not None
        assert (out_dir / "z.png").read_bytes() == base64.b64decode(DUMMY_PNG_B64)

    @patch("generate_image.subprocess.run")
    def test_file_output_path_takes_precedence_over_log(
        self, mock_run, monkeypatch, tmp_path
    ):
        """Если файл от старого Codex найден, приоритет у него — обратная совместимость."""
        sid = "0190000d-ca63-7d00-b64e-2dacddffffff"
        fake = tmp_path / "ig_x.png"
        fake.write_bytes(base64.b64decode(DUMMY_PNG_B64))
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: fake)
        # В лог кладём другое содержимое — оно не должно быть использовано
        sessions = tmp_path / "sessions"
        self._write_session_log(
            sessions,
            sid,
            {"payload": {"type": "image_generation_call",
                         "result": base64.b64encode(b"SHOULD-NOT-BE-USED").decode(),
                         "status": "completed"}},
        )
        monkeypatch.setattr("generate_image.CODEX_SESSIONS_DIR", sessions)
        mock_run.return_value = Mock(
            returncode=0, stdout=f"session id: {sid}\n", stderr=""
        )
        out_dir = tmp_path / "out"
        result = generate_image(
            prompt="x", backend="codex", output_dir=str(out_dir), output_name="z"
        )
        assert result is not None
        assert (out_dir / "z.png").read_bytes() == base64.b64decode(DUMMY_PNG_B64)


class TestBackendDispatch:
    """Проверяет, что auto / api / codex уходят по правильному пути"""

    @patch("generate_image.subprocess.run")
    @patch("generate_image.OpenAI")
    def test_explicit_codex_does_not_call_openai(
        self, mock_openai_cls, mock_run, monkeypatch, tmp_path
    ):
        fake = tmp_path / "ig_x.png"
        fake.write_bytes(base64.b64decode(DUMMY_PNG_B64))
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: fake)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        generate_image(
            prompt="x", backend="codex", output_dir=str(tmp_path / "out")
        )
        mock_openai_cls.assert_not_called()

    @patch("generate_image.subprocess.run")
    @patch("generate_image.OpenAI")
    def test_explicit_api_does_not_call_codex(
        self, mock_openai_cls, mock_run, tmp_path
    ):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.return_value = _make_image_response()
        generate_image(
            prompt="x", backend="api", output_dir=str(tmp_path / "out")
        )
        mock_run.assert_not_called()
        client.images.generate.assert_called_once()

    @patch("generate_image.subprocess.run")
    @patch("generate_image.OpenAI")
    def test_auto_with_codex_available_uses_codex_first(
        self, mock_openai_cls, mock_run, monkeypatch, tmp_path
    ):
        monkeypatch.setattr("generate_image._codex_subscription_available", lambda: True)
        fake = tmp_path / "ig_x.png"
        fake.write_bytes(base64.b64decode(DUMMY_PNG_B64))
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: fake)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        generate_image(
            prompt="x", backend="auto", output_dir=str(tmp_path / "out")
        )
        mock_run.assert_called_once()
        mock_openai_cls.assert_not_called()


class TestBackendFallback:
    """При неудаче Codex происходит откат на API (режим auto и наличие ключа)"""

    @patch("generate_image.subprocess.run")
    @patch("generate_image.OpenAI")
    def test_auto_falls_back_to_api_when_codex_fails(
        self, mock_openai_cls, mock_run, monkeypatch, tmp_path, capsys
    ):
        monkeypatch.setattr("generate_image._codex_subscription_available", lambda: True)
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: None)
        # Откат возможен только при заданном ключе. Без этой строки тест зависел бы
        # от окружения машины и падал там, где ключа нет
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="rate limit")
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.return_value = _make_image_response()

        result = generate_image(
            prompt="x", backend="auto", output_dir=str(tmp_path / "out")
        )
        assert result is not None
        client.images.generate.assert_called_once()
        out = capsys.readouterr().out
        assert "fallback" in out.lower() or "откат" in out.lower()

    @patch("generate_image.subprocess.run")
    @patch("generate_image.OpenAI")
    def test_explicit_codex_does_not_fallback(
        self, mock_openai_cls, mock_run, monkeypatch, tmp_path
    ):
        """При явном `--backend codex` отката нет — осознанный выбор уважается"""
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: None)
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="boom")
        result = generate_image(
            prompt="x", backend="codex", output_dir=str(tmp_path / "out")
        )
        assert result is None
        mock_openai_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Free-form --size validation (issue #018)
# ---------------------------------------------------------------------------


class TestValidateSize:
    """Граничные значения validate_size(): кратность 16, сторона 3840, 3:1, число пикселей"""

    # --- Проходящие случаи ---
    def test_legacy_square_passes(self):
        assert validate_size("1024x1024") == (1024, 1024)

    def test_legacy_portrait_passes(self):
        assert validate_size("1024x1536") == (1024, 1536)

    def test_legacy_landscape_passes(self):
        assert validate_size("1536x1024") == (1536, 1024)

    def test_4k_landscape_upper_bound_passes(self):
        """3840x2160 = 8,294,400 — ровно верхняя граница по числу пикселей"""
        assert validate_size("3840x2160") == (3840, 2160)

    def test_4k_portrait_passes(self):
        assert validate_size("2160x3840") == (2160, 3840)

    def test_total_pixels_lower_bound_passes(self):
        """1024x640 = 655,360 — ровно нижняя граница по числу пикселей"""
        assert validate_size("1024x640") == (1024, 640)

    def test_aspect_ratio_exactly_3to1_passes(self):
        """Ровно 3:1 допустимо, отсекается только > 3.0. 1536x512 = 3.0:1, всего 786,432"""
        assert validate_size("1536x512") == (1536, 512)

    # --- Нарушающие случаи ---
    def test_non_wxh_format_raises(self):
        with pytest.raises(ValueError):
            validate_size("1024")

    def test_garbage_format_raises(self):
        with pytest.raises(ValueError):
            validate_size("abc")

    def test_not_multiple_of_16_raises(self):
        with pytest.raises(ValueError, match="16"):
            validate_size("1000x1000")

    def test_height_not_multiple_of_16_raises(self):
        with pytest.raises(ValueError, match="16"):
            validate_size("1024x1000")

    def test_max_side_over_3840_raises(self):
        with pytest.raises(ValueError, match="3840"):
            validate_size("4096x1024")

    def test_aspect_ratio_over_3to1_raises(self):
        """3840x1024 = 3.75:1"""
        with pytest.raises(ValueError, match="3:1|соотношение"):
            validate_size("3840x1024")

    def test_total_pixels_below_lower_bound_raises(self):
        """512x512 = 262,144 < 655,360"""
        with pytest.raises(ValueError, match="655,360|пикс"):
            validate_size("512x512")

    def test_total_pixels_above_upper_bound_raises(self):
        """3840x2176 = 8,355,840 > 8,294,400 (кратность 16, сторона и пропорция в норме)"""
        with pytest.raises(ValueError, match="8,294,400|пикс"):
            validate_size("3840x2176")


class TestSizeFreeInputParsing:
    """argparse не режет значения через choices и принимает произвольный WxH"""

    def test_arbitrary_size_accepted_by_parser(self):
        args = parse_args(["p", "--size", "3840x2160"])
        assert args.size == "3840x2160"

    def test_legacy_size_still_accepted(self):
        args = parse_args(["p", "--size", "1024x1536"])
        assert args.size == "1024x1536"

    def test_auto_still_accepted(self):
        args = parse_args(["p", "--size", "auto"])
        assert args.size == "auto"


class TestSizeValidationIntegration:
    """Интеграция валидации в main() и generate_image()"""

    def _run_main(self, argv: list[str]) -> int | None:
        with patch.object(sys, "argv", ["generate_image.py", *argv]):
            try:
                main()
            except SystemExit as e:
                return e.code
        return None

    def test_main_rejects_invalid_size_exit_2(self, capsys):
        code = self._run_main(["p", "--size", "1000x1000"])
        assert code == 2
        assert "16" in capsys.readouterr().out

    @patch("generate_image.generate_image")
    def test_main_passes_valid_4k_through(self, mock_gen):
        mock_gen.return_value = "/tmp/fake.png"
        code = self._run_main(["p", "--size", "3840x2160", "--backend", "api"])
        assert code is None
        assert mock_gen.call_args.kwargs["size"] == "3840x2160"

    def test_generate_image_returns_none_on_invalid_size(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_image(prompt="x", size="1000x1000", output_dir=tmp, backend="api")
        assert result is None
        assert "16" in capsys.readouterr().out

    @patch("generate_image.subprocess.run")
    def test_codex_warns_size_not_guaranteed(self, mock_run, monkeypatch, tmp_path, capsys):
        fake = tmp_path / "ig_x.png"
        fake.write_bytes(base64.b64decode(DUMMY_PNG_B64))
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: fake)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        generate_image(
            prompt="x", size="3840x2160", backend="codex", output_dir=str(tmp_path / "out")
        )
        out = capsys.readouterr().out
        assert "[Warning]" in out
        assert "Codex" in out and "не соблюдает размер" in out


# ---------------------------------------------------------------------------
# Галерея (issue #024 / ccskill-gallery store-spec v1.0)
# ---------------------------------------------------------------------------


class TestGalleryDir:
    """Тесты определения пути к галерее"""

    def test_default_gallery_dir(self, monkeypatch):
        """По умолчанию — ~/.ccskill-gptimage/gallery"""
        monkeypatch.delenv(GALLERY_DIR_ENV, raising=False)
        assert get_gallery_dir() == Path.home() / ".ccskill-gptimage" / "gallery"

    def test_env_override(self, monkeypatch):
        """Путь к галерее меняется переменной окружения"""
        monkeypatch.setenv(GALLERY_DIR_ENV, "/custom/path/gallery")
        assert get_gallery_dir() == Path("/custom/path/gallery")


class TestOutputFormatToMime:
    def test_png(self):
        assert OUTPUT_FORMAT_TO_MIME["png"] == "image/png"

    def test_jpeg(self):
        assert OUTPUT_FORMAT_TO_MIME["jpeg"] == "image/jpeg"

    def test_webp(self):
        assert OUTPUT_FORMAT_TO_MIME["webp"] == "image/webp"


class TestStoreInGallery:
    """Тесты накопления в галерее (по store-spec v1.0)"""

    def _make_image(self, tmpdir: Path, name: str = "20260702_120000.png") -> Path:
        image_path = tmpdir / name
        image_path.write_bytes(b"fake-image-data")
        return image_path

    def _meta(self, prompt="тест") -> dict:
        return {
            "model": DEFAULT_MODEL,
            "prompt": prompt,
            "size": "1024x1024",
            "quality": "auto",
            "background": "auto",
            "output_format": "png",
            "mime_type": "image/png",
            "moderation": "auto",
            "reference_images": [],
            "mask": None,
            "input_fidelity": None,
            "revised_prompt": None,
            "backend": "api",
            "timestamp": "2026-07-02T12:00:00",
        }

    def test_image_and_sidecar_copied_to_store(self, tmp_path):
        """Картинка и JSON с метаданными копируются в галерею"""
        image_path = self._make_image(tmp_path)
        store_in_gallery(image_path, self._meta())

        gallery = get_gallery_dir()
        stored_image = gallery / "images" / image_path.name
        assert stored_image.exists()
        assert stored_image.read_bytes() == b"fake-image-data"
        assert (gallery / "images" / (image_path.name + ".json")).exists()

    def test_index_entry_has_required_keys(self, tmp_path):
        """В записи index.json есть обязательные ключи store-spec: file/prompt/mime_type/timestamp"""
        image_path = self._make_image(tmp_path)
        store_in_gallery(image_path, self._meta("закат"))

        index = json.loads(
            (get_gallery_dir() / "index.json").read_text(encoding="utf-8")
        )
        assert len(index["entries"]) == 1
        entry = index["entries"][0]
        assert entry["file"] == f"images/{image_path.name}"
        assert entry["prompt"] == "закат"
        assert entry["mime_type"] == "image/png"
        assert entry["timestamp"] == "2026-07-02T12:00:00"
        assert entry["model"] == DEFAULT_MODEL
        assert "project_dir" in entry

    def test_multiple_entries_accumulate(self, tmp_path):
        """Записи накапливаются при повторных генерациях"""
        img1 = self._make_image(tmp_path, "20260702_120000.png")
        img2 = self._make_image(tmp_path, "20260702_120100.png")
        store_in_gallery(img1, self._meta("первая"))
        store_in_gallery(img2, self._meta("вторая"))

        index = json.loads(
            (get_gallery_dir() / "index.json").read_text(encoding="utf-8")
        )
        assert len(index["entries"]) == 2

    def test_name_collision_gets_unique_name(self, tmp_path):
        """Если файл с таким именем уже есть, сохраняется под уникальным именем"""
        img = self._make_image(tmp_path)
        store_in_gallery(img, self._meta())
        store_in_gallery(img, self._meta())

        index = json.loads(
            (get_gallery_dir() / "index.json").read_text(encoding="utf-8")
        )
        assert len(index["entries"]) == 2
        files = [e["file"] for e in index["entries"]]
        assert len(set(files)) == 2  # имена не повторяются

    def test_corrupt_index_rebuilt_from_sidecars(self, tmp_path):
        """При повреждении index.json он пересобирается по сайдкарам в галерее"""
        img1 = self._make_image(tmp_path, "20260702_120000.png")
        store_in_gallery(img1, self._meta("старая"))

        index_path = get_gallery_dir() / "index.json"
        index_path.write_text("{ broken json", encoding="utf-8")

        img2 = self._make_image(tmp_path, "20260702_120100.png")
        store_in_gallery(img2, self._meta("новая"))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        prompts = {e["prompt"] for e in index["entries"]}
        assert prompts == {"старая", "новая"}


class TestGenerateImageStoresGallery:
    """generate_image() складывает результат в галерею — оба пути, API и Codex"""

    @patch("generate_image.OpenAI")
    def test_api_backend_stores_to_gallery(self, mock_openai_cls, tmp_path):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.return_value = _make_image_response()

        result = generate_image(
            prompt="тест галереи", output_dir=str(tmp_path / "out"), backend="api"
        )

        assert result is not None
        gallery = get_gallery_dir()
        index = json.loads((gallery / "index.json").read_text(encoding="utf-8"))
        assert len(index["entries"]) == 1
        entry = index["entries"][0]
        assert entry["prompt"] == "тест галереи"
        assert entry["mime_type"] == "image/png"
        assert (gallery / entry["file"]).exists()

    @patch("generate_image.subprocess.run")
    def test_codex_backend_stores_to_gallery(self, mock_run, monkeypatch, tmp_path):
        fake = tmp_path / "ig_x.png"
        fake.write_bytes(base64.b64decode(DUMMY_PNG_B64))
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: fake)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        result = generate_image(
            prompt="codex тест галереи", backend="codex", output_dir=str(tmp_path / "out")
        )

        assert result is not None
        gallery = get_gallery_dir()
        index = json.loads((gallery / "index.json").read_text(encoding="utf-8"))
        assert len(index["entries"]) == 1
        assert index["entries"][0]["prompt"] == "codex тест галереи"
        assert index["entries"][0]["backend"] == "codex"

    @patch("generate_image.OpenAI")
    def test_store_failure_does_not_break_generation(self, mock_openai_cls, monkeypatch, tmp_path, capsys):
        """Сбой записи в галерею не отменяет успешную генерацию изображения"""
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.return_value = _make_image_response()

        def _raise(*args, **kwargs):
            raise OSError("store failed")

        monkeypatch.setattr("generate_image.store_in_gallery", _raise)

        result = generate_image(prompt="x", output_dir=str(tmp_path / "out"), backend="api")

        assert result is not None
        assert "[Warning]" in capsys.readouterr().out
