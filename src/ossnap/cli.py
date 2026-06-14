import datetime
import shutil
import sys
import tempfile
from pathlib import Path

import click
import questionary

from . import config, crypto, git, github, install, repos, ssh, ui
from .exceptions import (
    ConfigNotFoundError,
    DecryptionError,
    GhAuthError,
    GitError,
    NetworkError,
)


class AliasedGroup(click.Group):
    ALIASES = {"i": "init", "s": "snapshot", "p": "pull", "l": "list"}
    _REVERSE = {v: k for k, v in ALIASES.items()}

    def get_command(self, ctx, cmd_name):
        return super().get_command(ctx, self.ALIASES.get(cmd_name, cmd_name))

    def format_commands(self, ctx, formatter):
        rows = []
        for name in self.list_commands(ctx):
            cmd = self.get_command(ctx, name)
            if cmd is None or cmd.hidden:
                continue
            alias = self._REVERSE.get(name, "")
            label = f"{name} ({alias})" if alias else name
            rows.append((label, cmd.get_short_help_str(limit=formatter.width)))
        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)


@click.group(cls=AliasedGroup, context_settings={"help_option_names": ["-h", "--help"]})
def main():
    """ossnap — snapshot and restore your macOS dev environment."""
    pass


HELP_OPTS = {"help_option_names": ["-h", "--help"]}


@main.command(context_settings=HELP_OPTS)
def init():
    """Interactive setup wizard."""
    ui.banner("init")

    # Load existing config as defaults (if re-running init)
    try:
        existing_cfg = config.load_config()
        ui.info("Existing config found — pre-filling values.")
    except ConfigNotFoundError:
        existing_cfg = {}

    # 1. Check gh CLI
    if not install.ensure_gh():
        sys.exit(1)

    # 2. Authenticate
    with ui.status_spinner("Checking GitHub authentication..."):
        username = github.check_authenticated()

    if username:
        ui.success(f"Logged in as: {username}")
    else:
        try:
            github.login()
            with ui.status_spinner("Verifying authentication..."):
                username = github.check_authenticated() or ""
            ui.success(f"Logged in as: {username}")
        except (GhAuthError, NetworkError) as e:
            ui.error(f"Authentication failed: {e}")
            sys.exit(1)

    # 3. Select or create snapshot repo
    ui.header("Snapshot Repository")
    try:
        with ui.status_spinner("Fetching your repositories..."):
            repo_list = github.list_repos()
    except NetworkError as e:
        ui.error(f"Failed to list repos: {e}")
        sys.exit(1)

    repo_map = {r["name"]: r["url"] for r in repo_list}
    CREATE_NEW = "+ Create new private repo"
    # Pre-select existing repo from config
    existing_url = existing_cfg.get("github_repo_url", "")
    existing_repo_name = existing_url.rstrip("/").split("/")[-1] if existing_url else None
    repo_default = existing_repo_name if existing_repo_name in repo_map else CREATE_NEW
    selected = questionary.select(
        "Snapshot repository:",
        choices=[CREATE_NEW] + list(repo_map.keys()),
        default=repo_default,
    ).ask()
    if selected is None:
        sys.exit(0)

    if selected == CREATE_NEW:
        repo_name = questionary.text(
            "Repository name:", default="macos_setup"
        ).ask()
        if not repo_name or not repo_name.strip():
            sys.exit(0)
        try:
            with ui.status_spinner(f"Creating {repo_name.strip()}..."):
                repo_url = github.create_private_repo(repo_name.strip())
            ui.success(f"Created: {repo_url}")
        except NetworkError as e:
            ui.error(f"Failed to create repo: {e}")
            sys.exit(1)
    else:
        repo_url = repo_map[selected]
        ui.success(f"Using: {repo_url}")

    # 4. SSH directory
    ui.header("SSH Directory")
    existing_ssh = existing_cfg.get("ssh_dir", "~/.ssh")
    existing_ssh = existing_ssh.replace(str(Path.home()), "~")
    ssh_dir_input = questionary.path(
        "SSH directory:",
        default=existing_ssh,
        only_directories=True,
    ).ask()
    if ssh_dir_input is None:
        sys.exit(0)
    ssh_dir = str(Path(ssh_dir_input).expanduser())
    ui.success(f"SSH dir: {ssh_dir}")

    # 5. Scan directories
    ui.header("Repo Scan Directories")
    home = Path.home()
    common_names = ["Documents", "Projects", "Developer", "Desktop", "workspace", "code", "repos", "work", "dev"]
    default_names = {"Documents", "Projects"}
    existing_scan = {str(Path(d).expanduser()) for d in existing_cfg.get("scan_dirs", [])}
    dir_choices = [
        questionary.Choice(
            str(home / name),
            checked=(str(home / name) in existing_scan if existing_scan else name in default_names),
        )
        for name in common_names
        if (home / name).exists()
    ]
    # Add custom dirs from existing config that aren't in common list
    for d in existing_scan:
        if not any(str(home / n) == d for n in common_names) and Path(d).exists():
            dir_choices.append(questionary.Choice(d, checked=True))
    scan_dirs = questionary.checkbox(
        "Select directories to scan for git repos:",
        choices=dir_choices,
        instruction="(space: select, a: all, i: invert)",
    ).ask()
    if scan_dirs is None:
        sys.exit(0)

    while True:
        d = questionary.path(
            "Add custom directory (leave blank to finish):",
            default="",
            only_directories=True,
        ).ask()
        if not d or not d.strip():
            break
        expanded = str(Path(d).expanduser())
        if expanded not in scan_dirs:
            scan_dirs.append(expanded)

    if not scan_dirs:
        ui.warn("No scan directories configured. You can edit ~/.ossnap/config.json later.")
    else:
        ui.success(f"Will scan: {', '.join(scan_dirs)}")

    # 6. Exclude paths (full paths to skip entirely, e.g. large AOSP trees)
    ui.header("Exclude Paths")
    ui.info("Add directories to skip entirely (e.g. large AOSP/ROM trees).")
    existing_exclude_paths = [
        str(Path(p).expanduser()) for p in existing_cfg.get("exclude_paths", [])
    ]
    exclude_paths: list[str] = list(existing_exclude_paths)
    while True:
        d = questionary.path(
            "Exclude path (leave blank to finish):",
            default="",
            only_directories=True,
        ).ask()
        if d is None:
            sys.exit(0)
        if not d.strip():
            break
        expanded = str(Path(d).expanduser())
        if expanded not in exclude_paths:
            exclude_paths.append(expanded)
            ui.success(f"Will exclude: {expanded}")
    if exclude_paths:
        ui.success(f"Excluded: {', '.join(exclude_paths)}")

    # 8. Env file patterns
    ui.header("Env File Patterns")
    default_patterns = {".env", ".env.local", ".env.development", ".env.production"}
    existing_patterns = set(existing_cfg.get("env_patterns", [])) or default_patterns
    known = [".env", ".env.local", ".env.development", ".env.production", ".env.staging", ".env.test"]
    all_choices = [
        questionary.Choice(p, checked=(p in existing_patterns))
        for p in known
    ]
    # Add custom patterns from existing config not in known list
    for p in existing_patterns:
        if p not in known:
            all_choices.append(questionary.Choice(p, checked=True))
    env_patterns = questionary.checkbox(
        "Select env file patterns to snapshot:",
        choices=all_choices,
        instruction="(space: select, a: all, i: invert)",
    ).ask()

    if env_patterns is None:
        sys.exit(0)

    custom = questionary.text(
        "Additional patterns? (comma-separated, leave blank to skip):", default=""
    ).ask()
    if custom:
        extras = [p.strip() for p in custom.split(",") if p.strip()]
        env_patterns.extend(e for e in extras if e not in env_patterns)

    ui.success(f"Env patterns: {', '.join(env_patterns)}")

    # 9. Encryption password
    ui.header("Encryption")
    existing_pw = crypto.get_password_if_exists()
    if existing_pw:
        change = questionary.confirm("Encryption password already set. Change it?", default=False).ask()
        if not change:
            pw = existing_pw
            ui.success("Keeping existing password.")
        else:
            existing_pw = None

    if not existing_pw:
        ui.info("Set a password to encrypt your SSH keys and .env files.")
        while True:
            pw = questionary.password("Password:").ask()
            if not pw:
                ui.error("Password cannot be empty.")
                continue
            pw2 = questionary.password("Confirm password:").ask()
            if pw != pw2:
                ui.error("Passwords do not match. Try again.")
                continue
            break
        crypto.set_password(pw)
        ui.success("Password saved to macOS Keychain")

    # 10. Save config
    cfg = config.default_config()
    cfg["github_repo_url"] = repo_url
    cfg["ssh_dir"] = ssh_dir_input.replace(str(Path.home()), "~")
    cfg["scan_dirs"] = [str(d).replace(str(Path.home()), "~") for d in scan_dirs]
    cfg["env_patterns"] = env_patterns
    cfg["exclude_paths"] = [str(p).replace(str(Path.home()), "~") for p in exclude_paths]
    config.save_config(cfg)
    ui.success("Config saved to ~/.ossnap/config.json")

    # 11. Verify connection
    ui.header("Verifying connection")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "verify"
        try:
            with ui.status_spinner("Connecting to snapshot repo..."):
                git.clone_or_pull(repo_url, tmp)
            ui.success("Connection verified")
        except GitError as e:
            ui.warn(f"Could not verify connection: {e}")
            ui.info("You can still snapshot/pull later.")

    # 12. Preview what will be backed up
    ui.header("Preview")
    with ui.status_spinner("Scanning SSH directory..."):
        ssh_result = ssh.scan_ssh(Path(ssh_dir).expanduser())
    with ui.status_spinner("Scanning repos..."):
        repo_list = repos.collect_repos(
            [str(Path(d).expanduser()) for d in scan_dirs],
            cfg.get("exclude_dirs", config.DEFAULT_CONFIG["exclude_dirs"]),
            exclude_paths,
        )
    with ui.status_spinner("Scanning env files..."):
        repo_results = [
            (
                entry["path"],
                [] if entry.get("type") == "repo_manifest"
                else repos.scan_envs(Path.home() / entry["path"], env_patterns),
            )
            for entry in repo_list
        ]
    ui.print_snapshot_tree(repo_results, ssh_result)

    ui.header("Done! Run `ossnap snapshot` to create your first snapshot.")


@main.command(name="list", context_settings=HELP_OPTS)
def list_snapshots():
    """List all snapshots."""
    ui.banner("list")

    try:
        cfg = config.load_config()
    except ConfigNotFoundError as e:
        ui.error(str(e))
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "snapshot_repo"
        try:
            with ui.status_spinner("Fetching snapshot history..."):
                git.clone_or_pull(cfg["github_repo_url"], tmp)
        except GitError as e:
            ui.error(f"Failed to access snapshot repo: {e}")
            sys.exit(1)

        commits = git.list_commits(tmp, limit=50)

    if not commits:
        ui.warn("No snapshots found.")
        return

    ui.print_table(
        title="Snapshot History",
        headers=["#", "Commit", "Date", "Name"],
        rows=[
            (
                str(i + 1),
                c["short"],
                c["date"],
                c["message"],
            )
            for i, c in enumerate(commits)
        ],
    )


@main.command(context_settings=HELP_OPTS)
@click.option("-n", "--name", default=None, help="Custom snapshot name.")
def snapshot(name: str | None):
    """Save a snapshot of your environment to GitHub."""
    ui.banner("snapshot")

    try:
        cfg = config.load_config()
    except ConfigNotFoundError as e:
        ui.error(str(e))
        sys.exit(1)

    try:
        password = crypto.get_or_create_password()
    except Exception as e:
        ui.error(f"Could not get encryption password: {e}")
        sys.exit(1)

    repo_url = cfg["github_repo_url"]
    ssh_dir = Path(cfg["ssh_dir"]).expanduser()
    scan_dirs = cfg["scan_dirs"]
    env_patterns = cfg.get("env_patterns", [".env", ".env.local"])
    exclude_dirs = cfg.get("exclude_dirs", [])
    snapshot_exclude_paths = cfg.get("exclude_paths", [])

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "snapshot_repo"
        try:
            with ui.status_spinner("Cloning snapshot repo..."):
                git.clone_or_pull(repo_url, tmp)
        except GitError as e:
            ui.error(f"Failed to access snapshot repo: {e}")
            sys.exit(1)

        # SSH
        ssh_result = {}
        try:
            with ui.status_spinner("Backing up SSH..."):
                ssh_result = ssh.snapshot_ssh(tmp, ssh_dir, password)
        except Exception as e:
            ui.warn(f"SSH snapshot failed: {e}")

        # Repos
        with ui.status_spinner("Discovering git repos..."):
            repo_list = repos.collect_repos(scan_dirs, exclude_dirs, snapshot_exclude_paths)

        # Clear entire repos/ dir so stale entries don't accumulate
        repos_dir = tmp / "repos"
        if repos_dir.exists():
            shutil.rmtree(repos_dir)

        repos.write_repos_json(repo_list, tmp)

        env_base = tmp / "repos" / "envs"
        snapshot_results = []
        with ui.status_spinner("Snapshotting env files...") as s:
            for entry in repo_list:
                if entry.get("type") == "repo_manifest":
                    snapshot_results.append((entry["path"], []))
                    continue
                s.update(f"[dim]Snapshotting {entry['path']}...[/]")
                repo_path = Path.home() / entry["path"]
                env_files = repos.snapshot_envs(repo_path, env_base, password, env_patterns)
                snapshot_results.append((entry["path"], env_files))

        ui.print_snapshot_tree(snapshot_results, ssh_result)

        # Meta
        import json, platform
        meta = {
            "tool_version": "0.1.0",
            "snapshot_date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "hostname": platform.uname().node,
        }
        (tmp / "meta.json").write_text(json.dumps(meta, indent=2))

        # Commit + push
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        msg = name.strip() if name else f"Snapshot at {now_str}"
        try:
            with ui.status_spinner("Saving snapshot..."):
                changed = git.git_add_commit_push(tmp, msg)
            if changed:
                ui.success(f"Snapshot complete — {msg}")
            else:
                ui.info("Nothing changed since last snapshot.")
        except GitError as e:
            ui.error(f"Snapshot failed: {e}")
            sys.exit(1)


@main.command(context_settings=HELP_OPTS)
@click.option("--ssh-dir", "ssh_dir_override", default=None, metavar="DIR",
              help="Directory to restore SSH keys into.")
@click.option("--repos-dir", "repos_dir_override", default=None, metavar="DIR",
              help="Base directory to clone repos into.")
def pull(ssh_dir_override: str | None, repos_dir_override: str | None):
    """Restore your environment from GitHub."""
    ui.banner("pull")

    try:
        cfg = config.load_config()
    except ConfigNotFoundError as e:
        ui.error(str(e))
        sys.exit(1)

    try:
        password = crypto.get_or_create_password()
    except Exception as e:
        ui.error(f"Could not get encryption password: {e}")
        sys.exit(1)

    repo_url = cfg["github_repo_url"]
    ssh_dir = Path(ssh_dir_override).expanduser() if ssh_dir_override else Path(cfg.get("ssh_dir", "~/.ssh")).expanduser()
    repos_base = Path(repos_dir_override).expanduser() if repos_dir_override else None

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / "snapshot_repo"
        try:
            with ui.status_spinner("Pulling from GitHub..."):
                git.clone_or_pull(repo_url, tmp)
        except GitError as e:
            ui.error(f"Failed to access snapshot repo: {e}")
            sys.exit(1)

        # Version selection
        commits = git.list_commits(tmp)
        if len(commits) > 1:
            ui.header("Version")
            def _fmt(c: dict, suffix: str = "") -> str:
                return f"{c['short']}  {c['date']}  {c['message']}{suffix}"

            LATEST = _fmt(commits[0], "  (latest)")
            choices = [LATEST] + [_fmt(c) for c in commits[1:]]
            selected_version = questionary.select(
                "Select snapshot to restore:",
                choices=choices,
            ).ask()
            if selected_version is None:
                sys.exit(0)
            if selected_version != LATEST:
                idx = choices.index(selected_version)
                git.checkout_commit(tmp, commits[idx]["hash"])

        # SSH — let user select what to restore
        ssh_items = ssh.list_snapshot_items(tmp)
        if ssh_items:
            ui.header("SSH")
            ui.info("Existing files will be skipped automatically.")
            selected_ssh = questionary.checkbox(
                "Select SSH items to restore:",
                choices=[questionary.Choice(item, checked=True) for item in ssh_items],
                instruction="(space: select, a: all, i: invert)",
            ).ask()
            if selected_ssh is None:
                sys.exit(0)
            ssh_selection = set(selected_ssh) if selected_ssh else None
        else:
            ssh_selection = None

        if ssh_selection:
            try:
                with ui.status_spinner("Restoring SSH keys..."):
                    ssh.restore_ssh(tmp, ssh_dir, password, ssh_selection)
            except DecryptionError:
                ui.error("Wrong encryption password. Aborting SSH restore.")
                sys.exit(1)
            except Exception as e:
                ui.warn(f"SSH restore failed: {e}")

        env_base = tmp / "repos" / "envs"

        # Repos — select which to clone
        repo_list = repos.read_repos_json(tmp)
        selected_repo_paths: set[str] = set()
        if repo_list:
            ui.header("Repos")
            selected_repos = questionary.checkbox(
                "Select repos to clone:",
                choices=[questionary.Choice(e["path"], checked=True) for e in repo_list],
                instruction="(space: select, a: all, i: invert)",
            ).ask()
            if selected_repos is None:
                sys.exit(0)
            selected_repo_paths = set(selected_repos)

        cloned = 0
        for entry in [e for e in repo_list if e["path"] in selected_repo_paths]:
            local_path = repos_base / entry["path"] if repos_base else Path.home() / entry["path"]
            if entry.get("type") == "repo_manifest":
                if local_path.exists() and (local_path / ".repo").exists():
                    ui.info(f"Already exists (manifest tree): {local_path}")
                else:
                    ui.info(f"Initializing manifest tree {entry['remote']} → {local_path}")
                    try:
                        git.init_repo_manifest(entry["remote"], local_path)
                        cloned += 1
                    except GitError as e:
                        ui.warn(f"Could not init manifest tree: {e}")
                        ui.info(f"  Manual steps:")
                        ui.info(f"    mkdir -p {local_path} && cd {local_path}")
                        ui.info(f"    repo init -u {entry['remote']}")
                        ui.info(f"    repo sync")
            elif not local_path.exists():
                ui.info(f"Cloning {entry['remote']} → {local_path}")
                try:
                    git.clone_repo(entry["remote"], local_path)
                    cloned += 1
                except GitError as e:
                    ui.warn(f"Could not clone {entry['remote']}: {e}")
            else:
                ui.info(f"Already exists: {local_path}")
        if cloned:
            ui.success(f"Cloned/initialized {cloned} repo(s)")

        # Env files — select which repos' env files to restore
        snapshot_envs = repos.list_snapshot_envs(env_base, [e["path"] for e in repo_list])
        if snapshot_envs:
            ui.header("Env Files")
            selected_env = questionary.checkbox(
                "Select repos to restore env files for:",
                choices=[
                    questionary.Choice(
                        f"{e['path']}  ({', '.join(e['files'])})",
                        value=e["path"],
                        checked=True,
                    )
                    for e in snapshot_envs
                ],
                instruction="(space: select, a: all, i: invert)",
            ).ask()
            if selected_env is None:
                sys.exit(0)

            env_restored = 0
            env_skipped = 0
            with ui.status_spinner("Restoring env files...") as s:
                for snap_rel in selected_env:
                    s.update(f"[dim]Restoring {snap_rel}...[/]")
                    if repos_base:
                        dest_path = repos_base / snap_rel
                    else:
                        dest_path = Path.home() / snap_rel
                    r, s_tmp = repos.restore_envs(env_base, snap_rel, dest_path, password)
                    env_restored += r
                    env_skipped += s_tmp
            if env_restored:
                ui.success(f"Restored {env_restored} env file(s) ({env_skipped} skipped)")

    ui.header("Pull complete.")
