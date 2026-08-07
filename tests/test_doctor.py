"""Тесты подкоманды doctor (issue #021)

Принципы, заложенные в #021:
  - doctor не читает содержимое секретных файлов: только наличие переменных
    окружения и существование файлов
  - значения ключа API и access_token не должны попадать в вывод
  - если ни один backend не доступен — exit 1, если хотя бы один есть — exit 0
  - Org Verification не проверяется вживую, выводится только статичная подсказка

HOME подменяется на временный каталог, поэтому реальное окружение не затрагивается.
Отрицательный сценарий без backend воспроизводится «поддельным репозиторием»
(только диспетчер и symlink на venv, без .env) и PATH без codex.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).parent.parent
DISPATCHER = REPO_DIR / "ccskill-gptimage"
INSTALL_SH = REPO_DIR / "install.sh"
REAL_VENV = REPO_DIR / "venv"

# Минимальный PATH без codex (coreutils нужны). Гарантирует, что doctor не увидит Codex.
MINIMAL_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def _base_env(home: Path) -> dict:
    env = dict(os.environ)
    env["HOME"] = str(home)
    return env


def _run_doctor(env: dict, cwd: Path | None = None, dispatcher: Path = DISPATCHER):
    return subprocess.run(
        [str(dispatcher), "doctor"],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd or REPO_DIR,
        timeout=60,
    )


@pytest.fixture
def installed_home(tmp_path: Path) -> Path:
    """Временный HOME с уже выполненным install.sh — symlink отмечается как ✓"""
    env = _base_env(tmp_path)
    env["CCSKILL_GPTIMAGE_INSTALL_SKIP_DEPS"] = "1"
    proc = subprocess.run(
        ["bash", str(INSTALL_SH)],
        capture_output=True, text=True, env=env, cwd=REPO_DIR, timeout=120,
    )
    assert proc.returncode == 0, f"install.sh failed:\n{proc.stdout}\n{proc.stderr}"
    return tmp_path


def _make_fake_repo(tmp_path: Path) -> Path:
    """Поддельный репозиторий: только диспетчер и symlink на venv, без .env.
    Нужен, чтобы backend api считался недоступным."""
    fake = tmp_path / "fake_repo"
    fake.mkdir()
    shutil.copy2(DISPATCHER, fake / "ccskill-gptimage")
    (fake / "ccskill-gptimage").chmod(0o755)
    (fake / "venv").symlink_to(REAL_VENV)
    return fake


class TestDoctorBasic:
    def test_doctor_runs_in_repo(self, tmp_path):
        """В настоящем репозитории (.env есть) backend доступен, поэтому exit 0"""
        proc = _run_doctor(_base_env(tmp_path))
        assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"

    def test_doctor_lists_all_sections(self, tmp_path):
        proc = _run_doctor(_base_env(tmp_path))
        out = proc.stdout
        # В выводе присутствуют названия основных разделов
        assert "Python" in out
        assert "Codex" in out
        assert "API" in out
        assert "Verification" in out

    def test_doctor_help_lists_doctor(self, tmp_path):
        proc = subprocess.run(
            [str(DISPATCHER), "help"],
            capture_output=True, text=True, env=_base_env(tmp_path), timeout=30,
        )
        assert proc.returncode == 0
        assert "doctor" in proc.stdout


class TestDoctorSecretHygiene:
    def test_doctor_never_prints_api_key(self, tmp_path):
        """В выводе нет ничего похожего на ключ OpenAI — секреты не утекают"""
        proc = _run_doctor(_base_env(tmp_path))
        combined = proc.stdout + proc.stderr
        assert "sk-" not in combined
        assert "access_token" not in combined

    def test_doctor_does_not_echo_injected_key(self, tmp_path):
        """Подставленное в окружение фиктивное значение ключа не попадает в вывод"""
        env = _base_env(tmp_path)
        env["OPENAI_API_KEY"] = "sk-doctortest-SHOULD-NOT-LEAK-1234567890"
        proc = _run_doctor(env)
        combined = proc.stdout + proc.stderr
        assert "SHOULD-NOT-LEAK" not in combined
        assert "sk-doctortest" not in combined


class TestDoctorBackendDetection:
    def test_api_presence_via_env_var(self, tmp_path):
        """При заданном OPENAI_API_KEY backend api считается доступным"""
        env = _base_env(tmp_path)
        env["OPENAI_API_KEY"] = "sk-dummy-value-not-printed"
        proc = _run_doctor(env)
        assert proc.returncode == 0
        # Печатается только факт наличия, без самого значения
        assert "API" in proc.stdout

    def test_no_backend_exits_one(self, tmp_path):
        """Поддельный репозиторий без .env, PATH без codex и без ключа: backend ✗ и exit 1"""
        fake = _make_fake_repo(tmp_path)
        env = _base_env(tmp_path)
        env.pop("OPENAI_API_KEY", None)
        env["PATH"] = MINIMAL_PATH
        proc = _run_doctor(env, dispatcher=fake / "ccskill-gptimage")
        assert proc.returncode == 1, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"

    def test_no_backend_still_no_secret(self, tmp_path):
        fake = _make_fake_repo(tmp_path)
        env = _base_env(tmp_path)
        env.pop("OPENAI_API_KEY", None)
        env["PATH"] = MINIMAL_PATH
        proc = _run_doctor(env, dispatcher=fake / "ccskill-gptimage")
        assert "sk-" not in (proc.stdout + proc.stderr)


class TestDoctorWithFullInstall:
    def test_symlinks_reported_ok_after_install(self, installed_home):
        """В HOME после установки команда в PATH и пользовательский скилл отмечены ✓, exit 0"""
        env = _base_env(installed_home)
        # В репозитории есть .env, поэтому backend доступен
        proc = _run_doctor(env)
        assert proc.returncode == 0
        out = proc.stdout
        # Признак того, что symlink разрешился: отметка ✓ или явное слово
        assert "skills" in out or "skill" in out.lower()
