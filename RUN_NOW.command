#!/bin/zsh
set -euo pipefail
umask 077
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print 'Run SETUP.command first.'
  read '?Press Return to close.'
  exit 1
fi
.venv/bin/python -m hr_agent.runner run
read '?Run finished. Press Return to close.'
