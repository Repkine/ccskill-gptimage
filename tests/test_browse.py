"""ccskill-gptimage browse サブコマンドのテスト (issue #024)

browse は自前の閲覧UIを実装せず、ccskill-gallery へ委譲する。
ccskill-gallery が未導入の環境ではエラーにせず(exit 0)案内を表示する。
"""

import os
import subprocess
from pathlib import Path

REPO_DIR = Path(__file__).parent.parent
DISPATCHER = REPO_DIR / "ccskill-gptimage"

# ccskill-gallery を含まない最小 PATH(coreutils は要る)
MINIMAL_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def _env(home: Path, path: str) -> dict:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["PATH"] = path
    return env


def _run_browse(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(DISPATCHER), "browse", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_DIR,
        timeout=30,
    )


def _make_fake_ccskill_gallery(tmp_path: Path) -> Path:
    """PATH 上に置く偽 ccskill-gallery。渡された引数をそのまま出力して終了する"""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    fake = bin_dir / "ccskill-gallery"
    fake.write_text("#!/bin/bash\necho \"CALLED_WITH:$@\"\n")
    fake.chmod(0o755)
    return bin_dir


class TestBrowseWithoutCcskillGallery:
    def test_exits_zero_with_guidance(self, tmp_path):
        proc = _run_browse(_env(tmp_path, MINIMAL_PATH))
        assert proc.returncode == 0
        assert "ccskill-gallery" in proc.stdout

    def test_mentions_gallery_store_path(self, tmp_path):
        proc = _run_browse(_env(tmp_path, MINIMAL_PATH))
        assert ".ccskill-gptimage/gallery" in proc.stdout

    def test_respects_gallery_dir_env_override_in_guidance(self, tmp_path):
        env = _env(tmp_path, MINIMAL_PATH)
        env["CCSKILL_GPTIMAGE_GALLERY_DIR"] = "/custom/gallery"
        proc = _run_browse(env)
        assert proc.returncode == 0
        assert "/custom/gallery" in proc.stdout


class TestBrowseWithCcskillGallery:
    def test_delegates_to_ccskill_gallery(self, tmp_path):
        bin_dir = _make_fake_ccskill_gallery(tmp_path)
        proc = _run_browse(_env(tmp_path, f"{bin_dir}:{MINIMAL_PATH}"))
        assert proc.returncode == 0
        assert "CALLED_WITH:browse" in proc.stdout

    def test_passes_through_options(self, tmp_path):
        bin_dir = _make_fake_ccskill_gallery(tmp_path)
        proc = _run_browse(
            _env(tmp_path, f"{bin_dir}:{MINIMAL_PATH}"), "--port", "9000", "--no-open"
        )
        assert proc.returncode == 0
        assert "CALLED_WITH:browse --port 9000 --no-open" in proc.stdout
