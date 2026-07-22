<p align="center">
  <h1 align="center">AWS On-Call Triage AI Agent</h1>
  <p align="center">
    From alert to root cause in 45 seconds. Not 20 minutes.
  </p>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#how-it-works">How It Works</a> •
  <a href="#safety-hooks">Safety Hooks</a> •
  <a href="#example-output">Example Output</a> •
  <a href="#deploy-to-lambda">Deploy</a>
</p>

---

## The Problem

You get paged at 3AM. You fumble for your laptop. Then you spend the next 20-30 minutes doing the exact same thing every time:

1. Check what alarm fired
2. Look at the metric trend
3. Search logs for errors
4. Check CloudTrail for recent changes
5. Connect the dots
6. Write up what you found

This agent does steps 1-6 in 45 seconds while you're still finding your glasses.

## What This Is

An AI agent built with [Strands Agents SDK](https://github.com/strands-agents/sdk-python) that automatically investigates CloudWatch alarms and produces structured incident reports. It uses 6 custom tools to query AWS services, follows a natural language SOP, and has safety hooks that prevent it from doing anything dangerous.

**It investigates. It does not fix.** Production remediation requires human approval.

---

## How It Works

```
CloudWatch Alarm fires
       │
       ▼
┌─────────────────────────┐
│  SNS → Lambda (prod)    │
│  or CLI (demo)          │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  Strands Agent          │
│  ┌───────────────────┐  │
│  │ 6 Investigation   │  │
│  │ Tools (@tool)     │  │
│  └───────────────────┘  │
│  ┌───────────────────┐  │
│  │ 6-Step Triage     │  │
│  │ SOP (markdown)    │  │
│  └───────────────────┘  │
│  ┌───────────────────┐  │
│  │ Safety Hooks      │  │
│  │ (deterministic)   │  │
│  └───────────────────┘  │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  Structured Incident    │
│  Report → Slack/Console │
└─────────────────────────┘
```

### The 6-Step Triage SOP

The agent follows this procedure in order, every time:

| Step | Action | Tool Used |
|------|--------|-----------|
| 1. ACKNOWLEDGE | Parse alarm: what metric, what service, when | `get_alarm_details` |
| 2. ASSESS SEVERITY | Is it spiking? Stable? Recovering? | `query_metric_trend` |
| 3. FIND ERRORS | Search logs around the alarm time | `search_logs` |
| 4. FIND THE CHANGE | What changed recently? (the killer step) | `check_recent_changes` + `get_deployment_history` |
| 5. CORRELATE | Connect alarm + errors + change = root cause | Agent reasoning |
| 6. REPORT | Produce structured report | `post_incident_report` |

Step 4 is where the magic happens. 70% of incidents are caused by recent changes. CloudTrail tells you exactly who changed what and when.

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/simplynadaf/aws-oncall-triage-ai-agent.git
cd aws-oncall-triage-ai-agent/src
pip install -r requirements.txt

# Run against an alarm
python main.py --alarm "HighCPU-prod-api-server"

# Or pass a full SNS payload
python main.py --payload '{"alarm_name": "Lambda-Errors-payment", "state": "ALARM"}'

# Verbose mode (see every tool call)
python main.py --alarm "HighCPU-prod-api-server" --verbose
```

### Prerequisites

- Python 3.11+
- AWS account with [Amazon Bedrock](https://aws.amazon.com/bedrock/) access (Amazon Nova Pro enabled)
- IAM permissions (read-only):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "cloudwatch:DescribeAlarms",
      "cloudwatch:GetMetricData",
      "logs:StartQuery",
      "logs:GetQueryResults",
      "cloudtrail:LookupEvents",
      "ecs:DescribeServices",
      "lambda:GetFunction",
      "lambda:ListVersionsByFunction",
      "bedrock:InvokeModel"
    ],
    "Resource": "*"
  }]
}
```

---

## Example Output

```
INCIDENT TRIAGE REPORT
========================
Alarm: HighCPU-prod-api-server
Fired: 2026-07-22 03:14 UTC
Current Value: 94% CPU (threshold: 80%)

TREND: Sustained spike since 03:10, NOT recovering

ERRORS FOUND:
- 847 "Connection pool exhausted" errors (03:10-03:14)
- Stack trace points to /api/v2/search handler

RECENT CHANGE FOUND:
- 03:08 UTC: ECS deployment by ci-pipeline-role
- Image tag: v2.4.1 -> v2.5.0 (2 min before spike)

PROBABLE ROOT CAUSE:
Deployment v2.5.0 introduced connection leak in search handler

RECOMMENDED ACTION: ROLLBACK to v2.4.1
CONFIDENCE: 87%
STATUS: AWAITING HUMAN APPROVAL (production service)
```

Total time: **4.6 seconds** (including Bedrock model latency).

---

## Safety Hooks

System prompts are suggestions. Hooks are laws.

The agent has three deterministic safety hooks that the LLM cannot override, no matter what it reasons:

| Hook | What It Enforces | Why It Matters |
|------|-----------------|----------------|
| **Budget Cap** | Max 15 tool calls per invocation | Prevents infinite investigation loops |
| **Fail-Fast** | After 3 consecutive API failures, stop | Don't waste time when permissions are broken |
| **Production Guard** | Block ALL remediation on `prod-*` services | No cowboy automation at 3AM |
| **Auth Sanitization** | Strip IAM ARNs from error messages | Don't leak infrastructure details to the model |

```python
# The hook fires BEFORE the tool executes. The model never gets a choice.
if tool_name == "rollback_deployment" and "prod-" in service_name:
    event.cancel_tool = (
        "BLOCKED: Remediation on production requires human approval. "
        "Mark it as AWAITING HUMAN APPROVAL in your report."
    )
```

---

## Project Structure

```
aws-oncall-triage-ai-agent/
├── src/
│   ├── main.py              # Agent setup (~20 lines of actual agent code)
│   ├── tools.py             # 6 @tool decorated AWS investigation functions
│   ├── hooks.py             # Safety hooks (HookProvider pattern)
│   ├── sop.md               # Natural language triage procedure
│   ├── config.py            # Thresholds, model ID, region
│   └── requirements.txt     # strands-agents, boto3, requests
├── tests/
│   ├── test_hooks.py        # 6 unit tests for safety hooks
│   └── simulate_alarm.py    # Synthetic alarm scenarios for E2E testing
└── README.md
```

---

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `AWS_REGION` | `us-east-1` | Region for all AWS API calls |
| `BEDROCK_MODEL_ID` | `amazon.nova-pro-v1:0` | Which Bedrock model to use |
| `SLACK_WEBHOOK_URL` | *(empty)* | Slack webhook for report delivery |

Edit `src/config.py` for safety thresholds:

```python
MAX_TOOL_CALLS_PER_INVOCATION = 15   # Budget cap
MAX_CONSECUTIVE_FAILURES = 3          # Fail-fast threshold
PRODUCTION_SERVICES = ["prod-", "production-", "prd-"]  # Guard prefixes
```

---

## Deploy to Lambda

For always-on triage, deploy as a Lambda function triggered by SNS:

```
CloudWatch Alarm → SNS Topic → Lambda (this agent) → Slack
```

The agent code is already structured for this. The `run_triage(payload=event)` function accepts SNS alarm payloads directly.

---

## Running Tests

```bash
# Unit tests (no AWS credentials needed)
cd tests/
python test_hooks.py

# Preview alarm scenarios
python simulate_alarm.py --scenario bad_deploy --dry-run
python simulate_alarm.py --scenario connection_leak --dry-run
```

All 6 hook tests pass:
```
✓ test_budget_cap passed
✓ test_fail_fast passed
✓ test_fail_fast_resets_on_success passed
✓ test_production_remediation_blocked passed
✓ test_non_production_remediation_allowed passed
✓ test_auth_error_sanitization passed
```

---

## Strands SDK Features Used

| Feature | How It's Used |
|---------|--------------|
| `@tool` decorator | 6 custom tools wrapping AWS SDK calls |
| `HookProvider` + `HookRegistry` | Deterministic safety guardrails |
| `BedrockModel` | Amazon Nova Pro via Bedrock |
| System prompt as SOP | Markdown file loaded as agent instructions |
| `BeforeToolCallEvent` | Block calls before they execute |
| `AfterToolCallEvent` | Sanitize results before model sees them |

---

## What's Next

- [ ] PagerDuty integration (auto-acknowledge + enrich)
- [ ] Slack interactive buttons ("Approve Rollback" / "Escalate")
- [ ] Multi-service correlation (trace across microservices)
- [ ] Historical pattern matching ("this looks like the outage from March 12")
- [ ] AgentCore Runtime deployment for managed hosting

---

## Built With

- [Strands Agents SDK](https://github.com/strands-agents/sdk-python) - Agent framework
- [Amazon Bedrock](https://aws.amazon.com/bedrock/) - LLM inference (Nova Pro)
- [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) - AWS SDK for Python
- [CloudWatch](https://aws.amazon.com/cloudwatch/) - Metrics, Logs, Alarms
- [CloudTrail](https://aws.amazon.com/cloudtrail/) - API audit trail (the secret weapon)

---

## License

MIT

---

*Built by [Sarvar Nadaf](https://sarvarnadaf.com) - Cloud Architect | AWS Community Builder | 7x AWS Certified*
