#!/bin/zsh
set -euo pipefail
umask 077
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print 'Run SETUP.command first.'
  read '?Press Return to close.'
  exit 1
fi
.venv/bin/python -m job_search_desk.runner demo
open examples/demo-output/artifacts
print 'Synthetic demo only; no network, AI or email was used.'
read '?Press Return to close.'
