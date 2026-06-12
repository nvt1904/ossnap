import subprocess
from pathlib import Path

from .exceptions import GitError


def _run(args: list[str], cwd=None) -> str:
    try:
        result = subprocess.run(
            args, cwd=cwd, check=True,
            capture_output=True, text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise GitError(e.stderr.strip() or e.stdout.strip()) from e
    except FileNotFoundError:
        raise GitError(f"Command not found: {args[0]}")


def find_git_repos(scan_dirs: list[str], exclude_dirs: list[str] | None = None) -> list[Path]:
    exclude = set(exclude_dirs or [])
    repos = []

    def walk(path: Path):
        try:
            entries = list(path.iterdir())
        except PermissionError:
            return
        if (path / ".git").exists():
            repos.append(path)
            return  # don't recurse into found repos
        for entry in entries:
            if entry.is_dir() and entry.name not in exclude and not entry.name.startswith("."):
                walk(entry)

    for d in scan_dirs:
        p = Path(d).expanduser()
        if p.exists():
            walk(p)
    return repos


def get_remote_url(repo_path: Path) -> str | None:
    try:
        return _run(["git", "-C", str(repo_path), "remote", "get-url", "origin"])
    except GitError:
        return None


def clone_repo(remote_url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", remote_url, str(dest)])


def clone_or_pull(remote_url: str, dest: Path) -> None:
    if (dest / ".git").exists():
        try:
            _run(["git", "-C", str(dest), "pull", "--ff-only"])
        except GitError:
            pass  # if pull fails (e.g. empty repo), that's fine
    else:
        dest.mkdir(parents=True, exist_ok=True)
        try:
            _run(["git", "clone", remote_url, str(dest)])
        except GitError as e:
            # empty repo — init locally and set remote
            if "empty" in str(e).lower() or dest.exists():
                _run(["git", "-C", str(dest), "init"])
                _run(["git", "-C", str(dest), "remote", "add", "origin", remote_url])
            else:
                raise


def list_commits(repo_path: Path, limit: int = 20) -> list[dict]:
    """Returns list of {hash, date, message} for recent commits."""
    out = _run(
        ["git", "-C", str(repo_path), "log",
         f"-{limit}", "--format=%H|%h|%aI|%s"],
    )
    commits = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) == 4:
            import datetime
            try:
                dt = datetime.datetime.fromisoformat(parts[2]).astimezone(datetime.timezone.utc)
                date_str = dt.strftime("%Y-%m-%d %H:%M UTC")
            except ValueError:
                date_str = parts[2]
            commits.append({"hash": parts[0], "short": parts[1], "date": date_str, "message": parts[3]})
    return commits


def checkout_commit(repo_path: Path, commit_hash: str) -> None:
    _run(["git", "-C", str(repo_path), "checkout", commit_hash])


def has_changes(repo_path: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def git_add_commit_push(repo_path: Path, message: str) -> bool:
    """Commit and push. Returns False if nothing to commit."""
    _run(["git", "-C", str(repo_path), "add", "-A"])
    if not has_changes(repo_path):
        return False
    _run(["git", "-C", str(repo_path), "commit", "-m", message])
    _run(["git", "-C", str(repo_path), "push", "--set-upstream", "origin", "HEAD"])
    return True
