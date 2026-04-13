#!/usr/bin/env python3
"""
Governed Multi-Agent Workspace Assistant Demo

This demo showcases Agent Governance Toolkit integration with
Microsoft Agent Framework + Claude Agent SDK.

It demonstrates four key governance values:
1. System-enforced control plane
2. Runtime trust-based delegation
3. Reliability and anomaly containment
4. MCP-era safety scanning
"""

import sys
import os
from pathlib import Path
from colorama import init, Fore, Style
import json

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from governance import (
    PolicyEngine,
    PolicyDecision,
    TrustSystem,
    TrustLevel,
    ReliabilityMonitor,
    AnomalyAction,
    MCPScanner
)

# Initialize colorama for cross-platform colored output
init()


class DemoRunner:
    """Orchestrates the 5-act governance demo"""

    def __init__(self):
        self.policy_engine = PolicyEngine(policy_dir="policies")
        self.trust_system = TrustSystem(policy_dir="policies")
        self.reliability_monitor = ReliabilityMonitor(policy_dir="policies")
        self.mcp_scanner = MCPScanner()

        self.current_agent = "workspace-governor"

    def print_header(self, text: str):
        """Print a section header"""
        print(f"\n{Fore.CYAN}{'═' * 80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{text:^80}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'═' * 80}{Style.RESET_ALL}\n")

    def print_subheader(self, text: str):
        """Print a subsection header"""
        print(f"\n{Fore.YELLOW}{'─' * 80}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}{text}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}{'─' * 80}{Style.RESET_ALL}")

    def print_success(self, text: str):
        """Print success message"""
        print(f"{Fore.GREEN}✅ {text}{Style.RESET_ALL}")

    def print_error(self, text: str):
        """Print error/denial message"""
        print(f"{Fore.RED}❌ {text}{Style.RESET_ALL}")

    def print_info(self, text: str):
        """Print info message"""
        print(f"{Fore.BLUE}ℹ️  {text}{Style.RESET_ALL}")

    def print_warning(self, text: str):
        """Print warning message"""
        print(f"{Fore.YELLOW}⚠️  {text}{Style.RESET_ALL}")

    def simulate_agent_action(self, agent_name: str, action: str, details: str):
        """Simulate an agent attempting an action"""
        print(f"\n{Fore.MAGENTA}[{agent_name}]{Style.RESET_ALL} {action}")
        print(f"  詳細: {details}")

    def act1_normal_flow(self):
        """Act 1: Normal helpful operation flow"""
        self.print_header("Act 1: 正常な動作 (Normal Helpful Flow)")

        self.print_info("目的: エージェントが正常に安全な操作を実行できることを示す")
        self.print_info("期待される結果: チケットの読み取りと分析が成功する")

        print("\n【シナリオ】ユーザーがワークスペースの調査を依頼")

        # Step 1: Main agent delegates to triage subagent
        self.print_subheader("Step 1: Triage Subagent にタスクを委任")

        self.simulate_agent_action(
            "workspace-governor",
            "triage-subagent にチケット分析を委任",
            "TICKET-001 の内容を読み取って分析してください"
        )

        # Check tool usage
        tool_result = self.policy_engine.check_tool_usage("triage-subagent", "read_file")
        if tool_result.decision == PolicyDecision.ALLOW:
            self.print_success(f"Tool usage allowed: {tool_result.message}")
        else:
            self.print_error(f"Tool usage denied: {tool_result.message}")

        # Step 2: Read ticket file
        self.print_subheader("Step 2: チケットファイルの読み取り")

        ticket_path = "demo_workspace/tickets/TICKET-001.md"
        self.simulate_agent_action(
            "triage-subagent",
            f"ファイル '{ticket_path}' を読み取り",
            "ワークスペース設定確認の内容を取得"
        )

        file_result = self.policy_engine.check_file_access(ticket_path)
        if file_result.decision == PolicyDecision.ALLOW:
            self.print_success(f"File access allowed: {file_result.message}")
            # Actually read and display the file
            try:
                with open(ticket_path) as f:
                    content = f.read()
                print(f"\n{Fore.WHITE}--- ファイル内容 (抜粋) ---{Style.RESET_ALL}")
                print(content[:300] + "...\n")
            except Exception as e:
                self.print_warning(f"Could not read file: {e}")
        else:
            self.print_error(f"File access denied: {file_result.message}")

        # Step 3: Read runbook
        self.print_subheader("Step 3: 関連するランブックの確認")

        runbook_path = "demo_workspace/runbooks/workspace-setup.md"
        self.simulate_agent_action(
            "triage-subagent",
            f"ランブック '{runbook_path}' を読み取り",
            "セットアップ手順を確認"
        )

        runbook_result = self.policy_engine.check_file_access(runbook_path)
        if runbook_result.decision == PolicyDecision.ALLOW:
            self.print_success(f"Runbook access allowed: {runbook_result.message}")
        else:
            self.print_error(f"Runbook access denied: {runbook_result.message}")

        # Summary
        print("\n" + "=" * 80)
        self.print_success("Act 1 完了: 正常なフローでは全ての操作が許可されました")
        print(f"\n{Fore.CYAN}【学び】{Style.RESET_ALL}")
        print("安全なファイルへのアクセスと読み取り専用操作は、")
        print("ガバナンスポリシーによって適切に許可されます。")

    def act2_unsafe_blocked(self):
        """Act 2: Unsafe request is blocked by policy"""
        self.print_header("Act 2: 危険な要求のブロック (Unsafe Request Blocked)")

        self.print_info("目的: システム強制の制御プレーンが危険な操作を実行前にブロックすることを示す")
        self.print_info("期待される結果: 機密ファイルへのアクセスとprivileged commandが拒否される")

        # Scenario 1: Try to access secrets
        self.print_subheader("Scenario 2.1: 機密ファイルへのアクセス試行")

        secret_path = "demo_workspace/secrets/.env"
        self.simulate_agent_action(
            "executor-subagent",
            f"ファイル '{secret_path}' を読み取り試行",
            "環境変数の確認(実際には認証情報が含まれる)"
        )

        secret_result = self.policy_engine.check_file_access(secret_path)
        if secret_result.decision == PolicyDecision.DENY:
            self.print_error(f"Access DENIED: {secret_result.message}")
            print(f"  ルール: {secret_result.rule_name}")
            print(f"  理由: {secret_result.details.get('description', '')}")

            # Record denial for anomaly detection
            anomaly = self.reliability_monitor.record_denial(
                "executor-subagent",
                secret_result.message
            )
        else:
            self.print_warning("Expected denial but got allowed - policy issue!")

        # Scenario 2: Try to run privileged command
        self.print_subheader("Scenario 2.2: 特権コマンドの実行試行")

        dangerous_cmd = "sudo cat /etc/passwd"
        self.simulate_agent_action(
            "executor-subagent",
            f"コマンド '{dangerous_cmd}' の実行試行",
            "システムユーザー情報の取得"
        )

        cmd_result = self.policy_engine.check_command_execution(dangerous_cmd)
        if cmd_result.decision == PolicyDecision.DENY:
            self.print_error(f"Command DENIED: {cmd_result.message}")
            print(f"  ルール: {cmd_result.rule_name}")
            print(f"  理由: {cmd_result.details.get('description', '')}")

            # Record denial
            anomaly = self.reliability_monitor.record_denial(
                "executor-subagent",
                cmd_result.message
            )
        else:
            self.print_warning("Expected denial but got allowed - policy issue!")

        # Scenario 3: Try destructive command
        self.print_subheader("Scenario 2.3: 破壊的コマンドの実行試行")

        destructive_cmd = "rm -rf /tmp/*"
        self.simulate_agent_action(
            "executor-subagent",
            f"コマンド '{destructive_cmd}' の実行試行",
            "一時ファイルのクリーンアップ(危険)"
        )

        dest_result = self.policy_engine.check_command_execution(destructive_cmd)
        if dest_result.decision == PolicyDecision.DENY:
            self.print_error(f"Command DENIED: {dest_result.message}")
            print(f"  ルール: {dest_result.rule_name}")

            # Record denial
            anomaly = self.reliability_monitor.record_denial(
                "executor-subagent",
                dest_result.message
            )
        else:
            self.print_warning("Expected denial but got allowed - policy issue!")

        # Summary
        print("\n" + "=" * 80)
        self.print_success("Act 2 完了: 危険な操作は全て実行前にブロックされました")
        print(f"\n{Fore.CYAN}【学び】{Style.RESET_ALL}")
        print("ガバナンスレイヤーは、エージェントの意図に関わらず、")
        print("システムレベルで危険な操作をブロックします。")
        print("LLMの判断に依存せず、ポリシーベースで制御します。")

    def act3_anomaly_containment(self):
        """Act 3: Suspicious repeated behavior triggers containment"""
        self.print_header("Act 3: 疑わしい反復動作の封じ込め (Suspicious Behavior Contained)")

        self.print_info("目的: 異常検知とサーキットブレーカーによる信頼性制御を示す")
        self.print_info("期待される結果: 繰り返しの拒否により隔離(quarantine)が発動")

        # Simulate repeated attempts to access secrets
        self.print_subheader("Scenario 3.1: 繰り返しの機密アクセス試行")

        for i in range(1, 4):
            self.simulate_agent_action(
                "executor-subagent",
                f"試行 #{i}: 機密ファイルへのアクセス",
                f"demo_workspace/secrets/.env (試行 {i}/3)"
            )

            result = self.policy_engine.check_file_access("demo_workspace/secrets/.env")
            self.print_error(f"試行 #{i} - DENIED: {result.message}")

            anomaly = self.reliability_monitor.record_denial(
                "executor-subagent",
                result.message
            )

            if anomaly.detected:
                self.print_warning(f"\n🚨 異常検知! {anomaly.anomaly_type}")
                print(f"  アクション: {anomaly.action.value}")
                print(f"  メッセージ: {anomaly.message}")
                print(f"  閾値: {anomaly.threshold}, 実際: {anomaly.actual_count}")
                break

        # Check if agent is quarantined
        self.print_subheader("Scenario 3.2: エージェント状態の確認")

        is_quarantined = self.reliability_monitor.is_quarantined("executor-subagent")
        status = self.reliability_monitor.get_agent_status("executor-subagent")

        print(f"\nエージェント状態:")
        print(f"  隔離状態: {is_quarantined}")
        print(f"  サーキットブレーカー: {status['circuit_state']}")
        print(f"  直近の拒否回数(60秒): {status['recent_denials_60s']}")

        if is_quarantined:
            self.print_error("executor-subagent は隔離されました!")
            self.print_info("隔離中は全ての操作が拒否されます")

        # Summary
        print("\n" + "=" * 80)
        self.print_success("Act 3 完了: 疑わしい動作が検知され封じ込められました")
        print(f"\n{Fore.CYAN}【学び】{Style.RESET_ALL}")
        print("繰り返しの拒否パターンは、ローグエージェントや")
        print("攻撃の兆候として検知され、自動的に隔離されます。")
        print("これにより被害の拡大を防ぎます。")

    def act4_trust_check(self):
        """Act 4: Trust-based peer agent delegation"""
        self.print_header("Act 4: ピアエージェント信頼チェック (Peer Trust Check)")

        self.print_info("目的: 信頼ベースのエージェント間アクセス制御を示す")
        self.print_info("期待される結果: 信頼されていないピアは拒否、信頼されたピアは許可")

        # Scenario 1: Try to delegate to untrusted peer
        self.print_subheader("Scenario 4.1: 信頼されていないピアへの委任試行")

        self.simulate_agent_action(
            "workspace-governor",
            "untrusted-peer-helper へタスクを委任",
            "診断タスクの実行を依頼"
        )

        trust_result = self.trust_system.check_agent_trust(
            "untrusted-peer-helper",
            ["read_workspace"]
        )

        if not trust_result.allowed:
            self.print_error("Delegation DENIED")
            print(f"  エージェント: {trust_result.agent_name}")
            print(f"  信頼レベル: {trust_result.trust_level.value}")
            print(f"  信頼スコア: {trust_result.trust_score}")
            print(f"  理由: {trust_result.reason}")
        else:
            self.print_warning("Expected denial but got allowed!")

        # Show agent info
        untrusted_info = self.trust_system.get_agent_info("untrusted-peer-helper")
        print(f"\n詳細情報:")
        print(f"  ID検証済み: {untrusted_info.get('identity_verified', False)}")
        print(f"  説明: {untrusted_info.get('description', '')}")

        # Scenario 2: Delegate to trusted peer
        self.print_subheader("Scenario 4.2: 信頼されたピアへの委任試行")

        self.simulate_agent_action(
            "workspace-governor",
            "trusted-peer-helper へタスクを委任",
            "診断タスクの実行を依頼"
        )

        trust_result2 = self.trust_system.check_agent_trust(
            "trusted-peer-helper",
            ["read_workspace"]
        )

        if trust_result2.allowed:
            self.print_success("Delegation ALLOWED")
            print(f"  エージェント: {trust_result2.agent_name}")
            print(f"  信頼レベル: {trust_result2.trust_level.value}")
            print(f"  信頼スコア: {trust_result2.trust_score}")
            print(f"  理由: {trust_result2.reason}")
        else:
            self.print_warning("Expected allow but got denied!")

        # Show trusted agents list
        self.print_subheader("Scenario 4.3: 信頼されたエージェントのリスト")

        high_trust = self.trust_system.list_trusted_agents(TrustLevel.HIGH)
        print(f"\n高信頼エージェント ({len(high_trust)}):")
        for agent in high_trust:
            info = self.trust_system.get_agent_info(agent)
            print(f"  • {agent} (スコア: {info.get('score', 0)})")

        # Summary
        print("\n" + "=" * 80)
        self.print_success("Act 4 完了: 信頼ベースのアクセス制御が機能しました")
        print(f"\n{Fore.CYAN}【学び】{Style.RESET_ALL}")
        print("全てのピアエージェントが同等に信頼されるわけではありません。")
        print("信頼レベルに基づいて、委任の可否が明示的に判定されます。")
        print("これにより、不正なエージェントからのアクセスを防ぎます。")

    def act5_mcp_scan(self):
        """Act 5: MCP configuration security scanning"""
        self.print_header("Act 5: MCPスキャン (MCP Safety Scan)")

        self.print_info("目的: MCP時代のセキュリティ - ツール定義のスキャンを示す")
        self.print_info("期待される結果: 安全な設定は合格、疑わしい設定は警告")

        # Scan safe config
        self.print_subheader("Scenario 5.1: 安全なMCP設定のスキャン")

        print(f"\nスキャン対象: mcp/safe_config.json")
        safe_result = self.mcp_scanner.scan_config("mcp/safe_config.json")

        if safe_result.passed:
            self.print_success(safe_result.summary)
        else:
            self.print_error(safe_result.summary)

        print(f"  リスクスコア: {safe_result.risk_score}/100")
        print(f"  検出された問題: {len(safe_result.findings)}")

        if safe_result.findings:
            print(f"\n  問題の詳細:")
            for finding in safe_result.findings[:3]:  # Show first 3
                print(f"    • [{finding.severity.value}] {finding.description}")

        # Scan suspicious config
        self.print_subheader("Scenario 5.2: 疑わしいMCP設定のスキャン")

        print(f"\nスキャン対象: mcp/suspicious_config.json")
        suspicious_result = self.mcp_scanner.scan_config("mcp/suspicious_config.json")

        if not suspicious_result.passed:
            self.print_error(suspicious_result.summary)
        else:
            self.print_warning("Expected failure but got pass!")

        print(f"  リスクスコア: {suspicious_result.risk_score}/100")
        print(f"  検出された問題: {len(suspicious_result.findings)}")

        if suspicious_result.findings:
            print(f"\n  深刻な問題:")
            high_severity = [f for f in suspicious_result.findings
                            if f.severity.value in ['HIGH', 'CRITICAL']]
            for finding in high_severity[:5]:  # Show first 5 high/critical
                print(f"    • [{finding.severity.value}] {finding.issue_type}")
                print(f"      {finding.description}")
                print(f"      推奨: {finding.recommendation}\n")

        # Generate and save full report
        self.print_subheader("Scenario 5.3: 完全なスキャンレポートの生成")

        all_results = self.mcp_scanner.scan_directory("mcp")
        report = self.mcp_scanner.generate_report(all_results)

        report_path = "artifacts/mcp_scan_report.txt"
        os.makedirs("artifacts", exist_ok=True)
        with open(report_path, 'w') as f:
            f.write(report)

        self.print_success(f"完全なレポートを保存: {report_path}")

        # Summary
        print("\n" + "=" * 80)
        self.print_success("Act 5 完了: MCP設定のセキュリティスキャンが完了しました")
        print(f"\n{Fore.CYAN}【学び】{Style.RESET_ALL}")
        print("MCPツール定義には、隠れた指示や悪意ある動作が含まれる可能性があります。")
        print("エージェントに使わせる前に、ガバナンスレイヤーでスキャンすることが重要です。")
        print("これにより、サプライチェーン攻撃やツール汚染を防ぎます。")

    def save_audit_logs(self):
        """Save audit logs for review"""
        os.makedirs("artifacts", exist_ok=True)

        # Save policy audit log
        self.policy_engine.save_audit_log("artifacts/policy_audit.json")
        self.print_success("Policy audit log saved: artifacts/policy_audit.json")

        # Save agent status
        agents = ["workspace-governor", "triage-subagent", "executor-subagent"]
        status_report = {}
        for agent in agents:
            status_report[agent] = self.reliability_monitor.get_agent_status(agent)

        with open("artifacts/agent_status.json", 'w') as f:
            json.dump(status_report, f, indent=2)
        self.print_success("Agent status report saved: artifacts/agent_status.json")

    def run_full_demo(self):
        """Run the complete 5-act demo"""
        self.print_header("🎭 Governed Multi-Agent Workspace Assistant Demo 🎭")

        print(f"{Fore.WHITE}このデモは、Agent Governance Toolkit (AGT) を使った{Style.RESET_ALL}")
        print(f"{Fore.WHITE}AIエージェントのガバナンスを実演します。{Style.RESET_ALL}\n")

        print(f"【4つのガバナンス価値】")
        print(f"  1. システム強制の制御プレーン (System-enforced control plane)")
        print(f"  2. 実行時信頼制御 (Runtime trust)")
        print(f"  3. 信頼性と封じ込め (Reliability containment)")
        print(f"  4. MCPセキュリティ (MCP safety)")

        input(f"\n{Fore.GREEN}Press Enter to start the demo...{Style.RESET_ALL}")

        # Run all acts
        self.act1_normal_flow()
        input(f"\n{Fore.GREEN}Press Enter to continue to Act 2...{Style.RESET_ALL}")

        self.act2_unsafe_blocked()
        input(f"\n{Fore.GREEN}Press Enter to continue to Act 3...{Style.RESET_ALL}")

        self.act3_anomaly_containment()
        input(f"\n{Fore.GREEN}Press Enter to continue to Act 4...{Style.RESET_ALL}")

        self.act4_trust_check()
        input(f"\n{Fore.GREEN}Press Enter to continue to Act 5...{Style.RESET_ALL}")

        self.act5_mcp_scan()

        # Save logs
        self.print_header("📊 Saving Audit Logs")
        self.save_audit_logs()

        # Final summary
        self.print_header("🎉 Demo Complete! デモ完了!")

        print(f"\n{Fore.WHITE}【まとめ】{Style.RESET_ALL}")
        print(f"このデモで示したこと:")
        print(f"  ✅ 危険な操作がシステムレベルでブロックされた")
        print(f"  ✅ 信頼レベルに基づいてエージェント委任が制御された")
        print(f"  ✅ 異常な動作が検知され封じ込められた")
        print(f"  ✅ MCPツール定義の脆弱性がスキャンで発見された")

        print(f"\n{Fore.CYAN}生成されたアーティファクト:{Style.RESET_ALL}")
        print(f"  • artifacts/policy_audit.json - ポリシー判定の監査ログ")
        print(f"  • artifacts/agent_status.json - エージェント状態レポート")
        print(f"  • artifacts/mcp_scan_report.txt - MCPセキュリティスキャンレポート")

        print(f"\n{Fore.YELLOW}次のステップ:{Style.RESET_ALL}")
        print(f"  1. artifacts/ フォルダ内の監査ログを確認")
        print(f"  2. policies/ フォルダのポリシーをカスタマイズ")
        print(f"  3. 独自のサブエージェントやスキルを追加")
        print(f"  4. 本番環境向けにMicrosoft Agent Frameworkと統合")


def main():
    """Main entry point"""
    demo = DemoRunner()

    if len(sys.argv) > 1:
        act = sys.argv[1]
        if act == "act1":
            demo.act1_normal_flow()
        elif act == "act2":
            demo.act2_unsafe_blocked()
        elif act == "act3":
            demo.act3_anomaly_containment()
        elif act == "act4":
            demo.act4_trust_check()
        elif act == "act5":
            demo.act5_mcp_scan()
        else:
            print(f"Unknown act: {act}")
            print("Usage: python demo.py [act1|act2|act3|act4|act5]")
    else:
        demo.run_full_demo()


if __name__ == "__main__":
    main()
