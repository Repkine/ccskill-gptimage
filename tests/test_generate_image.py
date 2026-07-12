"""ccskill-gptimage 画像生成スクリプトのテスト"""

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


# 1x1 透過 PNG の base64(モック用)
DUMMY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgAAIAAAUAAeImBZsAAAAASUVORK5CYII="
)


def _make_image_response(b64: str = DUMMY_PNG_B64, revised_prompt: str | None = None) -> Mock:
    """OpenAI Images API の擬似レスポンスを作る"""
    datum = Mock()
    datum.b64_json = b64
    datum.revised_prompt = revised_prompt
    response = Mock()
    response.data = [datum]
    return response


@pytest.fixture(autouse=True)
def _force_api_backend(request, monkeypatch):
    """既存テストは Codex を使わない前提に固定する。
    backend 検出ロジックそのものをテストする場合は @pytest.mark.no_force_api_backend で opt-out。"""
    if request.node.get_closest_marker("no_force_api_backend"):
        return
    monkeypatch.setattr("generate_image._codex_subscription_available", lambda: False)


@pytest.fixture(autouse=True)
def _isolate_gallery(tmp_path, monkeypatch):
    """テストが実ユーザのギャラリーストア(~/.ccskill-gptimage/gallery)に触れないよう隔離する"""
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
            # opaque/auto の場合は background パラメータは送らない
            assert "background" not in kwargs or kwargs["background"] != "transparent"
            # ファイルが実際に書き出されている
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
        # image は file-like のリスト or 単体
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
        # 複数枚はリストで渡す
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
        assert "参照画像が見つかりません" in captured.out


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
    """`_codex_subscription_available()` 自身の挙動。
    autouse fixture を opt-out して実関数を呼ぶ。"""

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
        """codex も key も無い場合でも api を返し、後段の OpenAI() で native エラーに任せる"""
        monkeypatch.setattr("generate_image._codex_subscription_available", lambda: False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert _resolve_backend("auto") == "api"


class TestGenerateViaCodex:
    """Codex backend 経由の生成ロジック。subprocess と画像探索をモックする"""

    @patch("generate_image.subprocess.run")
    def test_codex_subprocess_args_have_prompt_before_image(
        self, mock_run, monkeypatch, tmp_path
    ):
        """`-i` は variadic で後続 positional を食う罠を回避するため、prompt は -i より前"""
        # 生成画像をでっち上げ
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
        # prompt は positional の 1 つ、`-i` ペアより前にあること
        assert "codex" in cmd[0]
        assert "exec" in cmd
        assert "-i" in cmd
        i_idx = cmd.index("-i")
        # `-i` の直前は引数フラグ系 (--sandbox の値) or プロンプト文字列。
        # 重要なのはプロンプト文字列が `-i` より前にあること。
        # -i の引数 (ref.png 絶対パス) は -i の直後
        assert cmd[i_idx + 1] == str(ref)
        # prompt が -i より前のどこかにある
        prompt_indices = [k for k, v in enumerate(cmd) if "add a red beret" in v]
        assert prompt_indices, "prompt not found in command"
        assert max(prompt_indices) < i_idx

    @patch("generate_image.subprocess.run")
    def test_codex_includes_image_gen_directive_in_prompt(
        self, mock_run, monkeypatch, tmp_path
    ):
        """API 経由を防ぐため『image_gen を直接使え』ディレクティブを必ず含める"""
        fake = tmp_path / "ig_x.png"
        fake.write_bytes(base64.b64decode(DUMMY_PNG_B64))
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: fake)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        generate_image(
            prompt="hello",
            backend="codex",
            output_dir=str(tmp_path / "out"),
        )
        cmd = mock_run.call_args[0][0]
        # cmd の中に Codex agent 向けプロンプトがあり、そこに image_gen の指示が含まれる
        joined = " ".join(cmd)
        assert "image_gen" in joined

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
        # セッションログ回収フォールバックも空にする(実環境の ~/.codex/sessions を拾わない)
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


class TestCodexSessionLogRecovery:
    """新しい Codex (codex exec が画像をファイル化せず、セッションログに inline base64 で返す)
    への対応。ファイルが見つからないとき、ログから b64 を回収してデコード保存できること。"""

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
        # 旧来のファイル出力経路は見つからない
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
        """旧 Codex のファイル出力が見つかる場合はそちらを優先(後方互換)。"""
        sid = "0190000d-ca63-7d00-b64e-2dacddffffff"
        fake = tmp_path / "ig_x.png"
        fake.write_bytes(base64.b64decode(DUMMY_PNG_B64))
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: fake)
        # ログ側には別物を置いておく(使われないはず)
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
    """auto / api / codex 切替時に正しい経路に行くか"""

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
    """Codex が失敗したら API にフォールバック(auto モードかつ key あり)"""

    @patch("generate_image.subprocess.run")
    @patch("generate_image.OpenAI")
    def test_auto_falls_back_to_api_when_codex_fails(
        self, mock_openai_cls, mock_run, monkeypatch, tmp_path, capsys
    ):
        monkeypatch.setattr("generate_image._codex_subscription_available", lambda: True)
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: None)
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
        assert "fallback" in out.lower() or "フォールバック" in out

    @patch("generate_image.subprocess.run")
    @patch("generate_image.OpenAI")
    def test_explicit_codex_does_not_fallback(
        self, mock_openai_cls, mock_run, monkeypatch, tmp_path
    ):
        """`--backend codex` 明示時はフォールバックしない(意図的選択を尊重)"""
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
    """validate_size() の境界値挙動。4 制約(16 の倍数 / 最大辺 3840 / 3:1 / 総ピクセル)"""

    # --- 合格ケース ---
    def test_legacy_square_passes(self):
        assert validate_size("1024x1024") == (1024, 1024)

    def test_legacy_portrait_passes(self):
        assert validate_size("1024x1536") == (1024, 1536)

    def test_legacy_landscape_passes(self):
        assert validate_size("1536x1024") == (1536, 1024)

    def test_4k_landscape_upper_bound_passes(self):
        """3840x2160 = 8,294,400 = 総ピクセル上限ちょうど"""
        assert validate_size("3840x2160") == (3840, 2160)

    def test_4k_portrait_passes(self):
        assert validate_size("2160x3840") == (2160, 3840)

    def test_total_pixels_lower_bound_passes(self):
        """1024x640 = 655,360 = 総ピクセル下限ちょうど"""
        assert validate_size("1024x640") == (1024, 640)

    def test_aspect_ratio_exactly_3to1_passes(self):
        """3:1 ちょうどは許容(> 3.0 のみ弾く)。1536x512 = 3.0:1, total=786,432"""
        assert validate_size("1536x512") == (1536, 512)

    # --- 違反ケース ---
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
        with pytest.raises(ValueError, match="3:1|アスペクト"):
            validate_size("3840x1024")

    def test_total_pixels_below_lower_bound_raises(self):
        """512x512 = 262,144 < 655,360"""
        with pytest.raises(ValueError, match="655,360|総ピクセル"):
            validate_size("512x512")

    def test_total_pixels_above_upper_bound_raises(self):
        """3840x2176 = 8,355,840 > 8,294,400(16 の倍数・最大辺・比は OK)"""
        with pytest.raises(ValueError, match="8,294,400|総ピクセル"):
            validate_size("3840x2176")


class TestSizeFreeInputParsing:
    """argparse が choices で弾かず、任意 WxH を受け取れること"""

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
    """main() / generate_image() へのバリデーション統合"""

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
        assert "Codex" in out and ("保証" in out or "warn" in out.lower())


# ---------------------------------------------------------------------------
# ギャラリーストア (issue #024 / ccskill-gallery store-spec v1.0)
# ---------------------------------------------------------------------------


class TestGalleryDir:
    """ギャラリーストアのパス解決テスト"""

    def test_default_gallery_dir(self, monkeypatch):
        """デフォルトは ~/.ccskill-gptimage/gallery"""
        monkeypatch.delenv(GALLERY_DIR_ENV, raising=False)
        assert get_gallery_dir() == Path.home() / ".ccskill-gptimage" / "gallery"

    def test_env_override(self, monkeypatch):
        """環境変数でストアのパスを変更できる"""
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
    """ギャラリーストア蓄積のテスト(store-spec v1.0 準拠)"""

    def _make_image(self, tmpdir: Path, name: str = "20260702_120000.png") -> Path:
        image_path = tmpdir / name
        image_path.write_bytes(b"fake-image-data")
        return image_path

    def _meta(self, prompt="テスト") -> dict:
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
        """画像とメタデータJSONがストアへコピーされる"""
        image_path = self._make_image(tmp_path)
        store_in_gallery(image_path, self._meta())

        gallery = get_gallery_dir()
        stored_image = gallery / "images" / image_path.name
        assert stored_image.exists()
        assert stored_image.read_bytes() == b"fake-image-data"
        assert (gallery / "images" / (image_path.name + ".json")).exists()

    def test_index_entry_has_required_keys(self, tmp_path):
        """index.json のエントリに store-spec 必須キー(file/prompt/mime_type/timestamp)が揃う"""
        image_path = self._make_image(tmp_path)
        store_in_gallery(image_path, self._meta("夕焼け"))

        index = json.loads(
            (get_gallery_dir() / "index.json").read_text(encoding="utf-8")
        )
        assert len(index["entries"]) == 1
        entry = index["entries"][0]
        assert entry["file"] == f"images/{image_path.name}"
        assert entry["prompt"] == "夕焼け"
        assert entry["mime_type"] == "image/png"
        assert entry["timestamp"] == "2026-07-02T12:00:00"
        assert entry["model"] == DEFAULT_MODEL
        assert "project_dir" in entry

    def test_multiple_entries_accumulate(self, tmp_path):
        """複数回の生成でエントリが蓄積される"""
        img1 = self._make_image(tmp_path, "20260702_120000.png")
        img2 = self._make_image(tmp_path, "20260702_120100.png")
        store_in_gallery(img1, self._meta("1枚目"))
        store_in_gallery(img2, self._meta("2枚目"))

        index = json.loads(
            (get_gallery_dir() / "index.json").read_text(encoding="utf-8")
        )
        assert len(index["entries"]) == 2

    def test_name_collision_gets_unique_name(self, tmp_path):
        """同名ファイルが既にストアにある場合は一意な名前で保存される"""
        img = self._make_image(tmp_path)
        store_in_gallery(img, self._meta())
        store_in_gallery(img, self._meta())

        index = json.loads(
            (get_gallery_dir() / "index.json").read_text(encoding="utf-8")
        )
        assert len(index["entries"]) == 2
        files = [e["file"] for e in index["entries"]]
        assert len(set(files)) == 2  # 重複しない

    def test_corrupt_index_rebuilt_from_sidecars(self, tmp_path):
        """index.json 破損時はストア内のサイドカーから再構築される"""
        img1 = self._make_image(tmp_path, "20260702_120000.png")
        store_in_gallery(img1, self._meta("既存"))

        index_path = get_gallery_dir() / "index.json"
        index_path.write_text("{ broken json", encoding="utf-8")

        img2 = self._make_image(tmp_path, "20260702_120100.png")
        store_in_gallery(img2, self._meta("新規"))

        index = json.loads(index_path.read_text(encoding="utf-8"))
        prompts = {e["prompt"] for e in index["entries"]}
        assert prompts == {"既存", "新規"}


class TestGenerateImageStoresGallery:
    """generate_image() がギャラリーへ蓄積するテスト(API/Codex 両経路)"""

    @patch("generate_image.OpenAI")
    def test_api_backend_stores_to_gallery(self, mock_openai_cls, tmp_path):
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.return_value = _make_image_response()

        result = generate_image(
            prompt="蓄積テスト", output_dir=str(tmp_path / "out"), backend="api"
        )

        assert result is not None
        gallery = get_gallery_dir()
        index = json.loads((gallery / "index.json").read_text(encoding="utf-8"))
        assert len(index["entries"]) == 1
        entry = index["entries"][0]
        assert entry["prompt"] == "蓄積テスト"
        assert entry["mime_type"] == "image/png"
        assert (gallery / entry["file"]).exists()

    @patch("generate_image.subprocess.run")
    def test_codex_backend_stores_to_gallery(self, mock_run, monkeypatch, tmp_path):
        fake = tmp_path / "ig_x.png"
        fake.write_bytes(base64.b64decode(DUMMY_PNG_B64))
        monkeypatch.setattr("generate_image._find_latest_codex_image", lambda since: fake)
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        result = generate_image(
            prompt="codex蓄積テスト", backend="codex", output_dir=str(tmp_path / "out")
        )

        assert result is not None
        gallery = get_gallery_dir()
        index = json.loads((gallery / "index.json").read_text(encoding="utf-8"))
        assert len(index["entries"]) == 1
        assert index["entries"][0]["prompt"] == "codex蓄積テスト"
        assert index["entries"][0]["backend"] == "codex"

    @patch("generate_image.OpenAI")
    def test_store_failure_does_not_break_generation(self, mock_openai_cls, monkeypatch, tmp_path, capsys):
        """ストアへの蓄積が失敗しても画像生成自体は成功として返る"""
        client = Mock()
        mock_openai_cls.return_value = client
        client.images.generate.return_value = _make_image_response()

        def _raise(*args, **kwargs):
            raise OSError("store failed")

        monkeypatch.setattr("generate_image.store_in_gallery", _raise)

        result = generate_image(prompt="x", output_dir=str(tmp_path / "out"), backend="api")

        assert result is not None
        assert "[Warning]" in capsys.readouterr().out
