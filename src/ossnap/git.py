import subprocess
from pathlib import Path

from .exceptions import GitError


def _run(args: list[str], cwd=None, interactive=False) -> str:
    try:
        if interactive:
            result = subprocess.run(
                args, cwd=cwd, check=True, text=True
            )
            return ""
        else:
            result = subprocess.run(
                args, cwd=cwd, check=True,
                capture_output=True, text=True
            )
            return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if interactive:
            raise GitError(f"Command failed: {' '.join(args)}")
        else:
            raise GitError(e.stderr.strip() or e.stdout.strip()) from e
    except FileNotFoundError:
        raise GitError(f"Command not found: {args[0]}")


def find_git_repos(
    scan_dirs: list[str],
    exclude_dirs: list[str] | None = None,
    exclude_paths: list[str] | None = None,
) -> list[dict]:
    """Return list of {"path": Path, "type": "git"|"repo_manifest"}."""
    exclude_names = set(exclude_dirs or [])
    exclude_abs = {str(Path(p).expanduser().resolve()) for p in (exclude_paths or [])}
    results = []

    def walk(path: Path):
        try:
            entries = list(path.iterdir())
        except PermissionError:
            return
        if (path / ".repo" / "manifest.xml").exists():
            results.append({"path": path, "type": "repo_manifest"})
            return
        if (path / ".git").exists():
            results.append({"path": path, "type": "git"})
            return
        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name in exclude_names or entry.name.startswith("."):
                continue
            if str(entry.resolve()) in exclude_abs:
                continue
            walk(entry)

    for d in scan_dirs:
        p = Path(d).expanduser()
        if not p.exists():
            continue
        if str(p.resolve()) in exclude_abs:
            continue
        walk(p)
    return results


def get_remote_url(repo_path: Path) -> str | None:
    try:
        return _run(["git", "-C", str(repo_path), "remote", "get-url", "origin"])
    except GitError:
        return None


def get_manifest_remote(repo_root: Path) -> str | None:
    manifests_dir = repo_root / ".repo" / "manifests"
    if not manifests_dir.exists():
        return None
    try:
        return _run(["git", "-C", str(manifests_dir), "remote", "get-url", "origin"])
    except GitError:
        return None


def init_repo_manifest(manifest_url: str, dest: Path) -> None:
    """Initialize a repo manifest tree using the 'repo' tool."""
    import shutil
    if not shutil.which("repo"):
        raise GitError("'repo' tool not found — install it from https://source.android.com/docs/setup/download")
    dest.mkdir(parents=True, exist_ok=True)
    _run(["repo", "init", "-u", manifest_url], cwd=str(dest), interactive=True)
    _run(["repo", "sync"], cwd=str(dest), interactive=True)


def clone_repo(remote_url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", remote_url, str(dest)], interactive=True)


def clone_or_pull(remote_url: str, dest: Path) -> None:
    if (dest / ".git").exists():
        try:
            _run(["git", "-C", str(dest), "pull", "--ff-only"], interactive=True)
        except GitError:
            pass
    else:
        dest.mkdir(parents=True, exist_ok=True)
        try:
            _run(["git", "clone", remote_url, str(dest)], interactive=True)
        except GitError as e:
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
    _run(["git", "-C", str(repo_path), "push", "--set-upstream", "origin", "HEAD"], interactive=True)
    return True
