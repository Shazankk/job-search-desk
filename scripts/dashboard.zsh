# Sourced by the .command launchers. Stops Job Search Desk dashboards only; other apps are never touched.

# Dashboards started from any Job Search Desk folder, including an older version's folder.
desk_dashboard_pids() {
  local pid dir
  for pid in $(/usr/bin/pgrep -f 'streamlit run dashboard.py' 2>/dev/null); do
    dir=$(/usr/sbin/lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | /usr/bin/sed -n 's/^n//p')
    # job_search_desk/ now; hr_agent/ in releases before the rename.
    [[ ( -f "$dir/job_search_desk/runner.py" || -f "$dir/hr_agent/runner.py" ) && -f "$dir/dashboard.py" ]] && print "$pid"
  done
  return 0  # launchers run with errexit; finding nothing is not an error
}

# Ask politely, then force after 5 seconds. A run interrupted this way leaves no lock behind.
stop_pids() {
  local pids=("$@") alive pid
  (( ${#pids} )) || return 0
  kill -TERM "${pids[@]}" 2>/dev/null || true
  for _ in {1..50}; do
    alive=()
    for pid in "${pids[@]}"; do kill -0 "$pid" 2>/dev/null && alive+=("$pid"); done
    (( ${#alive} )) || return 0
    sleep 0.1
  done
  kill -KILL "${alive[@]}" 2>/dev/null || true
}

stop_desk_dashboards() {
  local pids=($(desk_dashboard_pids))
  (( ${#pids} )) || return 0
  print 'Closing the Job Search Desk dashboard that was already running…'
  stop_pids "${pids[@]}"
}

port_in_use() {
  /usr/sbin/lsof -nP -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1
}

# 8501 unless another app holds it; then the next free port up to 8520.
free_port() {
  local port
  for port in {8501..8520}; do
    port_in_use "$port" || { print "$port"; return 0 }
  done
  return 1
}
