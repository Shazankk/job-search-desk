#!/bin/zsh
set -euo pipefail
cd "${0:A:h}"
.venv/bin/python scripts/schedule.py uninstall
read '?Press Return to close.'
