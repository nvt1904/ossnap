import shutil
import stat
from pathlib import Path

from . import crypto, ui

SKIP_FILES = {"known_hosts", "environment"}
ENCRYPTED_FILES = ("config", "authorized_keys")
SKIP_EXTENSIONS = {".pub", ".pem.pub"}


def _is_private_key(path: Path) -> bool:
    if path.suffix == ".pub":
        return False
    if path.name in SKIP_FILES:
        return False
    try:
        header = path.read_bytes()[:50]
        return b"-----BEGIN" in header
    except (PermissionError, IsADirectoryError):
        return False


def scan_ssh(ssh_dir: Path) -> dict:
    """Returns the same dict as snapshot_ssh but without encrypting anything."""
    result = {"config": False, "authorized_keys": False, "keys": [], "known_hosts": False}
    if not ssh_dir.exists():
        return result
    for f in ssh_dir.iterdir():
        if not f.is_file():
            continue
        if f.name == "config":
            result["config"] = True
        elif f.name == "authorized_keys":
            result["authorized_keys"] = True
        elif f.name == "known_hosts":
            result["known_hosts"] = True
        elif _is_private_key(f):
            result["keys"].append(f.name)
    return result


def snapshot_ssh(snapshot_dir: Path, ssh_dir: Path, password: str) -> dict:
    """Returns dict with keys 'config', 'keys' (list of key names), 'known_hosts'."""
    keys_dir = snapshot_dir / "ssh" / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    ssh_snapshot_dir = snapshot_dir / "ssh"

    result = {"config": False, "authorized_keys": False, "keys": [], "known_hosts": False}

    if not ssh_dir.exists():
        ui.warn(f"SSH directory not found: {ssh_dir}")
        return result

    for f in ssh_dir.iterdir():
        if not f.is_file():
            continue
        if f.name in ENCRYPTED_FILES:
            crypto.encrypt_file(f, ssh_snapshot_dir / f"{f.name}.enc", password)
            result[f.name] = True
        elif f.name == "known_hosts":
            crypto.encrypt_file(f, ssh_snapshot_dir / "known_hosts.enc", password)
            result["known_hosts"] = True
        elif _is_private_key(f):
            crypto.encrypt_file(f, keys_dir / f"{f.name}.enc", password)
            result["keys"].append(f.name)
        elif f.suffix == ".pub":
            shutil.copy2(f, keys_dir / f.name)

    return result


def list_snapshot_items(snapshot_dir: Path) -> list[str]:
    """Returns list of SSH item names available in the snapshot."""
    ssh_snapshot_dir = snapshot_dir / "ssh"
    keys_dir = ssh_snapshot_dir / "keys"
    items = []
    for name in ENCRYPTED_FILES:
        if (ssh_snapshot_dir / f"{name}.enc").exists():
            items.append(name)
    if (ssh_snapshot_dir / "known_hosts.enc").exists() or (ssh_snapshot_dir / "known_hosts").exists():
        items.append("known_hosts")
    if keys_dir.exists():
        for f in sorted(keys_dir.iterdir()):
            if f.suffix == ".enc":
                items.append(f"keys/{f.stem}")
    return items


def restore_ssh(snapshot_dir: Path, ssh_dir: Path, password: str, selection: set[str] | None = None) -> None:
    ssh_dir.mkdir(parents=True, exist_ok=True)
    ssh_dir.chmod(0o700)
    ssh_snapshot_dir = snapshot_dir / "ssh"
    keys_dir = ssh_snapshot_dir / "keys"

    if not ssh_snapshot_dir.exists():
        ui.warn("No SSH data found in snapshot.")
        return

    restored = 0
    skipped = 0

    def _selected(name: str) -> bool:
        return selection is None or name in selection

    # Restore encrypted files (config, authorized_keys)
    for name in ENCRYPTED_FILES:
        if not _selected(name):
            continue
        enc_file = ssh_snapshot_dir / f"{name}.enc"
        if not enc_file.exists():
            continue
        dest = ssh_dir / name
        if dest.exists():
            ui.warn(f"Skipping existing: {dest}")
            skipped += 1
        else:
            crypto.decrypt_file(enc_file, dest, password)
            dest.chmod(0o600)
            restored += 1

    # Legacy plaintext known_hosts is supported for existing snapshots.
    if _selected("known_hosts"):
        encrypted_kh = ssh_snapshot_dir / "known_hosts.enc"
        legacy_kh = ssh_snapshot_dir / "known_hosts"
        dest = ssh_dir / "known_hosts"
        if dest.exists():
            ui.warn(f"Skipping existing: {dest}")
            skipped += 1
        elif encrypted_kh.exists():
            crypto.decrypt_file(encrypted_kh, dest, password)
            dest.chmod(0o644)
            restored += 1
        elif legacy_kh.exists():
            shutil.copy2(legacy_kh, dest)
            dest.chmod(0o644)
            restored += 1

    # Restore keys
    if keys_dir.exists():
        for enc_file in keys_dir.iterdir():
            if enc_file.suffix == ".enc":
                key_name = enc_file.stem
                if not _selected(f"keys/{key_name}"):
                    continue
                dest = ssh_dir / key_name
                if dest.exists():
                    ui.warn(f"Skipping existing: {dest}")
                    skipped += 1
                else:
                    crypto.decrypt_file(enc_file, dest, password)
                    dest.chmod(0o600)
                    restored += 1
            elif enc_file.suffix == ".pub":
                dest = ssh_dir / enc_file.name
                if not dest.exists():
                    shutil.copy2(enc_file, dest)
                    dest.chmod(0o644)

    ui.success(f"SSH: restored {restored} file(s), skipped {skipped} existing")
