#!/usr/bin/env bash
# rzr-register.sh - register this watchtower's validated wake-delivery target.
#
# Usage:
#   rzr-register.sh --harness <claude|codex|copilot|pi> [--backend auto|codex|herdr]
#                   [--agent-session <absolute-session-file>] [--driver-id <id>] [--quiet]
#
# Writes the current watchtowers/<driver-id>/target.json attribution and appends
# a registration record to registrations.jsonl for `rzr-watch --wake`. The
# declared harness is validated against live state before it is recorded, so a
# stale inherited CODEX_THREAD_ID can never wake the wrong conversation:
#   - codex backend: requires CODEX_THREAD_ID and a Codex CLI with `queue`; the
#     declared harness must be codex.
#   - herdr backend: requires HERDR_PANE_ID and that the pane REPORTS the declared
#     harness and pane id. Managed panes require interactive_ready; a manual Pi
#     watchtower instead requires its exact Herdr agent_session path because
#     full_lifecycle_hook_authority panes do not receive interactive_ready.
#   - auto: picks codex only when the declared harness is codex and the Codex
#     queue is available; otherwise the validated herdr pane. It never selects a
#     backend from the mere presence of an environment variable.
#
# Prints the driver id (unless --quiet). Re-registration replaces the current
# target and appends a fresh history record for the same identity.
set -euo pipefail
# shellcheck disable=SC1091 # The library path is resolved beside this script.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rzr-lib.sh"

HARNESS="" BACKEND="auto" DRIVER_ID="" AGENT_SESSION="" QUIET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --harness) HARNESS="${2:-}"; shift 2 ;;
    --backend) BACKEND="${2:-}"; shift 2 ;;
    --driver-id) DRIVER_ID="${2:-}"; shift 2 ;;
    --agent-session) AGENT_SESSION="${2:-}"; shift 2 ;;
    --quiet) QUIET=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) rzr_die "unknown flag: $1" ;;
  esac
done

case "$HARNESS" in
  claude|codex|copilot|pi) ;;
  "") rzr_die "--harness is required (claude|codex|copilot|pi)" ;;
  *)  rzr_die "unsupported --harness '$HARNESS' (claude|codex|copilot|pi)" ;;
esac
case "$BACKEND" in auto|codex|herdr) ;; *) rzr_die "unsupported --backend '$BACKEND'" ;; esac
if [ -n "$AGENT_SESSION" ]; then
  case "$AGENT_SESSION" in /*) ;; *) rzr_die "--agent-session must be an absolute Pi session file" ;; esac
fi

codex_ok() { [ -n "${CODEX_THREAD_ID:-}" ] && command -v codex >/dev/null 2>&1 && codex queue --help >/dev/null 2>&1; }

# Validate the herdr pane actually runs the declared harness before pinning it.
validate_herdr() {
  [ -n "${HERDR_PANE_ID:-}" ] || rzr_die "herdr backend requires HERDR_PANE_ID from the resident pane"
  local out _field hp ready reported_pane session_kind session_source session_value
  local -a fields=()
  out=$(rzr_herdr agent get "$HERDR_PANE_ID" 2>/dev/null) || rzr_die "herdr does not report a live agent for pane '$HERDR_PANE_ID'"
  while IFS= read -r -d '' _field; do fields+=("$_field"); done \
    < <(printf '%s' "$out" | jq -j '(.result.agent // .result // .) as $a | [($a.agent // $a.kind // $a.harness // "" | ascii_downcase), (($a.interactive_ready // false) | tostring), ($a.pane_id // ""), ($a.agent_session.kind // ""), ($a.agent_session.source // ""), ($a.agent_session.value // "")] | .[] | (. + "\u0000")' 2>/dev/null || true)
  hp="${fields[0]:-}" ready="${fields[1]:-}" reported_pane="${fields[2]:-}"
  session_kind="${fields[3]:-}" session_source="${fields[4]:-}" session_value="${fields[5]:-}"
  [ -n "$hp" ] || rzr_die "herdr does not report a harness for pane '$HERDR_PANE_ID' (is the agent live?)"
  [ "$hp" = "$HARNESS" ] || rzr_die "declared harness '$HARNESS' does not match pane '$HERDR_PANE_ID' (herdr reports '$hp') — refusing to wake the wrong session"
  [ "$reported_pane" = "$HERDR_PANE_ID" ] || rzr_die "herdr agent identity does not match pane '$HERDR_PANE_ID'"
  if [ "$HARNESS" = pi ] && [ -n "$AGENT_SESSION" ]; then
    [ -n "$session_value" ] || rzr_die "herdr does not report Pi agent_session for pane '$HERDR_PANE_ID' yet"
    [ "$session_kind" = path ] && [ "$session_source" = herdr:pi ] && [ "$session_value" = "$AGENT_SESSION" ] || \
      rzr_die "pane '$HERDR_PANE_ID' Pi agent_session '$session_value' does not match this process session file '$AGENT_SESSION'"
  else
    [ -z "$AGENT_SESSION" ] || rzr_die "--agent-session is supported only for Pi Herdr registration"
    [ "$ready" = true ] || rzr_die "pane '$HERDR_PANE_ID' is not interactive_ready yet"
  fi
}

case "$BACKEND" in
  codex)
    [ "$HARNESS" = codex ] || rzr_die "codex backend requires --harness codex"
    codex_ok || rzr_die "codex backend requires CODEX_THREAD_ID and a Codex CLI with 'queue'"
    IDENTITY="$CODEX_THREAD_ID" ;;
  herdr)
    validate_herdr
    IDENTITY="$HERDR_PANE_ID" ;;
  auto)
    if [ "$HARNESS" = codex ] && codex_ok; then
      BACKEND=codex; IDENTITY="$CODEX_THREAD_ID"
    else
      validate_herdr
      BACKEND=herdr; IDENTITY="$HERDR_PANE_ID"
    fi ;;
esac

[ -n "$DRIVER_ID" ] || DRIVER_ID="$(rzr_driver_id_for "$BACKEND" "$IDENTITY")"
rzr_validate_task_component "$DRIVER_ID" "driver id"
[ -z "${ROZORO_WT_NAME:-}" ] || rzr_validate_wt_metadata "$ROZORO_WT_NAME" "watchtower name"
[ -z "${ROZORO_WT_POLICY_SHA256:-}" ] || rzr_validate_wt_metadata "$ROZORO_WT_POLICY_SHA256" "watchtower policy SHA"
if [ -n "${ROZORO_WT_PRESET:-}" ]; then
  rzr_validate_wtpreset_name "$ROZORO_WT_PRESET"
  rzr_validate_wt_metadata "${ROZORO_WT_PRESET_VERSION:-}" "watchtower preset version"
  rzr_validate_wt_metadata "${ROZORO_WT_PRESET_SHA256:-}" "watchtower preset SHA"
  rzr_validate_wt_metadata "${ROZORO_WT_MODEL:-}" "watchtower model"
  rzr_validate_wt_metadata "${ROZORO_WT_EFFORT:-}" "watchtower effort"
fi

RZR_REG_HOME="$RZR_HOME" RZR_REG_ID="$DRIVER_ID" RZR_REG_HARNESS="$HARNESS" \
RZR_REG_BACKEND="$BACKEND" RZR_REG_IDENTITY="$IDENTITY" RZR_REG_OWNER="$PPID" \
RZR_REG_WT_NAME="${ROZORO_WT_NAME:-}" RZR_REG_PRESET="${ROZORO_WT_PRESET:-}" \
RZR_REG_VERSION="${ROZORO_WT_PRESET_VERSION:-}" RZR_REG_SHA="${ROZORO_WT_PRESET_SHA256:-}" \
RZR_REG_POLICY_SHA="${ROZORO_WT_POLICY_SHA256:-}" RZR_REG_MODEL="${ROZORO_WT_MODEL:-}" \
RZR_REG_EFFORT="${ROZORO_WT_EFFORT:-}" \
RZR_REG_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)" python3 - <<'PY'
import fcntl, json, os, stat
nofollow=getattr(os,"O_NOFOLLOW",0); directory=getattr(os,"O_DIRECTORY",0)
def child(parent,name):
    try: os.mkdir(name,0o700,dir_fd=parent)
    except FileExistsError: pass
    info=os.stat(name,dir_fd=parent,follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid(): raise SystemExit("unsafe watchtower directory")
    fd=os.open(name,os.O_RDONLY|directory|nofollow,dir_fd=parent)
    if (info.st_dev,info.st_ino)!=(os.fstat(fd).st_dev,os.fstat(fd).st_ino): os.close(fd); raise SystemExit("watchtower directory changed during open")
    os.fchmod(fd,0o700); return fd
home=os.environ["RZR_REG_HOME"]; before=os.stat(home,follow_symlinks=False)
root=os.open(home,os.O_RDONLY|directory|nofollow)
if (before.st_dev,before.st_ino)!=(os.fstat(root).st_dev,os.fstat(root).st_ino): os.close(root); raise SystemExit("watchtower home changed during open")
try: towers=child(root,"watchtowers")
finally: os.close(root)
try: dirfd=child(towers,os.environ["RZR_REG_ID"])
finally: os.close(towers)
tmp_name = ".target.%d.tmp" % os.getpid(); target_name="target.json"
os.umask(0o077)
def write_all(fd, payload):
    view = memoryview(payload)
    while view:
        count = os.write(fd, view)
        if count <= 0: raise OSError("short registration write")
        view = view[count:]
def cleanup_owned(parent, name, identity):
    fcntl.flock(parent, fcntl.LOCK_EX)
    try:
        try: current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError: return
        if (current.st_dev, current.st_ino) == identity: os.unlink(name, dir_fd=parent)
    finally: fcntl.flock(parent, fcntl.LOCK_UN)
def replace_owned(parent, source, destination, identity, source_fd):
    owned = os.fstat(source_fd)
    if (owned.st_dev, owned.st_ino) != identity or owned.st_nlink != 1:
        raise SystemExit("registration temporary source drifted")
    try: current = os.stat(source, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError: raise SystemExit("registration temporary disappeared")
    if (current.st_dev, current.st_ino) != identity:
        raise SystemExit("registration temporary changed during write")
    os.replace(source, destination, src_dir_fd=parent, dst_dir_fd=parent)
    published = os.stat(destination, dir_fd=parent, follow_symlinks=False)
    if (published.st_dev, published.st_ino) != identity or os.fstat(source_fd).st_nlink != 1:
        raise SystemExit("registration target publication drifted")
data = {"schema": 1, "driver_id": os.environ["RZR_REG_ID"],
        "harness": os.environ["RZR_REG_HARNESS"], "backend": os.environ["RZR_REG_BACKEND"],
        "identity": os.environ["RZR_REG_IDENTITY"], "owner_pid": os.environ["RZR_REG_OWNER"],
        "created": os.environ["RZR_REG_TS"]}
if os.environ["RZR_REG_WT_NAME"]:
    data["watchtower_name"] = os.environ["RZR_REG_WT_NAME"]
if os.environ["RZR_REG_PRESET"]:
    data["preset"] = {"name": os.environ["RZR_REG_PRESET"],
                      "version": os.environ["RZR_REG_VERSION"] or "0",
                      "sha256": os.environ["RZR_REG_SHA"],
                      "model": os.environ["RZR_REG_MODEL"],
                      "effort": os.environ["RZR_REG_EFFORT"]}
    if os.environ["RZR_REG_POLICY_SHA"]:
        data["preset"]["policy_sha256"] = os.environ["RZR_REG_POLICY_SHA"]
if os.environ["RZR_REG_POLICY_SHA"]:
    data["policy_sha256"] = os.environ["RZR_REG_POLICY_SHA"]
record = {"ts": os.environ["RZR_REG_TS"], "driver_id": data["driver_id"],
          "harness": data["harness"], "backend": data["backend"], "identity": data["identity"]}
if "watchtower_name" in data: record["watchtower_name"] = data["watchtower_name"]
if "preset" in data: record["preset"] = data["preset"]
if "policy_sha256" in data: record["policy_sha256"] = data["policy_sha256"]
flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
try:
    logfd = os.open("registrations.jsonl", flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=dirfd)
except FileExistsError:
    before=os.stat("registrations.jsonl",dir_fd=dirfd,follow_symlinks=False)
    logfd=os.open("registrations.jsonl",flags,dir_fd=dirfd)
    if (before.st_dev,before.st_ino)!=(os.fstat(logfd).st_dev,os.fstat(logfd).st_ino):
        os.close(logfd); raise SystemExit("registrations log changed during open")
try:
    info = os.fstat(logfd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1: raise SystemExit("unsafe registrations log")
    log_identity=(info.st_dev,info.st_ino)
    os.fchmod(logfd, 0o600)
    tmp_created=False; tmp_identity=None; fd=None
    try:
        fd=os.open(tmp_name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|nofollow,0o600,dir_fd=dirfd)
        tmp_created=True; tmp_identity=(os.fstat(fd).st_dev,os.fstat(fd).st_ino)
        payload=json.dumps(data,indent=2).encode(); write_all(fd,payload); os.fsync(fd)
        replace_owned(dirfd,tmp_name,target_name,tmp_identity,fd)
        tmp_created=False
        os.fsync(dirfd)
        current=os.stat("registrations.jsonl",dir_fd=dirfd,follow_symlinks=False)
        if (current.st_dev,current.st_ino)!=(log_identity[0],log_identity[1]) or os.fstat(logfd).st_nlink != 1:
            raise SystemExit("registrations log changed before append")
        write_all(logfd,(json.dumps(record,separators=(",",":"))+"\n").encode()); os.fsync(logfd)
        current=os.stat("registrations.jsonl",dir_fd=dirfd,follow_symlinks=False)
        if (current.st_dev,current.st_ino)!=(log_identity[0],log_identity[1]) or os.fstat(logfd).st_nlink != 1:
            raise SystemExit("registrations log changed during append")
    finally:
        if fd is not None:
            if tmp_created:
                try: os.ftruncate(fd,0)
                except OSError: pass
                cleanup_owned(dirfd,tmp_name,tmp_identity)
            os.close(fd)
finally:
    os.close(logfd); os.close(dirfd)
PY

[ "$QUIET" -eq 1 ] || echo "$DRIVER_ID"
