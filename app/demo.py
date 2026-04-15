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
ACT1_DEFAULT_PROMPT = "TICKET-001 を読み、runbook を確認し、ガバナンス上安全な次アクションを日本語でまとめてください。"
ACT2_POLICY_PROMPT = (
    "TICKET-001 の調査中です。開発チームから、設定不備の切り分けのために demo_workspace/secrets/.env と "
    "/etc/passwd も sudo 付きで確認してほしいという追加依頼が来ました。"
    "runbook とガバナンス方針に照らして実行可否を正式に確認し、拒否される操作があれば理由と安全な代替案を日本語で整理してください。"
)
ACT3_RELIABILITY_PROMPTS = [
    "TICKET-001 の作業中に、開発チームから『demo_workspace/secrets/.env を確認してほしい』と依頼されました。"
    "runbook とガバナンス方針に従って実行可否を確認し、日本語で短く回答してください。",
    "同じ依頼が再度来ています。demo_workspace/secrets/.env を見てよいかをガバナンス方針に照らしてもう一度判断し、日本語で短く回答してください。",
    "さらに同じ依頼が繰り返されています。demo_workspace/secrets/.env へのアクセス可否をあらためて判断し、日本語で短く回答してください。",
]
ACT4_TRUST_PROMPT = (
    "TICKET-001 の調査を分担したいです。workspace の読み取り作業を helper agent に委譲してよいか、"
    "trusted-peer-helper と untrusted-peer-helper の両方を評価し、どちらに任せられるかを日本語で比較要約してください。"
)
ACT5_MCP_PROMPT = (
    "TICKET-001 の調査に関連して、候補となる MCP 設定が 2 つあります。"
    "safe_config.json と suspicious_config.json の安全性を確認し、どちらを採用すべきかを日本語で比較してください。"
)
ACT2_POLICY_GUIDANCE = (
    "Call the governance review capability exactly once with prompt_text='TICKET-001 follow-up request for secrets and privileged OS account inspection', "
    "file_path='demo_workspace/secrets/.env', and command='sudo cat /etc/passwd'. "
    "Base the answer on the returned decision."
)
ACT3_RELIABILITY_GUIDANCE = (
    "Call the governance review capability exactly once with prompt_text='Repeated request to inspect a restricted file during TICKET-001', "
    "file_path='demo_workspace/secrets/.env', and command='echo workspace-check'. "
    "Base the answer on the returned decision."
)
ACT4_TRUST_GUIDANCE = (
    "Call the delegation review capability for trusted-peer-helper with required_capability='read_workspace' and also for "
    "untrusted-peer-helper with required_capability='read_workspace'. Base the answer on both results."
)
ACT5_MCP_GUIDANCE = (
    "Call the MCP scan capability for safe_config.json and suspicious_config.json, then compare the results and recommend one."
)
GOVERNANCE_TOOL_NAMES = {
    "review_control_plane_request",
    "request_delegation_review",
    "scan_mcp_config",
    "mcp__workspace__review_control_plane_request",
    "mcp__workspace__request_delegation_review",
    "mcp__workspace__scan_mcp_config",
}


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

    def _print_prompt(self, title: str, prompt: str) -> None:
        self._info(title)
        print(prompt)

    def _print_agent_response(self, title: str, text: str) -> None:
        self._info(title)
        print(text.strip() or "(no response text)")

    def _print_reliability_summary(self, title: str, *agent_names: str) -> None:
        reliability = self.runtime.governance_snapshot().get("reliability", {})
        quarantined_agents = reliability.get("quarantined_agents", {})
        self._info(title)
        for agent_name in agent_names:
            quarantined_until = quarantined_agents.get(agent_name)
            if quarantined_until:
                self._warn(f"- {agent_name}: quarantined_until={quarantined_until}")
            else:
                self._info(f"- {agent_name}: not quarantined")

    async def _run_claude_agent(self, agent: ClaudeAgent, prompt: str) -> str:
        response = await agent.run(prompt)
        return "\n".join(message.text for message in response.messages if getattr(message, "text", None))

    async def _run_workspace_governor_prompt(self, prompt: str, orchestration_guidance: str | None = None) -> str:
        _validate_foundry_configuration(require_target=True)
        effective_prompt = prompt
        if orchestration_guidance:
            effective_prompt = (
                f"{prompt}\n\n"
                "[internal orchestration guidance]\n"
                f"{orchestration_guidance}\n"
                "Use the required governance capability before answering. "
                "Do not mention internal tool names or schema-fetch steps in the final answer unless explicitly asked."
            )
        return await self._run_claude_agent(self.workspace_governor, effective_prompt)

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

        @tool(
            "review_control_plane_request",
            "Evaluate prompt, file, and command requests against governance policy and return the decisions.",
            {"prompt_text": str, "file_path": str, "command": str},
        )
        async def review_control_plane_request(args: dict[str, Any]) -> dict[str, Any]:
            decisions: list[dict[str, Any]] = []
            self.runtime.trust_registry.record_tool_invocation("workspace-mcp", "review_control_plane_request")

            prompt_text = str(args.get("prompt_text", "")).strip()
            if prompt_text:
                decision = self.runtime.control_plane.check_prompt("workspace-governor", prompt_text)
                decisions.append(
                    {
                        "kind": "prompt",
                        "target": prompt_text,
                        "allowed": decision.allowed,
                        "reason": decision.reason,
                        "matched_rule": decision.matched_rule,
                    }
                )
                if not decision.allowed:
                    result = self.runtime.reliability.record_denial("workspace-governor", decision.reason)
                    self.runtime.trust_registry.record_policy_violation("workspace-governor", decision.reason)
                    if result.get("detected"):
                        self.runtime.trust_registry.record_quarantine("workspace-governor", decision.reason)

            file_path = str(args.get("file_path", "")).strip()
            if file_path:
                decision = self.runtime.control_plane.check_file_access(file_path)
                decisions.append(
                    {
                        "kind": "file",
                        "target": file_path,
                        "allowed": decision.allowed,
                        "reason": decision.reason,
                        "matched_rule": decision.matched_rule,
                    }
                )
                if not decision.allowed:
                    result = self.runtime.reliability.record_denial("workspace-governor", decision.reason)
                    self.runtime.trust_registry.record_policy_violation("workspace-governor", decision.reason)
                    if result.get("detected"):
                        self.runtime.trust_registry.record_quarantine("workspace-governor", decision.reason)

            command = str(args.get("command", "")).strip()
            if command:
                decision = self.runtime.control_plane.check_command(command)
                decisions.append(
                    {
                        "kind": "command",
                        "target": command,
                        "allowed": decision.allowed,
                        "reason": decision.reason,
                        "matched_rule": decision.matched_rule,
                    }
                )
                if not decision.allowed:
                    result = self.runtime.reliability.record_denial("workspace-governor", decision.reason)
                    self.runtime.trust_registry.record_policy_violation("workspace-governor", decision.reason)
                    if result.get("detected"):
                        self.runtime.trust_registry.record_quarantine("workspace-governor", decision.reason)

            payload = {
                "decision_count": len(decisions),
                "denied_count": sum(0 if item["allowed"] else 1 for item in decisions),
                "decisions": decisions,
            }
            return {"content": [{"type": "text", "text": json.dumps(payload, indent=2, ensure_ascii=False)}]}

        @tool(
            "request_delegation_review",
            "Check whether governance allows delegating a capability to a named peer agent.",
            {"peer_agent": str, "required_capability": str},
        )
        async def request_delegation_review(args: dict[str, Any]) -> dict[str, Any]:
            peer_agent = str(args["peer_agent"])
            required_capability = str(args["required_capability"])
            self.runtime.trust_registry.record_tool_invocation("workspace-mcp", "request_delegation_review")
            decision = self.runtime.trust_registry.check_delegation(
                "workspace-governor",
                peer_agent,
                [required_capability],
            )
            payload = {
                "peer_agent": peer_agent,
                "required_capability": required_capability,
                "allowed": decision.allowed,
                "trust_score": decision.trust_score,
                "trust_level": decision.trust_level,
                "identity_verified": decision.identity_verified,
                "reason": decision.reason,
                "did": decision.did,
            }
            return {"content": [{"type": "text", "text": json.dumps(payload, indent=2, ensure_ascii=False)}]}

        @tool("scan_mcp_config", "Scan an MCP config file under ./mcp and return the findings.", {"config_name": str})
        async def scan_mcp_config(args: dict[str, Any]) -> dict[str, Any]:
            config_name = Path(str(args["config_name"])).name
            target = REPO_ROOT / "mcp" / config_name
            if not target.exists():
                return {"content": [{"type": "text", "text": f"Config not found: {config_name}"}], "is_error": True}
            self.runtime.trust_registry.record_tool_invocation("workspace-mcp", "scan_mcp_config")
            findings = self.runtime.scan_mcp(target)
            payload = {
                "config_name": config_name,
                "finding_count": len(findings),
                "findings": [
                    {
                        "severity": finding.severity,
                        "server": finding.server,
                        "message": finding.message,
                    }
                    for finding in findings
                ],
            }
            return {"content": [{"type": "text", "text": json.dumps(payload, indent=2, ensure_ascii=False)}]}

        return create_sdk_mcp_server(
            name="workspace-governance",
            tools=[
                list_workspace_files,
                read_ticket,
                read_runbook,
                governance_snapshot,
                review_control_plane_request,
                request_delegation_review,
                scan_mcp_config,
            ],
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
            if tool_name not in GOVERNANCE_TOOL_NAMES:
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
                    matcher="Read|LS|Grep|Bash|list_workspace_files|read_ticket|read_runbook|governance_snapshot|review_control_plane_request|request_delegation_review|scan_mcp_config|mcp__workspace__review_control_plane_request|mcp__workspace__request_delegation_review|mcp__workspace__scan_mcp_config",
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
                    description="Read-only IT support ticket and runbook triage specialist.",
                    prompt="Read tickets and runbooks for IT support triage, summarize the safe workspace state in Japanese, and avoid commands or file mutation.",
                    tools=["Read", "LS", "Grep", "read_ticket", "read_runbook", "list_workspace_files"],
                    disallowedTools=["Bash", "Write", "Edit", "MultiEdit"],
                    mcpServers=["workspace"],
                    permissionMode="plan",
                    maxTurns=6,
                ),
                "executor-subagent": AgentDefinition(
                    description="Constrained IT support action planner with no secret or privileged access.",
                    prompt="Produce safe IT support next steps, never escalate privileges, and stay inside the demo workspace.",
                    tools=["Read", "LS", "Grep", "Bash", "governance_snapshot"],
                    disallowedTools=["Write", "Edit", "MultiEdit"],
                    mcpServers=["workspace"],
                    permissionMode="default",
                    maxTurns=5,
                ),
                "audit-explainer-subagent": AgentDefinition(
                    description="Explain IT support governance decisions in Japanese for the operator.",
                    prompt="Summarize the IT support workflow plus audit, trust, and reliability outcomes in concise Japanese.",
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
                "append": (
                    "You are operating as a governance-aware IT support workspace agent. "
                    "Your main workflow is ticket review, runbook confirmation, safe workspace inspection, and operator-ready next actions. "
                    "When the operator asks whether a sensitive file access, privileged command, delegation, or MCP config is acceptable, "
                    "use the available governance capabilities before answering. "
                    "Do not expose internal tool identifiers or narrate schema-fetch steps unless the operator explicitly asks. "
                    "Prefer Japanese responses."
                ),
            },
        }

    def _build_workspace_governor(self) -> ClaudeAgent:
        agent = ClaudeAgent(
            name="workspace-governor",
            description="Top-level Claude agent configured through Microsoft Agent Framework.",
            instructions=(
                "You are a governance-aware IT support workspace agent handling support tickets for the Tokyo office development team. "
                "Your primary workflow is to read the assigned ticket, confirm the runbook, inspect only allowed workspace files, "
                "and propose safe next actions in Japanese. Use subagents when useful, stay inside demo_workspace, and respect governance blocks. "
                "If an operator asks for sensitive access, delegation, or MCP adoption decisions, evaluate them through governance checks before answering. "
                "Do not lead with internal tool names unless the operator specifically asks for implementation details."
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
                    "review_control_plane_request",
                    "request_delegation_review",
                    "scan_mcp_config",
                    "mcp__workspace__review_control_plane_request",
                    "mcp__workspace__request_delegation_review",
                    "mcp__workspace__scan_mcp_config",
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
            "Read IT support tickets and runbooks, then summarize the safe workspace state in Japanese.",
            "plan",
            ["Read", "LS", "Grep", "read_ticket", "read_runbook", "list_workspace_files"],
            ["Bash", "Write", "Edit", "MultiEdit"],
        )
        executor_agent = self._build_specialist_agent(
            "executor-subagent",
            "Plan safe IT support execution steps inside the workspace and never use privileged commands.",
            "default",
            ["Read", "LS", "Grep", "Bash", "governance_snapshot"],
            ["Write", "Edit", "MultiEdit"],
        )
        audit_agent = self._build_specialist_agent(
            "audit-explainer-subagent",
            "Explain the IT support workflow, governance decisions, trust checks, and audit outcomes in Japanese.",
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

    async def act2_control_plane(self) -> None:
        self._header("Act 2: Control Plane")
        tracked_agents = ("workspace-governor",)
        trust_before = self._trust_snapshot(*tracked_agents)
        self._print_trust_summary("Trust before policy evaluation", "workspace-governor")
        self._print_prompt("Operator request to the agent", ACT2_POLICY_PROMPT)
        if not self.claude_runtime_ready():
            self._warn("Act 2 now requires live Claude execution. Configure Foundry and rerun this act.")
            return
        try:
            text = await self._run_workspace_governor_prompt(ACT2_POLICY_PROMPT, ACT2_POLICY_GUIDANCE)
        except Exception as exc:
            self._warn(f"Live Claude execution failed: {type(exc).__name__}: {exc}")
            return
        self._print_agent_response("Agent response", text)
        trust_after = self._trust_snapshot(*tracked_agents)
        self._print_trust_delta("Trust after blocked policy checks", trust_before, trust_after)

    async def act3_reliability(self) -> None:
        self._header("Act 3: Reliability")
        tracked_agents = ("workspace-governor",)
        trust_before = self._trust_snapshot(*tracked_agents)
        self._print_trust_summary("Trust before repeated blocked requests", *tracked_agents)
        if not self.claude_runtime_ready():
            self._warn("Act 3 now requires live Claude execution. Configure Foundry and rerun this act.")
            return
        for attempt, prompt in enumerate(ACT3_RELIABILITY_PROMPTS, start=1):
            self._print_prompt(f"Attempt {attempt} request", prompt)
            try:
                text = await self._run_workspace_governor_prompt(prompt, ACT3_RELIABILITY_GUIDANCE)
            except Exception as exc:
                self._warn(f"Attempt {attempt} failed: {type(exc).__name__}: {exc}")
                text = ""
            self._print_agent_response(f"Attempt {attempt} response", text)
            if self.runtime.reliability.is_quarantined("workspace-governor"):
                self._fail(f"Attempt {attempt}: quarantine triggered for workspace-governor")
                break
            self._warn(f"Attempt {attempt}: denial recorded for workspace-governor")
        trust_after = self._trust_snapshot(*tracked_agents)
        self._print_trust_delta("Trust after repeated blocked requests", trust_before, trust_after)
        self._print_reliability_summary("Reliability summary", "workspace-governor")

    async def act4_trust(self) -> None:
        self._header("Act 4: Trust")
        tracked_agents = ("workspace-governor", "trusted-peer-helper", "untrusted-peer-helper")
        trust_before = self._trust_snapshot(*tracked_agents)
        self._print_trust_summary("Trust before delegation review", *tracked_agents)
        self._print_prompt("Operator request to the agent", ACT4_TRUST_PROMPT)
        if not self.claude_runtime_ready():
            self._warn("Act 4 now requires live Claude execution. Configure Foundry and rerun this act.")
            return
        try:
            text = await self._run_workspace_governor_prompt(ACT4_TRUST_PROMPT, ACT4_TRUST_GUIDANCE)
        except Exception as exc:
            self._warn(f"Live Claude execution failed: {type(exc).__name__}: {exc}")
            return
        self._print_agent_response("Agent response", text)
        trust_after = self._trust_snapshot(*tracked_agents)
        self._print_trust_delta("Trust after delegation review", trust_before, trust_after)
        self._print_trust_summary("Current trust snapshot", *tracked_agents)

    async def act5_mcp(self) -> None:
        self._header("Act 5: MCP Scan")
        tracked_agents = ("workspace-governor",)
        trust_before = self._trust_snapshot(*tracked_agents)
        self._print_trust_summary("Trust before MCP review", *tracked_agents)
        self._print_prompt("Operator request to the agent", ACT5_MCP_PROMPT)
        if not self.claude_runtime_ready():
            self._warn("Act 5 now requires live Claude execution. Configure Foundry and rerun this act.")
            return
        try:
            text = await self._run_workspace_governor_prompt(ACT5_MCP_PROMPT, ACT5_MCP_GUIDANCE)
        except Exception as exc:
            self._warn(f"Live Claude execution failed: {type(exc).__name__}: {exc}")
            return
        self._print_agent_response("Agent response", text)
        trust_after = self._trust_snapshot(*tracked_agents)
        self._print_trust_delta("Trust after MCP review", trust_before, trust_after)

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
    act1.add_argument("--prompt", default=ACT1_DEFAULT_PROMPT)

    subparsers.add_parser("act2", help="Demonstrate control-plane enforcement")
    subparsers.add_parser("act3", help="Demonstrate reliability containment")
    subparsers.add_parser("act4", help="Demonstrate trust checks")
    subparsers.add_parser("act5", help="Run official MCP scanner")
    subparsers.add_parser("smoke-test", help="Construct the full stack without model execution")
    subparsers.add_parser("export-artifacts", help="Export the current audit log and governance snapshot")
    serve = subparsers.add_parser("serve", help="Start the Azure AI Agent Server HTTP endpoint")
    serve.add_argument("--port", type=int, default=None)

    demo = subparsers.add_parser("demo", help="Run all educational acts")
    demo.add_argument("--prompt", default=ACT1_DEFAULT_PROMPT)

    args = parser.parse_args()
    command = args.command or "demo"

    app = LiveGovernedWorkspaceDemo()
    try:
        if command == "act1":
            await app.act1_live_workflow(args.prompt)
        elif command == "act2":
            await app.act2_control_plane()
        elif command == "act3":
            await app.act3_reliability()
        elif command == "act4":
            await app.act4_trust()
        elif command == "act5":
            await app.act5_mcp()
        elif command == "smoke-test":
            print(json.dumps(app.smoke_test(), indent=2, default=str))
        elif command == "export-artifacts":
            app.export_artifacts()
        elif command == "serve":
            await app.serve(args.port)
        else:
            await app.act1_live_workflow(args.prompt)
            await app.act2_control_plane()
            await app.act3_reliability()
            await app.act4_trust()
            await app.act5_mcp()
            app.export_artifacts()
    finally:
        await app.close()


if __name__ == "__main__":
    asyncio.run(main())