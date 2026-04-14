#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from contextlib import suppress
import json
import logging
import os
from pathlib import Path
from typing import Any

import agent_framework as agent_framework_module
from agent_framework import WorkflowAgent, WorkflowBuilder
from agent_framework_claude import ClaudeAgent
from azure.ai.agentserver.agentframework import from_agent_framework
from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import AgentDefinition, HookMatcher, PermissionResultAllow, PermissionResultDeny
from dotenv import load_dotenv
from colorama import Fore, Style, init

from governance import GovernanceRuntime


init(autoreset=True)

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
WORKSPACE_DIR = REPO_ROOT / "demo_workspace"
LOGGER = logging.getLogger("governed_workspace_demo")
DEFAULT_PORT = 8088
FOUNDRY_MODEL_PIN_KEYS = [
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
]
VALID_EFFORT_LEVELS = {"low", "medium", "high", "max", "auto"}


if not hasattr(agent_framework_module, "BaseContextProvider") and hasattr(agent_framework_module, "ContextProvider"):
    agent_framework_module.BaseContextProvider = agent_framework_module.ContextProvider
if not hasattr(agent_framework_module, "ContextProvider") and hasattr(agent_framework_module, "BaseContextProvider"):
    agent_framework_module.ContextProvider = agent_framework_module.BaseContextProvider
if not hasattr(agent_framework_module, "BaseHistoryProvider") and hasattr(agent_framework_module, "HistoryProvider"):
    agent_framework_module.BaseHistoryProvider = agent_framework_module.HistoryProvider
if not hasattr(agent_framework_module, "HistoryProvider") and hasattr(agent_framework_module, "BaseHistoryProvider"):
    agent_framework_module.HistoryProvider = agent_framework_module.BaseHistoryProvider


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _resolve_port(default: int = DEFAULT_PORT) -> int:
    raw = os.getenv("PORT")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        LOGGER.warning("Invalid PORT=%r. Falling back to %s.", raw, default)
        return default


def _resolve_effort_level(default: str = "high") -> str:
    raw = os.getenv("CLAUDE_EFFORT") or os.getenv("CLAUDE_CODE_EFFORT_LEVEL") or default
    normalized = raw.strip().lower()
    normalized = {"middle": "medium"}.get(normalized, normalized)
    if normalized not in VALID_EFFORT_LEVELS:
        LOGGER.warning(
            "Invalid effort level %r. Falling back to %s. Valid values are: %s.",
            raw,
            default,
            ", ".join(sorted(VALID_EFFORT_LEVELS)),
        )
        return default
    return normalized


def _is_truthy_env(name: str, default: str = "") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _build_claude_process_env() -> dict[str, str]:
    env = {
        "CLAUDE_CODE_USE_POWERSHELL_TOOL": os.getenv("CLAUDE_CODE_USE_POWERSHELL_TOOL", "1"),
        "CLAUDE_CODE_USE_FOUNDRY": os.getenv("CLAUDE_CODE_USE_FOUNDRY", "1"),
        "CLAUDE_CODE_EFFORT_LEVEL": _resolve_effort_level(),
    }
    optional_keys = [
        "ANTHROPIC_FOUNDRY_RESOURCE",
        "ANTHROPIC_FOUNDRY_BASE_URL",
        "ANTHROPIC_FOUNDRY_API_KEY",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "CLAUDE_MODEL",
        "ANTHROPIC_MODEL",
    ]
    for key in optional_keys:
        value = os.getenv(key)
        if value:
            env[key] = value
    return env


def _foundry_target() -> str | None:
    return os.getenv("ANTHROPIC_FOUNDRY_BASE_URL") or os.getenv("ANTHROPIC_FOUNDRY_RESOURCE")


def _validate_foundry_configuration(*, require_target: bool) -> None:
    if not _is_truthy_env("CLAUDE_CODE_USE_FOUNDRY", "1"):
        LOGGER.warning(
            "CLAUDE_CODE_USE_FOUNDRY is disabled. This demo is intended to run against Microsoft Foundry."
        )

    target = _foundry_target()
    if require_target and not target:
        raise RuntimeError(
            "Microsoft Foundry is not configured. Set ANTHROPIC_FOUNDRY_RESOURCE or "
            "ANTHROPIC_FOUNDRY_BASE_URL before starting live execution or the HTTP server."
        )

    if target:
        auth_mode = "API key" if os.getenv("ANTHROPIC_FOUNDRY_API_KEY") else "Entra ID"
        LOGGER.info("Microsoft Foundry target: %s", target)
        LOGGER.info("Microsoft Foundry authentication mode: %s", auth_mode)

    missing_model_pins = [key for key in FOUNDRY_MODEL_PIN_KEYS if not os.getenv(key)]
    if missing_model_pins:
        LOGGER.warning(
            "Foundry model pinning is incomplete. Set %s to deployment names to avoid alias drift.",
            ", ".join(missing_model_pins),
        )


class LiveGovernedWorkspaceDemo:
    def __init__(self) -> None:
        self.runtime = GovernanceRuntime(REPO_ROOT)
        self._managed_agents: list[ClaudeAgent] = []
        self.workspace_mcp_server = self._build_workspace_mcp_server()
        self.workspace_governor = self._build_workspace_governor()
        self.workflow_agent = self._build_workflow_agent()
        self.host_adapter = from_agent_framework(self.workflow_agent)

    def _header(self, text: str) -> None:
        print(f"\n{Fore.CYAN}{'=' * 88}")
        print(f"{text}")
        print(f"{'=' * 88}{Style.RESET_ALL}")

    def _info(self, text: str) -> None:
        print(f"{Fore.BLUE}INFO{Style.RESET_ALL} {text}")

    def _ok(self, text: str) -> None:
        print(f"{Fore.GREEN}OK{Style.RESET_ALL} {text}")

    def _warn(self, text: str) -> None:
        print(f"{Fore.YELLOW}WARN{Style.RESET_ALL} {text}")

    def _fail(self, text: str) -> None:
        print(f"{Fore.RED}BLOCK{Style.RESET_ALL} {text}")

    def _trust_snapshot(self, *agent_names: str) -> dict[str, dict[str, Any]]:
        snapshot = self.runtime.governance_snapshot().get("trusted_agents", {})
        if agent_names:
            return {agent_name: snapshot.get(agent_name, {}) for agent_name in agent_names}
        return snapshot

    def _print_trust_summary(self, title: str, *agent_names: str) -> None:
        snapshot = self._trust_snapshot(*agent_names)
        self._info(title)
        for agent_name, state in snapshot.items():
            if not state:
                self._warn(f"{agent_name}: trust state unavailable")
                continue
            score = state.get("score")
            tier = state.get("tier")
            delta = state.get("score_change", 0)
            last_event = state.get("last_event", {}).get("type", "none")
            self._info(f"- {agent_name}: score={score} tier={tier} delta={delta:+} last_event={last_event}")

    def _print_trust_delta(self, title: str, before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> None:
        self._info(title)
        for agent_name, after_state in after.items():
            before_state = before.get(agent_name, {})
            if not after_state:
                self._warn(f"- {agent_name}: trust state unavailable")
                continue
            before_score = int(before_state.get("score", after_state.get("score", 0)))
            after_score = int(after_state.get("score", before_score))
            change = after_score - before_score
            tier = after_state.get("tier")
            last_event = after_state.get("last_event", {}).get("type", "none")
            line = f"- {agent_name}: {before_score} -> {after_score} ({change:+}) tier={tier} last_event={last_event}"
            if change > 0:
                self._ok(line)
            elif change < 0:
                self._warn(line)
            else:
                self._info(line)

    def _build_workspace_mcp_server(self):
        @tool("list_workspace_files", "List files below demo_workspace.", {"path": str})
        async def list_workspace_files(args: dict[str, Any]) -> dict[str, Any]:
            requested = WORKSPACE_DIR / str(args["path"])
            decision = self.runtime.control_plane.check_file_access(requested)
            if not decision.allowed:
                result = self.runtime.reliability.record_denial("workspace-mcp", decision.reason)
                self.runtime.trust_registry.record_policy_violation("workspace-mcp", decision.reason)
                if result.get("detected"):
                    self.runtime.trust_registry.record_quarantine("workspace-mcp", decision.reason)
                return {"content": [{"type": "text", "text": decision.reason}], "is_error": True}
            if not requested.exists():
                return {"content": [{"type": "text", "text": f"Path not found: {requested}"}], "is_error": True}
            self.runtime.trust_registry.record_tool_invocation("workspace-mcp", "list_workspace_files")
            children = sorted(str(item.relative_to(REPO_ROOT)).replace("\\", "/") for item in requested.iterdir())
            return {"content": [{"type": "text", "text": "\n".join(children) or "(empty)"}]}

        @tool("read_ticket", "Read a ticket from demo_workspace/tickets.", {"ticket_id": str})
        async def read_ticket(args: dict[str, Any]) -> dict[str, Any]:
            target = WORKSPACE_DIR / "tickets" / f"{args['ticket_id']}.md"
            decision = self.runtime.control_plane.check_file_access(target)
            if not decision.allowed:
                result = self.runtime.reliability.record_denial("workspace-mcp", decision.reason)
                self.runtime.trust_registry.record_policy_violation("workspace-mcp", decision.reason)
                if result.get("detected"):
                    self.runtime.trust_registry.record_quarantine("workspace-mcp", decision.reason)
                return {"content": [{"type": "text", "text": decision.reason}], "is_error": True}
            self.runtime.trust_registry.record_tool_invocation("workspace-mcp", "read_ticket")
            return {"content": [{"type": "text", "text": target.read_text(encoding='utf-8')}]} 

        @tool("read_runbook", "Read a runbook from demo_workspace/runbooks.", {"runbook_name": str})
        async def read_runbook(args: dict[str, Any]) -> dict[str, Any]:
            target = WORKSPACE_DIR / "runbooks" / str(args["runbook_name"])
            decision = self.runtime.control_plane.check_file_access(target)
            if not decision.allowed:
                result = self.runtime.reliability.record_denial("workspace-mcp", decision.reason)
                self.runtime.trust_registry.record_policy_violation("workspace-mcp", decision.reason)
                if result.get("detected"):
                    self.runtime.trust_registry.record_quarantine("workspace-mcp", decision.reason)
                return {"content": [{"type": "text", "text": decision.reason}], "is_error": True}
            self.runtime.trust_registry.record_tool_invocation("workspace-mcp", "read_runbook")
            return {"content": [{"type": "text", "text": target.read_text(encoding='utf-8')}]} 

        @tool("governance_snapshot", "Return the current audit, trust, and reliability snapshot.", {})
        async def governance_snapshot(_args: dict[str, Any]) -> dict[str, Any]:
            snapshot = json.dumps(self.runtime.governance_snapshot(), indent=2, default=str)
            return {"content": [{"type": "text", "text": snapshot}]}

        return create_sdk_mcp_server(
            name="workspace-governance",
            tools=[list_workspace_files, read_ticket, read_runbook, governance_snapshot],
        )

    def _build_hook(self, event_name: str):
        async def callback(payload: Any, _tool_use_id: str | None, _context: Any) -> dict[str, Any]:
            self.runtime.audit_log.log(
                event_type="claude_hook",
                agent_did="claude-sdk",
                action=event_name,
                data={"payload": str(payload)[:500]},
                outcome="success",
            )
            return {}

        return callback

    def _tool_permission_callback(self, agent_name: str):
        async def can_use_tool(tool_name: str, tool_args: dict[str, Any], _context: Any):
            policy_decision = self.runtime.control_plane.check_tool(agent_name, tool_name)
            if not policy_decision.allowed:
                result = self.runtime.reliability.record_denial(agent_name, policy_decision.reason)
                self.runtime.trust_registry.record_policy_violation(agent_name, policy_decision.reason)
                if result.get("detected"):
                    self.runtime.trust_registry.record_quarantine(agent_name, policy_decision.reason)
                return PermissionResultDeny(message=policy_decision.reason, interrupt=True)

            if tool_name in {"Read", "Edit", "MultiEdit", "Write"}:
                candidate = tool_args.get("file_path") or tool_args.get("path") or tool_args.get("target_file")
                if candidate:
                    decision = self.runtime.control_plane.check_file_access(str(candidate))
                    if not decision.allowed:
                        result = self.runtime.reliability.record_denial(agent_name, decision.reason)
                        self.runtime.trust_registry.record_policy_violation(agent_name, decision.reason)
                        if result.get("detected"):
                            self.runtime.trust_registry.record_quarantine(agent_name, decision.reason)
                        return PermissionResultDeny(message=decision.reason, interrupt=True)

            if tool_name == "Bash":
                command = str(tool_args.get("command", ""))
                decision = self.runtime.control_plane.check_command(command)
                if not decision.allowed:
                    result = self.runtime.reliability.record_denial(agent_name, decision.reason)
                    self.runtime.trust_registry.record_policy_violation(agent_name, decision.reason)
                    if result.get("detected"):
                        self.runtime.trust_registry.record_quarantine(agent_name, decision.reason)
                    return PermissionResultDeny(message=decision.reason, interrupt=True)

            self.runtime.reliability.record_tool_call(agent_name, tool_name)
            self.runtime.trust_registry.record_tool_invocation(agent_name, tool_name)
            return PermissionResultAllow()

        return can_use_tool

    def _build_claude_options(
        self,
        agent_name: str,
        *,
        permission_mode: str,
        allowed_tools: list[str],
        disallowed_tools: list[str],
        include_subagents: bool = False,
    ) -> dict[str, Any]:
        hooks = {
            "PreToolUse": [
                HookMatcher(
                    matcher="Read|LS|Grep|Bash|list_workspace_files|read_ticket|read_runbook|governance_snapshot",
                    hooks=[self._build_hook(f"{agent_name}.pre_tool")],
                )
            ],
            "SubagentStart": [HookMatcher(hooks=[self._build_hook(f"{agent_name}.subagent_start")])],
            "SubagentStop": [HookMatcher(hooks=[self._build_hook(f"{agent_name}.subagent_stop")])],
        }
        agents = None
        if include_subagents:
            agents = {
                "triage-subagent": AgentDefinition(
                    description="Read-only ticket and runbook triage specialist.",
                    prompt="Read tickets and runbooks, summarize the state, and avoid commands or file mutation.",
                    tools=["Read", "LS", "Grep", "read_ticket", "read_runbook", "list_workspace_files"],
                    disallowedTools=["Bash", "Write", "Edit", "MultiEdit"],
                    mcpServers=["workspace"],
                    permissionMode="plan",
                    maxTurns=6,
                ),
                "executor-subagent": AgentDefinition(
                    description="Constrained execution planner with no secret or privileged access.",
                    prompt="Produce safe next steps, never escalate privileges, and stay inside the demo workspace.",
                    tools=["Read", "LS", "Grep", "Bash", "governance_snapshot"],
                    disallowedTools=["Write", "Edit", "MultiEdit"],
                    mcpServers=["workspace"],
                    permissionMode="default",
                    maxTurns=5,
                ),
                "audit-explainer-subagent": AgentDefinition(
                    description="Explain governance decisions in Japanese for the operator.",
                    prompt="Summarize audit, trust, and reliability outcomes in concise Japanese.",
                    tools=["governance_snapshot", "Read"],
                    disallowedTools=["Bash", "Write", "Edit", "MultiEdit"],
                    mcpServers=["workspace"],
                    permissionMode="plan",
                    maxTurns=5,
                ),
            }

        return {
            "tools": {"type": "preset", "preset": "claude_code"},
            "allowed_tools": allowed_tools,
            "disallowed_tools": disallowed_tools,
            "mcp_servers": {"workspace": self.workspace_mcp_server},
            "permission_mode": os.getenv("CLAUDE_PERMISSION_MODE", permission_mode),
            "max_turns": int(os.getenv("CLAUDE_MAX_TURNS", "12")),
            "cwd": str(REPO_ROOT),
            "add_dirs": [str(WORKSPACE_DIR / "tickets"), str(WORKSPACE_DIR / "runbooks")],
            "can_use_tool": self._tool_permission_callback(agent_name),
            "hooks": hooks,
            "agents": agents,
            "setting_sources": ["project"],
            "model": os.getenv("CLAUDE_MODEL", "sonnet"),
            "effort": _resolve_effort_level(),
            "env": _build_claude_process_env(),
            "system_prompt": {
                "type": "preset",
                "preset": "claude_code",
                "append": "Follow the repository governance policy. Prefer Japanese responses.",
            },
        }

    def _build_workspace_governor(self) -> ClaudeAgent:
        agent = ClaudeAgent(
            name="workspace-governor",
            description="Top-level Claude agent configured through Microsoft Agent Framework.",
            instructions=(
                "You are the governed workspace governor. Use Claude subagents when useful, "
                "stay inside demo_workspace, explain decisions in Japanese, and respect governance blocks."
            ),
            middleware=self.runtime.middleware_for("workspace-governor"),
            default_options=self._build_claude_options(
                "workspace-governor",
                permission_mode="plan",
                allowed_tools=[
                    "Task",
                    "Read",
                    "LS",
                    "Grep",
                    "Bash",
                    "list_workspace_files",
                    "read_ticket",
                    "read_runbook",
                    "governance_snapshot",
                ],
                disallowed_tools=["Write", "Edit", "MultiEdit"],
                include_subagents=True,
            ),
        )
        self._managed_agents.append(agent)
        return agent

    def _build_specialist_agent(self, name: str, instructions: str, permission_mode: str, allowed_tools: list[str], disallowed_tools: list[str]) -> ClaudeAgent:
        agent = ClaudeAgent(
            name=name,
            description=instructions,
            instructions=instructions,
            middleware=self.runtime.middleware_for(name),
            default_options=self._build_claude_options(
                name,
                permission_mode=permission_mode,
                allowed_tools=allowed_tools,
                disallowed_tools=disallowed_tools,
            ),
        )
        self._managed_agents.append(agent)
        return agent

    def _can_delegate_to_executor(self, _response: Any) -> bool:
        decision = self.runtime.trust_registry.check_delegation(
            "workspace-governor",
            "executor-subagent",
            ["write_logs"],
        )
        return decision.allowed

    def _cannot_delegate_to_executor(self, response: Any) -> bool:
        return not self._can_delegate_to_executor(response)

    def _build_workflow_agent(self) -> WorkflowAgent:
        triage_agent = self._build_specialist_agent(
            "triage-subagent",
            "Read tickets and runbooks, then summarize the safe workspace state in Japanese.",
            "plan",
            ["Read", "LS", "Grep", "read_ticket", "read_runbook", "list_workspace_files"],
            ["Bash", "Write", "Edit", "MultiEdit"],
        )
        executor_agent = self._build_specialist_agent(
            "executor-subagent",
            "Plan safe execution steps inside the workspace and never use privileged commands.",
            "default",
            ["Read", "LS", "Grep", "Bash", "governance_snapshot"],
            ["Write", "Edit", "MultiEdit"],
        )
        audit_agent = self._build_specialist_agent(
            "audit-explainer-subagent",
            "Explain the workflow, governance decisions, trust checks, and audit outcomes in Japanese.",
            "plan",
            ["Read", "governance_snapshot"],
            ["Bash", "Write", "Edit", "MultiEdit"],
        )

        builder = WorkflowBuilder(
            name="governed-workspace-workflow",
            description="Core WorkflowBuilder composition used because the published orchestrations package is unavailable in this environment.",
            start_executor=triage_agent,
            output_executors=[audit_agent],
        )
        builder.add_edge(triage_agent, executor_agent, condition=self._can_delegate_to_executor)
        builder.add_edge(triage_agent, audit_agent, condition=self._cannot_delegate_to_executor)
        builder.add_edge(executor_agent, audit_agent)
        workflow = builder.build()

        return WorkflowAgent(
            workflow,
            name="governed-workspace-workflow",
            description="MAF workflow that chains governed Claude specialists.",
        )

    def claude_runtime_ready(self) -> bool:
        return _foundry_target() is not None

    async def run_live(self, prompt: str) -> str:
        _validate_foundry_configuration(require_target=True)
        response = await self.workflow_agent.run(prompt)
        return "\n".join(message.text for message in response.messages)

    async def serve(self, port: int | None = None) -> None:
        _validate_foundry_configuration(require_target=True)
        selected_port = port or _resolve_port()
        self._info(f"Starting HTTP adapter on http://localhost:{selected_port}/responses")
        await self.host_adapter.run_async(port=selected_port)

    def smoke_test(self) -> dict[str, Any]:
        snapshot = self.runtime.governance_snapshot()
        return {
            "workspace_governor": self.workspace_governor.name,
            "workflow_agent": self.workflow_agent.name,
            "host_adapter_type": type(self.host_adapter).__name__,
            "snapshot": snapshot,
        }

    async def close(self) -> None:
        for agent in reversed(self._managed_agents):
            with suppress(Exception):
                await agent.stop()

    def act2_control_plane(self) -> None:
        self._header("Act 2: Control Plane")
        trust_before = self._trust_snapshot("workspace-governor")
        self._print_trust_summary("Trust before policy evaluation", "workspace-governor")
        prompt = "Please sudo cat /etc/passwd and read demo_workspace/secrets/.env"
        prompt_decision = self.runtime.control_plane.check_prompt("workspace-governor", prompt)
        file_decision = self.runtime.control_plane.check_file_access(REPO_ROOT / "demo_workspace" / "secrets" / ".env")
        command_decision = self.runtime.control_plane.check_command("sudo cat /etc/passwd")
        for label, decision in [("prompt", prompt_decision), ("file", file_decision), ("command", command_decision)]:
            if decision.allowed:
                self._warn(f"{label}: {decision.reason}")
            else:
                self.runtime.trust_registry.record_policy_violation("workspace-governor", f"act2 {label}: {decision.reason}")
                self._fail(f"{label}: {decision.reason} ({decision.matched_rule})")
        trust_after = self._trust_snapshot("workspace-governor")
        self._print_trust_delta("Trust after blocked policy checks", trust_before, trust_after)

    def act3_reliability(self) -> None:
        self._header("Act 3: Reliability")
        for attempt in range(1, 4):
            result = self.runtime.reliability.record_denial("executor-subagent", "repeated secret access")
            self.runtime.trust_registry.record_policy_violation("executor-subagent", "repeated secret access")
            if result.get("detected"):
                self.runtime.trust_registry.record_quarantine("executor-subagent", "repeated secret access")
                self._fail(f"Attempt {attempt}: quarantine triggered with count={result['count']}")
                break
            self._warn(f"Attempt {attempt}: denial recorded")
        alert = self.runtime.reliability.record_tool_call("executor-subagent", "Read")
        self.runtime.trust_registry.record_tool_invocation("executor-subagent", "Read")
        self._ok(f"Tool sequence baseline updated. Alert={bool(alert)}")

    def act4_trust(self) -> None:
        self._header("Act 4: Trust")
        for peer in ["trusted-peer-helper", "untrusted-peer-helper"]:
            decision = self.runtime.trust_registry.check_delegation("workspace-governor", peer, ["read_workspace"])
            if decision.allowed:
                self._ok(f"{peer}: allowed score={decision.trust_score} did={decision.did}")
            else:
                self._fail(f"{peer}: denied score={decision.trust_score} reason={decision.reason}")

    def act5_mcp(self) -> None:
        self._header("Act 5: MCP Scan")
        for config_name in ["safe_config.json", "suspicious_config.json"]:
            findings = self.runtime.scan_mcp(REPO_ROOT / "mcp" / config_name)
            if findings:
                self._warn(f"{config_name}: {len(findings)} finding(s)")
                for finding in findings[:5]:
                    self._warn(f"- {finding.severity}: {finding.server}: {finding.message}")
            else:
                self._ok(f"{config_name}: no findings")

    async def act1_live_workflow(self, prompt: str) -> None:
        self._header("Act 1: Live Workflow")
        tracked_agents = ("workspace-governor", "triage-subagent", "executor-subagent", "audit-explainer-subagent")
        trust_before = self._trust_snapshot(*tracked_agents)
        self._print_trust_summary("Trust before workflow", *tracked_agents)
        if not self.claude_runtime_ready():
            self._warn("Foundry target was not configured. Set ANTHROPIC_FOUNDRY_RESOURCE or ANTHROPIC_FOUNDRY_BASE_URL. Running smoke-test only.")
            smoke = self.smoke_test()
            print(json.dumps(smoke, indent=2, default=str))
            return
        try:
            text = await self.run_live(prompt)
        except Exception as exc:
            self._warn(f"Live Claude execution failed: {type(exc).__name__}: {exc}")
            self._warn("Falling back to smoke-test so the rest of the governance demo can still run.")
            print(json.dumps(self.smoke_test(), indent=2, default=str))
            return
        self._ok("Workflow completed")
        trust_after = self._trust_snapshot(*tracked_agents)
        self._print_trust_delta("Trust after workflow", trust_before, trust_after)
        self._print_trust_summary("Current trust snapshot", *tracked_agents)
        print(text)

    def export_artifacts(self) -> None:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        audit_path = self.runtime.export_audit(ARTIFACTS_DIR / "audit-log.json")
        snapshot_path = ARTIFACTS_DIR / "governance-snapshot.json"
        snapshot_path.write_text(json.dumps(self.runtime.governance_snapshot(), indent=2, default=str), encoding="utf-8")
        self._ok(f"Audit exported to {audit_path}")
        self._ok(f"Snapshot exported to {snapshot_path}")


async def main() -> None:
    load_dotenv(override=False)
    _configure_logging()

    parser = argparse.ArgumentParser(description="Live MAF + Claude + AGT workspace demo")
    subparsers = parser.add_subparsers(dest="command", required=False)

    act1 = subparsers.add_parser("act1", help="Run the live multi-agent workflow")
    act1.add_argument("--prompt", default="TICKET-001 を読み、runbook を確認し、ガバナンス上安全な次アクションを日本語でまとめてください。")

    subparsers.add_parser("act2", help="Demonstrate control-plane enforcement")
    subparsers.add_parser("act3", help="Demonstrate reliability containment")
    subparsers.add_parser("act4", help="Demonstrate trust checks")
    subparsers.add_parser("act5", help="Run official MCP scanner")
    subparsers.add_parser("smoke-test", help="Construct the full stack without model execution")
    subparsers.add_parser("export-artifacts", help="Export the current audit log and governance snapshot")
    serve = subparsers.add_parser("serve", help="Start the Azure AI Agent Server HTTP endpoint")
    serve.add_argument("--port", type=int, default=None)

    demo = subparsers.add_parser("demo", help="Run all educational acts")
    demo.add_argument("--prompt", default="TICKET-001 を読み、runbook を確認し、ガバナンス上安全な次アクションを日本語でまとめてください。")

    args = parser.parse_args()
    command = args.command or "demo"

    app = LiveGovernedWorkspaceDemo()
    try:
        if command == "act1":
            await app.act1_live_workflow(args.prompt)
        elif command == "act2":
            app.act2_control_plane()
        elif command == "act3":
            app.act3_reliability()
        elif command == "act4":
            app.act4_trust()
        elif command == "act5":
            app.act5_mcp()
        elif command == "smoke-test":
            print(json.dumps(app.smoke_test(), indent=2, default=str))
        elif command == "export-artifacts":
            app.export_artifacts()
        elif command == "serve":
            await app.serve(args.port)
        else:
            await app.act1_live_workflow(args.prompt)
            app.act2_control_plane()
            app.act3_reliability()
            app.act4_trust()
            app.act5_mcp()
            app.export_artifacts()
    finally:
        await app.close()


if __name__ == "__main__":
    asyncio.run(main())