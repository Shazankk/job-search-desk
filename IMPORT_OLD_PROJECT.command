#!/bin/zsh
set -euo pipefail
umask 077
cd "${0:A:h}"
print 'Run SETUP.command in this NEW folder first.'
print 'This copies your old resume, configuration and job history into this project.'
print 'Your old folder is left unchanged. Existing Keychain credentials stay on this Mac.'
read '?Press Return to choose your old project folder, or Ctrl-C to cancel.'
source scripts/dashboard.zsh
stop_desk_dashboards  # old and new dashboards must not hold the databases during the copy
.venv/bin/python scripts/import_previous.py
read '?Press Return to close.'
