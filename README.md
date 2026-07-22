# AWS On-Call Triage AI Agent

An AI agent that replaces the first 20-30 minutes of manual 3AM on-call triage. Built with [Strands Agents SDK](https://github.com/strands-agents/sdk-python), it automatically investigates CloudWatch alarms, correlates errors with recent changes via CloudTrail, and produces structured incident reports in 45 seconds.

## How It Works

```
CloudWatch Alarm fires
       |
       v
SNS Topic (production) / CLI (demo)
       |
       v
Strands Agent with 6 investigation tools
       |
       v
Agent follows 6-step triage SOP
       |
       v
Safety hooks enforce production guardrails
       |
       v
Structured incident report --> Slack / Console
```

## Key Features

- **6 Investigation Tools**: CloudWatch Alarms, Metrics, Logs Insights, CloudTrail, ECS Deployments, Lambda versions
- **Natural Language SOP**: Agent follows a 6-step triage procedure written in plain markdown
- **Safety Hooks**: Deterministic guardrails the LLM cannot bypass (budget cap, fail-fast, production guard)
- **CloudTrail Correlation**: The killer feature. Answers "what changed?" which is the root cause 70% of the time
- **Production-Safe**: Hooks block any remediation on production services without human approval

## Quick Start

```bash
cd src/
pip install -r requirements.txt

# Investigate a specific alarm
python main.py --alarm "HighCPU-prod-api-server"

# Or pass a full alarm payload
python main.py --payload '{"alarm_name": "...", "state": "ALARM", ...}'

# Verbose mode (shows tool calls)
python main.py --alarm "Lambda-Errors-payment" --verbose
```

## Prerequisites

- Python 3.11+
- AWS account with Bedrock access (Amazon Nova Pro enabled)
- IAM role with read access to CloudWatch, CloudTrail, ECS, Lambda, Logs
- (Optional) Slack webhook URL for report delivery

## Project Structure

```
aws-oncall-triage-ai-agent/
├── src/
│   ├── main.py              # Entry point + agent setup (~20 lines of agent code)
│   ├── tools.py             # 6 @tool decorated investigation functions
│   ├── hooks.py             # Safety hooks (production guard, budget cap, fail-fast)
│   ├── sop.md               # Agent SOP (natural language triage procedure)
│   ├── config.py            # Configuration (region, thresholds, model)
│   └── requirements.txt     # Python dependencies
├── tests/
│   ├── test_hooks.py        # Unit tests for safety hooks (6 tests)
│   └── simulate_alarm.py    # End-to-end test with synthetic alarm scenarios
└── README.md
```

## The 6-Step Triage SOP

1. **ACKNOWLEDGE** - Parse alarm: what metric, what service, when
2. **ASSESS SEVERITY** - Check metric trend: spiking? sustained? recovering?
3. **FIND ERRORS** - Query CloudWatch Logs Insights (5 min window around alarm)
4. **FIND THE CHANGE** - Query CloudTrail (last 24hr changes to this service)
5. **CORRELATE & DIAGNOSE** - Connect alarm + errors + recent change = root cause
6. **REPORT** - Produce structured incident report

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

RECOMMENDED ACTION: ROLLBACK to v2.4.1 (confidence: 87%)
STATUS: AWAITING HUMAN APPROVAL (production service)
```

## Safety Hooks

The hooks enforce rules that system prompts cannot guarantee:

| Hook | What It Does |
|------|-------------|
| Budget Cap | Stops investigation after 15 tool calls, forces report |
| Fail-Fast | After 3 consecutive API failures, stops and reports honestly |
| Production Guard | Blocks any remediation action on prod services |
| Auth Sanitization | Strips IAM ARNs from error messages before model sees them |

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | us-east-1 | AWS region for all API calls |
| `BEDROCK_MODEL_ID` | amazon.nova-pro-v1:0 | Bedrock model to use |
| `SLACK_WEBHOOK_URL` | (empty) | Slack webhook for report delivery |

## Running Tests

```bash
cd tests/
python test_hooks.py          # Unit tests (no AWS needed)
python simulate_alarm.py --dry-run --scenario bad_deploy  # Preview scenario
```

## Strands SDK Features Demonstrated

1. **@tool decorator** - 6 custom tools for AWS investigation
2. **Hooks (HookProvider)** - Deterministic safety guardrails
3. **System prompt as SOP** - Natural language workflow in markdown
4. **BedrockModel** - Amazon Nova Pro via Amazon Bedrock

## License

MIT
