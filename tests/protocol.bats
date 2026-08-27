#!/usr/bin/env bats
load test_helper/common

run_protocol_module() {
  # Python filesystem tests exercise ordinary process defaults explicitly.
  umask 022
  run env PYTHONPATH="$REPO_ROOT/tests/python:$REPO_ROOT/lib" python3 -m unittest -v "$1"
  assert_success
}

@test "protocol v1 Python contract: attention_ledger" {
  cd "$REPO_ROOT"
  run_protocol_module test_attention_ledger
}

@test "protocol v1 Python contract: claude_hook_capability" {
  cd "$REPO_ROOT"
  run_protocol_module test_claude_hook_capability
}

@test "protocol v1 Python contract: claude_producer" {
  cd "$REPO_ROOT"
  run_protocol_module test_claude_producer
}

@test "protocol v1 Python contract: claude_watchtower_poller" {
  cd "$REPO_ROOT"
  run_protocol_module test_claude_watchtower_poller
}

@test "protocol v1 Python contract: client" {
  cd "$REPO_ROOT"
  run_protocol_module test_client
}

@test "protocol v1 Python contract: codex_native_hook" {
  cd "$REPO_ROOT"
  run_protocol_module test_codex_native_hook
}

@test "protocol v1 Python contract: dated_artifact_skills" {
  cd "$REPO_ROOT"
  run_protocol_module test_dated_artifact_skills
}

@test "protocol v1 Python contract: delivery_ledger" {
  cd "$REPO_ROOT"
  run_protocol_module test_delivery_ledger
}

@test "protocol v1 Python contract: herdr" {
  cd "$REPO_ROOT"
  run_protocol_module test_herdr
}

@test "protocol v1 Python contract: monitor_lifecycle" {
  cd "$REPO_ROOT"
  run_protocol_module test_monitor_lifecycle
}

@test "protocol v1 Python contract: notify" {
  cd "$REPO_ROOT"
  run_protocol_module test_notify
}

@test "protocol v1 Python contract: policy_contracts" {
  cd "$REPO_ROOT"
  run_protocol_module test_policy_contracts
}

@test "protocol v1 Python contract: projections_report" {
  cd "$REPO_ROOT"
  run_protocol_module test_projections_report
}

@test "protocol v1 Python contract: protocol" {
  cd "$REPO_ROOT"
  run_protocol_module test_protocol
}

@test "protocol v1 Python contract: reducer" {
  cd "$REPO_ROOT"
  run_protocol_module test_reducer
}

@test "protocol v1 Python contract: server" {
  cd "$REPO_ROOT"
  run_protocol_module test_server
}

@test "protocol v1 Python contract: store" {
  cd "$REPO_ROOT"
  run_protocol_module test_store
}

@test "protocol v1 Python contract: watchtower_artifact_home_matrix" {
  cd "$REPO_ROOT"
  run_protocol_module test_watchtower_artifact_home_matrix
}

@test "protocol v1 Python contract: watchtower_docs" {
  cd "$REPO_ROOT"
  run_protocol_module test_watchtower_docs
}

@test "protocol v1 Python contract: watchtower_home_matrix" {
  cd "$REPO_ROOT"
  run_protocol_module test_watchtower_home_matrix
}

@test "protocol v1 Python contract: watchtower_home_source_audit" {
  cd "$REPO_ROOT"
  run_protocol_module test_watchtower_home_source_audit
}

@test "protocol v1 Python contract: watchtower_ledger_home_matrix" {
  cd "$REPO_ROOT"
  run_protocol_module test_watchtower_ledger_home_matrix
}

@test "protocol v1 Python contract: watchtower_monitor_home_matrix" {
  cd "$REPO_ROOT"
  run_protocol_module test_watchtower_monitor_home_matrix
}
