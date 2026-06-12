import json
import subprocess

from .exceptions import GhNotInstalledError, GhAuthError, NetworkError


def _run_gh(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["gh"] + args, check=True,
            capture_output=True, text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise NetworkError(e.stderr.strip() or e.stdout.strip()) from e
    except FileNotFoundError:
        raise GhNotInstalledError(
            "GitHub CLI (gh) is not installed.\n"
            "Install it with: brew install gh"
        )


def check_gh_installed() -> None:
    try:
        subprocess.run(["gh", "--version"], check=True, capture_output=True)
    except FileNotFoundError:
        raise GhNotInstalledError(
            "GitHub CLI (gh) is not installed.\n"
            "Install it with: brew install gh"
        )


def login() -> None:
    """Runs interactive gh auth login via browser."""
    try:
        subprocess.run(
            [
                "gh", "auth", "login",
                "--hostname", "github.com",
                "--git-protocol", "https",
                "--web",
                "--skip-ssh-key",
            ],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise GhAuthError("GitHub authentication failed.") from e


def check_authenticated() -> str | None:
    """Returns username if already authenticated, None otherwise."""
    try:
        result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            username = result.stdout.strip()
            if username:
                return username
    except Exception:
        pass
    return None




def list_repos() -> list[dict]:
    """Returns list of private repos for the authenticated user."""
    out = _run_gh([
        "repo", "list",
        "--limit", "100",
        "--visibility", "private",
        "--json", "name,url",
    ])
    repos = json.loads(out)
    return repos


def create_private_repo(name: str) -> str:
    """Creates a private repo and returns its HTTPS URL."""
    _run_gh(["repo", "create", name, "--private"])
    return _run_gh(["repo", "view", name, "--json", "url", "--jq", ".url"])


