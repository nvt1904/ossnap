from ossnap import ssh


def test_known_hosts_is_encrypted_and_restored(tmp_path):
    source_ssh = tmp_path / "source-ssh"
    source_ssh.mkdir()
    (source_ssh / "known_hosts").write_text("github.com ssh-ed25519 AAAA\n")
    snapshot = tmp_path / "snapshot"

    ssh.snapshot_ssh(snapshot, source_ssh, "password")

    assert (snapshot / "ssh" / "known_hosts.enc").exists()
    assert not (snapshot / "ssh" / "known_hosts").exists()

    restored_ssh = tmp_path / "restored-ssh"
    ssh.restore_ssh(snapshot, restored_ssh, "password", {"known_hosts"})

    assert (restored_ssh / "known_hosts").read_text() == "github.com ssh-ed25519 AAAA\n"


def test_legacy_plaintext_known_hosts_still_restores(tmp_path):
    snapshot = tmp_path / "snapshot"
    legacy = snapshot / "ssh" / "known_hosts"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("legacy-host ssh-rsa AAAA\n")

    restored_ssh = tmp_path / "restored-ssh"
    ssh.restore_ssh(snapshot, restored_ssh, "password", {"known_hosts"})

    assert (restored_ssh / "known_hosts").read_text() == "legacy-host ssh-rsa AAAA\n"
