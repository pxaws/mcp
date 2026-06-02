# How to Run the DI MCP E2E Test

Runbook for an agent (pi or Claude Code) to trigger the Dynamic Instrumentation
MCP regression test in its own session. Validates the 11 DI tools end-to-end at
the MCP plumbing layer (request → boto3 → AWS API → parse → render).

## What this tests (and what it does NOT)

The `di-e2e-test` skill exercises three tool families — CRUD, status, snapshot —
against the live `applicationsignals` MCP server, using a **simulator** for
synthetic status/snapshot data. It does **not** test the Java/Python DI agent,
and needs no sample apps, traffic, or CloudWatch Agent.

## Prerequisites (verify before triggering)

```bash
# 1. MCP is live
claude mcp list | grep applicationsignals
#   Expect: applicationsignals - ✓ Connected

# 2. Skill is deployed
ls ~/.claude/skills/di-e2e-test/SKILL.md

# 3. Simulator lives inside THIS repo (its source of truth)
ls ~/Documents/mcp/src/cloudwatch-applicationsignals-mcp-server/sdk_simulator/sdk_simulator.py

# 4. AWS creds for the default profile are valid (test runs against real AWS, us-east-1)
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
AWS_PROFILE=default aws sts get-caller-identity --region us-east-1 --query Account --output text
#   If expired: ~/.toolbox/bin/ada credentials update --account <ACCT> --role Admin --profile default --once
```

If `applicationsignals` is missing or failed — STOP and
fix the MCP registration before running. See the setup guide Phase 3.3.

## Fail-fast simulator check (do this first)

The single most likely breakage: the simulator
imports the MCP's private-model client factory
(`awslabs.cloudwatch_applicationsignals_mcp_server.dynamic_instrumentation.aws_clients.get_application_signals_client`).
If that import is broken, the run dies deep at Test 19. Catch it in one second:

```bash
cd ~/Documents/mcp/src/cloudwatch-applicationsignals-mcp-server
AWS_REGION=us-east-1 uv run python sdk_simulator/sdk_simulator.py --help
#   Expect: usage block. ImportError/ModuleNotFoundError = STOP, fix import first.
```

(The skill's "Pre-flight 0a" runs exactly this — but checking here saves a wasted
launch.)

## Trigger the test in a fresh Claude Code session

The test is a 30-step skill that runs autonomously with one prompt. Launch
Claude Code in a tmux session so it runs without blocking, and watch via the
session transcript (Claude `-p` headless mode buffers output; interactive mode
shows live progress in the pane).

### Option A — interactive (recommended; live progress visible)

```bash
tmux kill-session -t di-e2e 2>/dev/null || true
tmux new-session -d -s di-e2e -x 200 -y 55
tmux send-keys -t di-e2e \
  'cd ~/di-mac-setup && AWS_PROFILE=default AWS_REGION=us-east-1 CLAUDE_CODE_USE_BEDROCK=1 claude --dangerously-skip-permissions' Enter
sleep 10   # wait for the TUI to come up
```

Then send the prompt (single line):

```bash
PROMPT='Run the di-e2e-test skill end-to-end against the applicationsignals MCP server (the awslabs CloudWatch Application Signals MCP server). Read ~/.claude/skills/di-e2e-test/SKILL.md and follow it EXACTLY, all 30 tests in order, including the Pre-flight 0a simulator import check. Inputs: Region=us-east-1, Test service=mcp-e2e-test-svc, Test environment=mcp-e2e-test-env. The simulator is at ~/Documents/mcp/src/cloudwatch-applicationsignals-mcp-server/sdk_simulator/sdk_simulator.py and is invoked by cd-ing into ~/Documents/mcp/src/cloudwatch-applicationsignals-mcp-server and running `AWS_REGION=us-east-1 uv run python sdk_simulator/sdk_simulator.py ...`. Use the DI MCP tools from the applicationsignals server for every tool call. Do NOT stand up the Java/Python sample apps; use the simulator for status/snapshot data. Respect the Bash timeout guidance (pass timeout 180000 for the 120s wait). At the very end, print the full E2E MCP Test Results summary table with PASS/FAIL per test plus the Passed X/30 line, quote actual tool output for any FAIL, and also write the final summary table to ~/di-mac-setup/di-e2e-result.md.'
tmux send-keys -t di-e2e "$PROMPT"; sleep 1; tmux send-keys -t di-e2e Enter
```

Attach to watch live (optional, e.g. in a Ghostty split):

```bash
tmux attach -t di-e2e
```

### Option B — headless (`-p`, no live output until done)

```bash
cd ~/di-mac-setup
AWS_PROFILE=default AWS_REGION=us-east-1 CLAUDE_CODE_USE_BEDROCK=1 \
  claude --dangerously-skip-permissions -p "$PROMPT" 2>&1 | tee /tmp/di-e2e-run.log
```

## Monitor progress (works for both options)

Claude Code writes a JSONL transcript that updates in real time — the most
reliable progress signal:

```bash
LATEST=$(ls -t ~/.claude/projects/-Users-pinxiang-di-mac-setup/*.jsonl | head -1)
tail -150 "$LATEST" | python3 -c "
import sys,json
for line in sys.stdin:
    try: o=json.loads(line)
    except: continue
    m=o.get('message',{})
    if m.get('role')=='assistant':
        for c in m.get('content',[]):
            if isinstance(c,dict) and c.get('type')=='text':
                for ln in c['text'].splitlines():
                    if any(k in ln for k in ['Test ','Phase','Pre-flight','PASS','FAIL']):
                        print(ln.strip()[:140])
"
pgrep -f 'claude --dangerously' >/dev/null && echo RUNNING || echo FINISHED
```

The run takes ~7 min (most of it a single ~120s CloudWatch Logs ingestion wait
before the snapshot queries in Phase 7).

## Verify the result

```bash
cat ~/di-mac-setup/di-e2e-result.md        # full 30-row PASS/FAIL table
grep 'Passed:' ~/di-mac-setup/di-e2e-result.md
```

Expected: `Passed: 30/30 | Failed: 0`.

Then confirm cleanup left nothing behind (the test creates/deletes throwaway BPs
under service `mcp-e2e-test-svc` / env `mcp-e2e-test-env`):

```bash
cd ~/Documents/mcp/src/cloudwatch-applicationsignals-mcp-server
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
AWS_PROFILE=default AWS_REGION=us-east-1 uv run python - <<'PY' 2>&1 | grep -v DEBUG
from awslabs.cloudwatch_applicationsignals_mcp_server.dynamic_instrumentation.aws_clients import get_application_signals_client
c = get_application_signals_client()
r = c.list_instrumentation_configurations(Service="mcp-e2e-test-svc", Environment="mcp-e2e-test-env", InstrumentationType="BREAKPOINT")
print("Leftover test-scope BPs:", len(r.get("InstrumentationConfigurations", r.get("Configurations", []))))
PY
```

Expected: `Leftover test-scope BPs: 0`.

## Key facts (so the next agent doesn't rediscover them)

- **MCP server name**: `applicationsignals`.
  Registered as: `uv tool run --from <this repo> awslabs.cloudwatch-applicationsignals-mcp-server`
  with env `MCP_DYNAMIC_INSTRUMENTATION_SNAPSHOT_LOG_GROUP=/telemend/telemetry`,
  `AWS_PROFILE=default`, `AWS_REGION=us-east-1`.
- **Simulator location**: `sdk_simulator/sdk_simulator.py` inside this repo (its source
  of truth). Run via `uv run` from the repo root so the package import resolves —
  do NOT add a `sys.path` hack and do NOT look for it under `~/di-mac-setup`
  (there is no copy there).
- **Skill source of truth**: `~/Documents/private-aws-otel-python-instrumentation-staging/plugins/adot-enablement/skills/di-e2e-test/`.
  Deployed copy (what Claude Code reads): `~/.claude/skills/di-e2e-test/`. Edit the
  SoT, then rsync to deployed (see the setup guide "Syncing" section).
- **Snapshots land in** CloudWatch Logs group `/telemend/telemetry`, stream `default`,
  region `us-east-1`.
- **Scope**: the test uses throwaway service `mcp-e2e-test-svc` / env `mcp-e2e-test-env`
  — safe, no real workload uses these.
