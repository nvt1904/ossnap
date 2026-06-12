import shutil
import subprocess

import questionary

from . import ui

BREW_INSTALL_SH = "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"


def _installed(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run_install(cmd: list[str] | str, shell: bool = False) -> bool:
    result = subprocess.run(cmd, shell=shell)
    return result.returncode == 0


def ensure_brew() -> bool:
    """Returns True if brew is available, installing if user agrees."""
    if _installed("brew"):
        return True

    ui.warn("Homebrew is not installed.")
    if not questionary.confirm("Install Homebrew now?", default=True).ask():
        ui.info("Install manually at: https://brew.sh")
        return False

    ui.info("Installing Homebrew (you may be prompted for your password)...")
    if not _run_install(f'/bin/bash -c "$(curl -fsSL {BREW_INSTALL_SH})"', shell=True):
        ui.error("Homebrew installation failed.")
        return False

    ui.success("Homebrew installed.")
    return True


def ensure_gh() -> bool:
    """Returns True if gh CLI is available, installing via brew if user agrees."""
    if _installed("gh"):
        return True

    ui.warn("GitHub CLI (gh) is not installed.")
    if not questionary.confirm("Install gh via Homebrew?", default=True).ask():
        ui.info("Install manually: https://cli.github.com")
        return False

    if not ensure_brew():
        return False

    ui.info("Installing gh...")
    if not _run_install(["brew", "install", "gh"]):
        ui.error("gh installation failed.")
        return False

    ui.success("gh installed.")
    return True
