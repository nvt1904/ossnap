#!/bin/bash
set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
warn() { echo -e "  ${YELLOW}⚠${RESET}  $1"; }
err()  { echo -e "  ${RED}✗${RESET} $1"; exit 1; }
info() { echo -e "  $1"; }

echo ""
echo -e "${BOLD}ossnap installer${RESET}"
echo "──────────────────────────────────────"
echo ""

# 1. macOS check
if [[ "$(uname)" != "Darwin" ]]; then
  err "ossnap requires macOS."
fi

# 2. Python 3.11+ check
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3; do
  if command -v "$cmd" &>/dev/null; then
    version=$("$cmd" -c 'import sys; print(sys.version_info[:2])' 2>/dev/null)
    major=$("$cmd" -c 'import sys; print(sys.version_info.major)')
    minor=$("$cmd" -c 'import sys; print(sys.version_info.minor)')
    if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
      PYTHON="$cmd"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  warn "Python 3.11+ not found."
  info "Install it with: brew install python@3.11"
  err "Python 3.11+ is required."
fi
ok "Python $($PYTHON --version)"

# 3. pipx check / install
if ! command -v pipx &>/dev/null; then
  warn "pipx not found — installing via Homebrew..."
  if ! command -v brew &>/dev/null; then
    err "Homebrew not found. Install it first: https://brew.sh"
  fi
  brew install pipx
  pipx ensurepath
  ok "pipx installed"
else
  ok "pipx $(pipx --version)"
fi

# 4. Install ossnap
echo ""
info "Installing ossnap..."
echo ""
pipx install ossnap --force

echo ""
echo "──────────────────────────────────────"
ok "ossnap installed successfully!"
echo ""
info "Get started:"
info "  ${BOLD}ossnap init${RESET}      — run setup wizard"
info "  ${BOLD}ossnap --help${RESET}    — see all commands"
echo ""
