"""Тесты install.sh и диспетчера ccskill-gptimage (issue #020)

HOME подменяется на временный каталог, поэтому реальные ~/.local/bin
и ~/.claude/skills не затрагиваются.
pip install пропускается через CCSKILL_GPTIMAGE_INSTALL_SKIP_DEPS=1 —
диспетчер использует venv, уже собранный в репозитории.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).parent.parent
INSTALL_SH = REPO_DIR / "install.sh"
DISPATCHER = REPO_DIR / "ccskill-gptimage"


def _env(home: Path) -> dict:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["CCSKILL_GPTIMAGE_INSTALL_SKIP_DEPS"] = "1"
    return env


def _run_install(home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(INSTALL_SH), *args],
        capture_output=True,
        text=True,
        env=_env(home),
        cwd=REPO_DIR,
        timeout=120,
    )


def _run_dispatcher(home: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Запускает диспетчер через установленный symlink"""
    link = home / ".local/bin/ccskill-gptimage"
    return subprocess.run(
        [str(link), *args],
        capture_output=True,
        text=True,
        env=_env(home),
        cwd=cwd or home,
        timeout=120,
    )


@pytest.fixture
def installed_home(tmp_path: Path) -> Path:
    """Временный HOME с уже выполненным install.sh"""
    proc = _run_install(tmp_path)
    assert proc.returncode == 0, f"install.sh failed:\n{proc.stdout}\n{proc.stderr}"
    return tmp_path


class TestInstallScript:
    def test_install_exits_zero(self, tmp_path):
        proc = _run_install(tmp_path)
        assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"

    def test_creates_bin_symlink(self, installed_home):
        link = installed_home / ".local/bin/ccskill-gptimage"
        assert link.is_symlink()
        assert link.resolve() == DISPATCHER.resolve()

    def test_creates_user_skill_symlink(self, installed_home):
        link = installed_home / ".claude/skills/ccskill-gptimage"
        assert link.is_symlink()
        # SKILL.md разрешается через symlink, то есть Claude Code его увидит
        assert (link / "SKILL.md").is_file()
        assert link.resolve() == (REPO_DIR / ".claude/skills/ccskill-gptimage").resolve()

    def test_idempotent_rerun(self, installed_home):
        proc = _run_install(installed_home)
        assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        assert (installed_home / ".local/bin/ccskill-gptimage").is_symlink()
        assert (installed_home / ".claude/skills/ccskill-gptimage").is_symlink()

    def test_refuses_foreign_skill_dir(self, tmp_path):
        """Если на месте уже лежит обычный каталог без SKILL.md — ошибка, ничего не ломаем"""
        foreign = tmp_path / ".claude/skills/ccskill-gptimage"
        foreign.mkdir(parents=True)
        (foreign / "keep.txt").write_text("do not delete")
        proc = _run_install(tmp_path)
        assert proc.returncode != 0
        assert (foreign / "keep.txt").exists()

    def test_replaces_stale_skill_copy(self, tmp_path):
        """Обычный каталог с SKILL.md (след ручного копирования) заменяется на symlink"""
        stale = tmp_path / ".claude/skills/ccskill-gptimage"
        stale.mkdir(parents=True)
        (stale / "SKILL.md").write_text("# old copy")
        proc = _run_install(tmp_path)
        assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        link = tmp_path / ".claude/skills/ccskill-gptimage"
        assert link.is_symlink()


class TestDispatcher:
    def test_version_exits_zero(self, installed_home):
        proc = _run_dispatcher(installed_home, "version")
        assert proc.returncode == 0
        assert "ccskill-gptimage" in proc.stdout

    def test_help_lists_subcommands(self, installed_home):
        proc = _run_dispatcher(installed_home, "help")
        assert proc.returncode == 0
        for sub in ("generate", "uninstall", "version", "help"):
            assert sub in proc.stdout

    def test_no_args_shows_help(self, installed_home):
        proc = _run_dispatcher(installed_home)
        assert proc.returncode == 0
        assert "generate" in proc.stdout

    def test_unknown_command_fails(self, installed_home):
        proc = _run_dispatcher(installed_home, "nosuchcommand")
        assert proc.returncode != 0

    def test_generate_wires_to_python_validation(self, installed_home, tmp_path):
        """generate добирается до самого скрипта из другого каталога.
        Неверный размер отсекается до вызова API: exit 2 и текст ошибки, без списаний"""
        workdir = tmp_path / "elsewhere"
        workdir.mkdir(parents=True, exist_ok=True)
        proc = _run_dispatcher(
            installed_home, "generate", "test prompt", "--size", "1000x1000",
            cwd=workdir,
        )
        assert proc.returncode == 2
        assert "16" in proc.stdout

    def test_generate_help_passthrough(self, installed_home):
        proc = _run_dispatcher(installed_home, "generate", "--help")
        assert proc.returncode == 0
        assert "--size" in proc.stdout


class TestUninstall:
    def test_uninstall_removes_symlinks(self, installed_home):
        proc = _run_dispatcher(installed_home, "uninstall")
        assert proc.returncode == 0
        assert not (installed_home / ".local/bin/ccskill-gptimage").exists()
        assert not (installed_home / ".claude/skills/ccskill-gptimage").exists()

    def test_uninstall_keeps_repo_intact(self, installed_home):
        _run_dispatcher(installed_home, "uninstall")
        assert DISPATCHER.exists()
        assert (REPO_DIR / ".claude/skills/ccskill-gptimage/SKILL.md").exists()
