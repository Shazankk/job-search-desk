#!/bin/zsh
set -euo pipefail
umask 077
cd "${0:A:h}"
print 'Job Search Desk — first-time setup'
print 'This needs macOS, Python 3.11 or newer, and internet for the first installation.'
if [[ "$(uname -s)" != Darwin ]]; then
  print 'This setup launcher is for macOS. See README for manual Python commands.'
  exit 1
fi
PYTHON="$(command -v python3 || true)"
if [[ -z "$PYTHON" ]] || ! "$PYTHON" -c 'import sys; assert sys.version_info >= (3,11)' 2>/dev/null; then
  print 'Install the current Python 3 macOS installer from https://www.python.org/downloads/macos/ .'
  print 'Then double-click SETUP.command again. Python is not bundled in this ZIP.'
  read '?Press Return to close.'
  exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
mkdir -p data/imports data/inbox data/contacts logs artifacts
[[ -f config/settings.json ]] || cp config/settings.example.json config/settings.json
.venv/bin/python -m job_search_desk.runner check
print 'Setup complete. The dashboard is opening.'
print 'Use INSTALL_DAILY.command separately when sources and settings are ready.'
exec ./OPEN_DASHBOARD.command
