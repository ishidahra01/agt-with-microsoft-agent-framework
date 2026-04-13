.PHONY: demo install clean test act1 act2 act3 act4 act5 help

help:  ## Show this help message
	@echo "Governed Multi-Agent Workspace Assistant Demo"
	@echo ""
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install Python dependencies
	pip install -r requirements.txt

demo:  ## Run the full interactive 5-act demo
	python app/demo.py

act1:  ## Run Act 1: Normal helpful flow
	python app/demo.py act1

act2:  ## Run Act 2: Unsafe request blocked
	python app/demo.py act2

act3:  ## Run Act 3: Anomaly containment
	python app/demo.py act3

act4:  ## Run Act 4: Trust check
	python app/demo.py act4

act5:  ## Run Act 5: MCP scan
	python app/demo.py act5

test:  ## Run all individual acts in sequence (non-interactive)
	@echo "Running all acts..."
	@echo ""
	@echo "=== Act 1: Normal Flow ==="
	@python app/demo.py act1
	@echo ""
	@echo "=== Act 2: Unsafe Blocked ==="
	@python app/demo.py act2
	@echo ""
	@echo "=== Act 3: Anomaly Containment ==="
	@python app/demo.py act3
	@echo ""
	@echo "=== Act 4: Trust Check ==="
	@python app/demo.py act4
	@echo ""
	@echo "=== Act 5: MCP Scan ==="
	@python app/demo.py act5
	@echo ""
	@echo "✅ All acts completed!"

clean:  ## Remove generated artifacts
	rm -rf artifacts/*.json artifacts/*.txt
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

artifacts:  ## Show generated artifacts
	@echo "Generated artifacts:"
	@ls -lh artifacts/ 2>/dev/null || echo "No artifacts generated yet. Run 'make demo' first."

view-audit:  ## View policy audit log
	@cat artifacts/policy_audit.json 2>/dev/null || echo "No audit log found. Run the demo first."

view-status:  ## View agent status report
	@cat artifacts/agent_status.json 2>/dev/null || echo "No status report found. Run the demo first."

view-scan:  ## View MCP scan report
	@cat artifacts/mcp_scan_report.txt 2>/dev/null || echo "No scan report found. Run Act 5 first."

check:  ## Verify repository structure
	@echo "Checking repository structure..."
	@test -d app && echo "✅ app/" || echo "❌ app/ missing"
	@test -d app/.claude && echo "✅ app/.claude/" || echo "❌ app/.claude/ missing"
	@test -d policies && echo "✅ policies/" || echo "❌ policies/ missing"
	@test -d demo_workspace && echo "✅ demo_workspace/" || echo "❌ demo_workspace/ missing"
	@test -d mcp && echo "✅ mcp/" || echo "❌ mcp/ missing"
	@test -f app/demo.py && echo "✅ app/demo.py" || echo "❌ app/demo.py missing"
	@test -f requirements.txt && echo "✅ requirements.txt" || echo "❌ requirements.txt missing"
	@echo ""
	@echo "Checking Python syntax..."
	@python -m py_compile app/demo.py && echo "✅ demo.py syntax OK" || echo "❌ demo.py syntax error"
	@python -m py_compile app/governance/*.py && echo "✅ governance modules syntax OK" || echo "❌ governance modules syntax error"
