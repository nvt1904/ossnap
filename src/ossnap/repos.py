import json
from pathlib import Path

import questionary

from . import crypto, git, ui

HOME = Path.home()
SKIP_DIRS = {"node_modules", ".git", "venv", "__pycache__", ".venv", "dist", "build"}



def collect_repos(
    scan_dirs: list[str],
    exclude_dirs: list[str] | None = None,
    exclude_paths: list[str] | None = None,
) -> list[dict]:
    found = git.find_git_repos(scan_dirs, exclude_dirs, exclude_paths)
    result = []
    for item in found:
        repo_path = item["path"]
        repo_type = item["type"]
        try:
            rel = str(repo_path.relative_to(HOME))
        except ValueError:
            rel = str(repo_path)
        if repo_type == "repo_manifest":
            remote = git.get_manifest_remote(repo_path)
            if not remote:
                ui.warn(f"No manifest remote: {repo_path} — skipping")
                continue
            result.append({"path": rel, "remote": remote, "type": "repo_manifest"})
        else:
            remote = git.get_remote_url(repo_path)
            if not remote:
                ui.warn(f"No remote origin: {repo_path} — skipping")
                continue
            result.append({"path": rel, "remote": remote})
    return result


def write_repos_json(repos: list[dict], snapshot_dir: Path) -> None:
    repos_dir = snapshot_dir / "repos"
    repos_dir.mkdir(parents=True, exist_ok=True)
    (repos_dir / "repos.json").write_text(json.dumps(repos, indent=2))


def read_repos_json(snapshot_dir: Path) -> list[dict]:
    f = snapshot_dir / "repos" / "repos.json"
    if not f.exists():
        return []
    return json.loads(f.read_text())


def _find_env_files(repo_path: Path, patterns: list[str]) -> list[Path]:
    """Recursively find env files within repo, skipping non-source dirs."""
    found = []
    for pattern in patterns:
        for f in repo_path.rglob(pattern):
            if f.name.endswith(".example"):
                continue
            rel_parts = f.relative_to(repo_path).parts
            if any(skip in rel_parts for skip in SKIP_DIRS):
                continue
            found.append(f)
    return found


def scan_envs(repo_path: Path, patterns: list[str]) -> list[str]:
    """Returns env file paths (relative to repo) found without snapshotting."""
    return [str(f.relative_to(repo_path)) for f in _find_env_files(repo_path, patterns)]


def snapshot_envs(
    repo_path: Path,
    env_base_dir: Path,
    password: str,
    patterns: list[str],
) -> list[str]:
    try:
        repo_rel = repo_path.relative_to(HOME)
    except ValueError:
        repo_rel = Path(repo_path)
    env_dir = env_base_dir / repo_rel

    snapped = []
    for f in _find_env_files(repo_path, patterns):
        within_repo = f.relative_to(repo_path)       # e.g. apps/web/.env
        dest = env_dir / within_repo.parent / f"{f.name}.enc"
        crypto.encrypt_file(f, dest, password)
        snapped.append(str(within_repo))
    return snapped


def list_snapshot_envs(env_base_dir: Path, repo_paths: list[str]) -> list[dict]:
    """Returns list of {path, files} for repos that have env files in the snapshot."""
    result = []
    for repo_path in repo_paths:
        env_dir = env_base_dir / repo_path
        if not env_dir.exists():
            continue
        files = []
        for enc_file in sorted(env_dir.rglob("*.enc")):
            sub = enc_file.relative_to(env_dir)
            display = str(sub.parent / enc_file.stem) if sub.parent != Path(".") else enc_file.stem
            files.append(display)
        if files:
            result.append({"path": repo_path, "files": files})
    return result


def restore_envs(
    env_base_dir: Path,
    snapshot_rel: str,
    dest_path: Path,
    password: str,
) -> tuple[int, int]:
    """Restore env files from snapshot into dest_path, preserving subfolder structure."""
    env_dir = env_base_dir / snapshot_rel
    restored = 0
    skipped = 0

    if not env_dir.exists():
        return restored, skipped

    for enc_file in sorted(env_dir.rglob("*.enc")):
        sub = enc_file.relative_to(env_dir)          # e.g. apps/web/.env.enc
        dest = dest_path / sub.parent / enc_file.stem # e.g. dest/apps/web/.env
        if dest.exists():
            overwrite = questionary.confirm(
                f"  {dest} already exists. Overwrite?",
                default=False,
            ).ask()
            if not overwrite:
                skipped += 1
                continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        crypto.decrypt_file(enc_file, dest, password)
        restored += 1

    return restored, skipped
