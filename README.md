# ossnap

> Snapshot and restore your macOS dev environment in minutes.

ossnap backs up your SSH keys, `.env` files, and git repo list to a **private GitHub repository** — encrypted — and restores everything on a new machine with a single command.

---

## What it does

- **SSH keys** — encrypted and stored securely
- **.env files** — discovered recursively across all your repos (including monorepos)
- **Repo list** — re-clones all your git repos on restore
- **Versioned snapshots** — full history, restore any point in time

Everything sensitive is encrypted with AES before leaving your machine. The password lives in your macOS Keychain.

---

## Requirements

- macOS
- Python 3.11+
- [GitHub CLI](https://cli.github.com) (`gh`) — installed automatically if missing

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/nvt1904/ossnap/main/install.sh | bash
```

Or manually with pipx:

```bash
pipx install ossnap
```

---

## Quick start

```bash
ossnap init        # one-time setup wizard
ossnap snapshot    # save current state
ossnap list        # view snapshot history
ossnap pull        # restore to this or a new machine
```

Aliases: `i`, `s`, `l`, `p`

```bash
ossnap s -n "before reinstall"   # named snapshot
ossnap p --repos-dir ~/code      # restore repos to custom dir
```

---

## Commands

| Command | Alias | Description |
|---------|-------|-------------|
| `init` | `i` | Interactive setup wizard |
| `snapshot` | `s` | Save a snapshot to GitHub |
| `list` | `l` | List all snapshots |
| `pull` | `p` | Restore from a snapshot |

### `ossnap snapshot`

```
-n, --name TEXT    Custom snapshot name (default: timestamp)
-h, --help
```

### `ossnap pull`

```
--ssh-dir DIR      Restore SSH keys to a custom directory
--repos-dir DIR    Clone repos into a custom base directory
-h, --help
```

---

## How it works

```
ossnap snapshot
└── Clones your private GitHub repo
    ├── ssh/
    │   ├── config          (encrypted)
    │   ├── authorized_keys (encrypted)
    │   └── keys/
    │       └── id_ed25519  (encrypted)
    └── repos/
        ├── repos.json      (list of all your git repos)
        └── envs/
            └── Documents/my-project/
                └── .env    (encrypted)
```

Each snapshot is a git commit. History is preserved — roll back to any point.

**Encryption**: AES-256 via [Fernet](https://cryptography.io/en/latest/fernet/), key derived from your password using PBKDF2-HMAC-SHA256 (600,000 iterations). Password stored in macOS Keychain.

---

## Configuration

Config file: `~/.ossnap/config.json`

```json
{
  "github_repo_url": "https://github.com/you/your-private-repo",
  "ssh_dir": "~/.ssh",
  "scan_dirs": ["~/Documents", "~/Projects"],
  "env_patterns": [".env", ".env.local", ".env.development", ".env.production"],
  "exclude_dirs": ["node_modules", ".git", "venv", "__pycache__", ".venv"]
}
```

Edit directly or re-run `ossnap init` to reconfigure (existing values are pre-filled).

---

## Uninstall

```bash
pipx uninstall ossnap
rm -rf ~/.ossnap
```

Your snapshot repo on GitHub is unaffected — delete it manually if you want.

---

## License

MIT
