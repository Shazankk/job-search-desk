#!/bin/zsh
set -euo pipefail
cd "${0:A:h}"
source scripts/dashboard.zsh
if [[ -z "$(desk_dashboard_pids)" ]]; then
  print 'No Job Search Desk dashboard is running.'
else
  stop_desk_dashboards
  print 'Dashboard closed. OPEN_DASHBOARD.command starts it again.'
fi
read '?Press Return to close.'
