#!/bin/zsh
set -euo pipefail
umask 077
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print 'Run SETUP.command first.'
  read '?Press Return to close.'
  exit 1
fi
source scripts/dashboard.zsh
stop_desk_dashboards
if ! PORT=$(free_port); then
  print 'Ports 8501–8520 are all in use by other apps. Close one of them and try again.'
  read '?Press Return to close.'
  exit 1
fi
[[ "$PORT" == 8501 ]] || print "Port 8501 is used by another app, so the dashboard opens at http://127.0.0.1:$PORT instead."
exec .venv/bin/python -m streamlit run dashboard.py --server.address 127.0.0.1 --server.port "$PORT" --browser.gatherUsageStats false
