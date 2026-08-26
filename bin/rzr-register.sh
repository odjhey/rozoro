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
# target.json is the authoritative current record. Registration writers for one
# driver serialize on an advisory lock. History is appended after the target
# commit; a later registration repairs a target-ahead history gap left by an
# abrupt process death before recording the next tenure.
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
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
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

rzr_validate_wt_metadata "$IDENTITY" "wake target identity"
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
import fcntl, json, math, os, secrets, stat

nofollow = getattr(os, "O_NOFOLLOW", 0)
directory = getattr(os, "O_DIRECTORY", 0)
nonblock = getattr(os, "O_NONBLOCK", 0)

def child(parent, name):
    try:
        os.mkdir(name, 0o700, dir_fd=parent)
    except FileExistsError:
        pass
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise SystemExit("unsafe watchtower directory")
    fd = os.open(name, os.O_RDONLY | directory | nofollow, dir_fd=parent)
    opened = os.fstat(fd)
    if (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
        os.close(fd)
        raise SystemExit("watchtower directory changed during open")
    os.fchmod(fd, 0o700)
    tightened = os.fstat(fd)
    if stat.S_IMODE(tightened.st_mode) != 0o700:
        os.close(fd)
        raise SystemExit("could not secure watchtower directory")
    return fd

def require_owned_regular(fd, what):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
        raise SystemExit(f"unsafe {what}")
    return info

def open_state_file(dirfd, name, flags, what):
    """Descriptor-relative, no-follow, race-safe create-or-open for macOS/Linux."""
    for _ in range(8):
        try:
            fd = os.open(name, flags | nofollow, dir_fd=dirfd)
        except FileNotFoundError:
            try:
                fd = os.open(name, flags | os.O_CREAT | os.O_EXCL | nofollow, 0o600, dir_fd=dirfd)
            except FileExistsError:
                continue
        info = require_owned_regular(fd, what)
        os.fchmod(fd, 0o600)
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
            os.close(fd)
            raise SystemExit(f"could not secure {what}")
        return fd
    raise SystemExit(f"could not create or open {what}")

def safe_string(value):
    return isinstance(value, str) and len(value) <= 120 and "=" not in value and not any(ord(c) < 32 or ord(c) == 127 for c in value)

def valid_registration_id(value):
    return safe_string(value) and bool(value)

def reject_constant(value):
    raise ValueError("non-standard JSON constant: " + value)

def valid_version(value):
    if isinstance(value, str):
        return safe_string(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return abs(value) <= 2**53 - 1 and len(str(value)) <= 120

def write_all(fd, payload):
    view = memoryview(payload)
    while view:
        count = os.write(fd, view)
        if count <= 0:
            raise OSError("short registration write")
        view = view[count:]

def record_from_target(data, *, recovered=False):
    if not isinstance(data, dict) or type(data.get("schema")) is not int or data["schema"] != 1:
        raise SystemExit("invalid registration schema")
    registration_id = data.get("registration_id")
    if not valid_registration_id(registration_id):
        raise SystemExit("invalid registration id")
    copied = ("created", "driver_id", "harness", "backend", "identity", "watchtower_name", "policy_sha256")
    if any(key in data and not safe_string(data[key]) for key in copied):
        raise SystemExit("invalid existing registration metadata")
    owner_pid = data.get("owner_pid")
    if owner_pid is not None and (not isinstance(owner_pid, str) or not owner_pid.isdigit() or not 1 <= int(owner_pid) <= 2**63 - 1):
        raise SystemExit("invalid existing registration owner pid")
    preset = data.get("preset")
    if preset is not None:
        if not isinstance(preset, dict):
            raise SystemExit("invalid existing registration preset")
        for key in ("name", "sha256", "policy_sha256", "model", "effort"):
            if key in preset and not safe_string(preset[key]):
                raise SystemExit("invalid existing registration preset")
        if "version" in preset and not valid_version(preset["version"]):
            raise SystemExit("invalid existing registration preset")
    record = {
        "schema": 1,
        "ts": data.get("created", "unknown"),
        "registration_id": registration_id,
        "driver_id": data.get("driver_id", ""),
        "harness": data.get("harness", ""),
        "backend": data.get("backend", ""),
        "identity": data.get("identity", ""),
    }
    if "watchtower_name" in data:
        record["watchtower_name"] = data["watchtower_name"]
    if preset is not None:
        record["preset"] = preset
    if "policy_sha256" in data:
        record["policy_sha256"] = data["policy_sha256"]
    if recovered:
        record["recovered"] = True
    return record

def last_history_registration_id(logfd):
    os.lseek(logfd, 0, os.SEEK_SET)
    last = ""
    stream = os.fdopen(os.dup(logfd), "r", encoding="utf-8", errors="strict")
    try:
        for line in stream:
            try:
                item = json.loads(line, parse_constant=reject_constant)
            except (UnicodeError, ValueError):
                raise SystemExit("invalid registrations history")
            if not isinstance(item, dict) or not valid_registration_id(item.get("registration_id")):
                raise SystemExit("invalid registrations history")
            last = item["registration_id"]
    finally:
        stream.close()
    return last

def read_current_target(dirfd):
    try:
        fd = os.open("target.json", os.O_RDONLY | nofollow | nonblock, dir_fd=dirfd)
    except FileNotFoundError:
        return None
    try:
        require_owned_regular(fd, "registration target")
        with os.fdopen(os.dup(fd), "r", encoding="utf-8") as stream:
            data = json.load(stream, parse_constant=reject_constant)
        if not isinstance(data, dict) or data.get("driver_id") != os.environ["RZR_REG_ID"] or not safe_string(data.get("driver_id")):
            raise SystemExit("invalid existing registration target")
        record_from_target(data)
        return data
    except (UnicodeError, ValueError, TypeError):
        raise SystemExit("invalid existing registration target")
    finally:
        os.close(fd)

home = os.environ["RZR_REG_HOME"]
before = os.stat(home, follow_symlinks=False)
root = os.open(home, os.O_RDONLY | directory | nofollow)
if (before.st_dev, before.st_ino) != (os.fstat(root).st_dev, os.fstat(root).st_ino):
    os.close(root)
    raise SystemExit("watchtower home changed during open")
try:
    towers = child(root, "watchtowers")
finally:
    os.close(root)
try:
    dirfd = child(towers, os.environ["RZR_REG_ID"])
finally:
    os.close(towers)

lockfd = None
logfd = None
tmp_fd = None
tmp_name = None
tmp_created = False
try:
    lockfd = open_state_file(dirfd, ".registration.lock", os.O_RDWR | nonblock, "registration lock")
    fcntl.flock(lockfd, fcntl.LOCK_EX)

    logfd = open_state_file(dirfd, "registrations.jsonl", os.O_RDWR | os.O_APPEND | nonblock, "registrations log")

    current = read_current_target(dirfd)
    last_history_id = last_history_registration_id(logfd)
    if current is not None:
        recovery = record_from_target(current, recovered=True)
        if recovery is not None and recovery["registration_id"] != last_history_id:
            write_all(logfd, (json.dumps(recovery, separators=(",", ":"), allow_nan=False) + "\n").encode())
            os.fsync(logfd)

    registration_id = secrets.token_hex(16)
    data = {
        "schema": 1,
        "registration_id": registration_id,
        "driver_id": os.environ["RZR_REG_ID"],
        "harness": os.environ["RZR_REG_HARNESS"],
        "backend": os.environ["RZR_REG_BACKEND"],
        "identity": os.environ["RZR_REG_IDENTITY"],
        "owner_pid": os.environ["RZR_REG_OWNER"],
        "created": os.environ["RZR_REG_TS"],
    }
    if os.environ["RZR_REG_WT_NAME"]:
        data["watchtower_name"] = os.environ["RZR_REG_WT_NAME"]
    if os.environ["RZR_REG_PRESET"]:
        data["preset"] = {
            "name": os.environ["RZR_REG_PRESET"],
            "version": os.environ["RZR_REG_VERSION"] or "0",
            "sha256": os.environ["RZR_REG_SHA"],
            "model": os.environ["RZR_REG_MODEL"],
            "effort": os.environ["RZR_REG_EFFORT"],
        }
        if os.environ["RZR_REG_POLICY_SHA"]:
            data["preset"]["policy_sha256"] = os.environ["RZR_REG_POLICY_SHA"]
    if os.environ["RZR_REG_POLICY_SHA"]:
        data["policy_sha256"] = os.environ["RZR_REG_POLICY_SHA"]

    record = record_from_target(data)
    tmp_name = ".target.%d.%s.tmp" % (os.getpid(), secrets.token_hex(12))
    os.umask(0o077)
    tmp_fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o600, dir_fd=dirfd)
    tmp_created = True
    write_all(tmp_fd, json.dumps(data, indent=2, allow_nan=False).encode())
    os.fsync(tmp_fd)
    os.close(tmp_fd)
    tmp_fd = None

    # target.json is the commit point and current source of truth.
    os.replace(tmp_name, "target.json", src_dir_fd=dirfd, dst_dir_fd=dirfd)
    tmp_created = False
    os.fsync(dirfd)

    write_all(logfd, (json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n").encode())
    os.fsync(logfd)
finally:
    if tmp_fd is not None:
        os.close(tmp_fd)
    if tmp_created and tmp_name is not None:
        try:
            os.unlink(tmp_name, dir_fd=dirfd)
        except FileNotFoundError:
            pass
    if logfd is not None:
        os.close(logfd)
    if lockfd is not None:
        try:
            fcntl.flock(lockfd, fcntl.LOCK_UN)
        finally:
            os.close(lockfd)
    os.close(dirfd)
PY

[ "$QUIET" -eq 1 ] || echo "$DRIVER_ID"
