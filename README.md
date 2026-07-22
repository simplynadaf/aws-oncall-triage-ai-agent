<p align="center">
  <img src="https://img.shields.io/badge/AWS-Bedrock-orange?style=for-the-badge&logo=amazon-aws" alt="AWS Bedrock">
  <img src="https://img.shields.io/badge/Strands-Agents_SDK-blue?style=for-the-badge" alt="Strands Agents SDK">
  <img src="https://img.shields.io/badge/Python-3.11+-green?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="MIT License">
</p>

<h1 align="center">🚨 AWS On-Call Triage AI Agent</h1>

<p align="center">
  <strong>From alert to root cause in 45 seconds. Not 20 minutes.</strong>
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-how-it-works">How It Works</a> •
  <a href="#-safety-hooks">Safety Hooks</a> •
  <a href="#-example-output">Example Output</a> •
  <a href="#-deploy-to-lambda">Deploy</a>
</p>

---

## 😴 The Problem

You get paged at 3AM. You fumble for your laptop. Then you spend the next 20-30 minutes doing the exact same thing every single time:

1. Check what alarm fired
2. Look at the metric trend
3. Search logs for errors
4. Check CloudTrail for recent changes
5. Connect the dots
6. Write up what you found

**This agent does steps 1-6 in 45 seconds** while you're still finding your glasses.

---

## 🧠 What This Is

An AI agent built with [Strands Agents SDK](https://github.com/strands-agents/sdk-python) that automatically investigates CloudWatch alarms and produces structured incident reports.

- 🔍 **6 custom tools** to query AWS services
- 📋 **Natural language SOP** the agent follows step-by-step
- 🛡️ **Safety hooks** that prevent it from doing anything dangerous
- ⚡ **4.6 seconds** average triage time (including model latency)

> **It investigates. It does not fix.** Production remediation requires human approval.

---

## 🏗️ How It Works

```
CloudWatch Alarm fires
       │
       ▼
┌─────────────────────────┐
│  📡 SNS → Lambda (prod) │
│  or CLI (demo)          │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  🤖 Strands Agent       │
│  ┌───────────────────┐  │
│  │ 🔧 6 Tools        │  │
│  │ 📋 6-Step SOP     │  │
│  │ 🛡️ Safety Hooks   │  │
│  └───────────────────┘  │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  📊 Incident Report     │
│  → Slack / Console      │
└─────────────────────────┘
```

### 📋 The 6-Step Triage SOP

| Step | Action | Tool |
|------|--------|------|
| 1️⃣ ACKNOWLEDGE | Parse alarm: what metric, what service, when | `get_alarm_details` |
| 2️⃣ ASSESS | Is it spiking? Stable? Recovering? | `query_metric_trend` |
| 3️⃣ FIND ERRORS | Search logs around the alarm time | `search_logs` |
| 4️⃣ FIND THE CHANGE | What changed recently? **(the killer step)** | `check_recent_changes` |
| 5️⃣ CORRELATE | Alarm + errors + change = root cause | Agent reasoning |
| 6️⃣ REPORT | Structured report with confidence level | `post_incident_report` |

> 💡 **Step 4 is where the magic happens.** 70% of incidents are caused by recent changes. CloudTrail tells you exactly who changed what and when.

---

## 🚀 Quick Start

```bash
# Clone and install
git clone https://github.com/simplynadaf/aws-oncall-triage-ai-agent.git
cd aws-oncall-triage-ai-agent/src
pip install -r requirements.txt

# 🔥 Run against an alarm
python main.py --alarm "HighCPU-prod-api-server"

# Or pass a full SNS payload
python main.py --payload '{"alarm_name": "Lambda-Errors-payment", "state": "ALARM"}'

# 🔍 Verbose mode (see every tool call)
python main.py --alarm "HighCPU-prod-api-server" --verbose
```

### 📋 Prerequisites

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

## 📊 Example Output

```
🚨 INCIDENT TRIAGE REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━
Alarm: HighCPU-prod-api-server
Fired: 2026-07-22 03:14 UTC
Current Value: 94% CPU (threshold: 80%)

📈 TREND: Sustained spike since 03:10, NOT recovering

🔍 ERRORS FOUND:
- 847 "Connection pool exhausted" errors (03:10-03:14)
- Stack trace points to /api/v2/search handler

🔄 RECENT CHANGE FOUND:
- 03:08 UTC: ECS deployment by ci-pipeline-role
- Image tag: v2.4.1 → v2.5.0 (2 min before spike)

🎯 PROBABLE ROOT CAUSE:
Deployment v2.5.0 introduced connection leak in search handler

⚡ RECOMMENDED ACTION: ROLLBACK to v2.4.1
📊 CONFIDENCE: 87%
🔒 STATUS: AWAITING HUMAN APPROVAL (production service)
```

⏱️ Total time: **4.6 seconds** (including Bedrock model latency).

---

## 🛡️ Safety Hooks

> System prompts are suggestions. **Hooks are laws.**

The agent has deterministic safety hooks that the LLM **cannot override**, no matter what it reasons:

| Hook | What It Enforces | Why |
|------|-----------------|-----|
| 🔋 **Budget Cap** | Max 15 tool calls per invocation | Prevents infinite loops |
| ⚡ **Fail-Fast** | Stop after 3 consecutive API failures | Don't waste time when permissions are broken |
| 🚫 **Production Guard** | Block ALL remediation on `prod-*` services | No cowboy automation at 3AM |
| 🔐 **Auth Sanitization** | Strip IAM ARNs from error messages | Don't leak infra details to the model |

```python
# The hook fires BEFORE the tool executes. The model never gets a choice.
if tool_name == "rollback_deployment" and "prod-" in service_name:
    event.cancel_tool = (
        "BLOCKED: Remediation on production requires human approval. "
        "Mark it as AWAITING HUMAN APPROVAL in your report."
    )
```

---

## 📁 Project Structure

```
aws-oncall-triage-ai-agent/
├── src/
│   ├── main.py              # 🤖 Agent setup (~20 lines of agent code)
│   ├── tools.py             # 🔧 6 @tool decorated investigation functions
│   ├── hooks.py             # 🛡️ Safety hooks (HookProvider pattern)
│   ├── sop.md               # 📋 Natural language triage procedure
│   ├── config.py            # ⚙️ Thresholds, model ID, region
│   └── requirements.txt     # 📦 Dependencies
├── tests/
│   ├── test_hooks.py        # ✅ 6 unit tests for safety hooks
│   └── simulate_alarm.py    # 🧪 Synthetic alarm scenarios
└── README.md
```

---

## ⚙️ Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | Region for all AWS API calls |
| `BEDROCK_MODEL_ID` | `amazon.nova-pro-v1:0` | Bedrock model to use |
| `SLACK_WEBHOOK_URL` | *(empty)* | Slack webhook for report delivery |

Tune safety thresholds in `src/config.py`:

```python
MAX_TOOL_CALLS_PER_INVOCATION = 15   # 🔋 Budget cap
MAX_CONSECUTIVE_FAILURES = 3          # ⚡ Fail-fast threshold
PRODUCTION_SERVICES = ["prod-", "production-", "prd-"]  # 🚫 Guard prefixes
```

---

## 🚀 Deploy to Lambda

For always-on triage, deploy as a Lambda triggered by SNS:

```
CloudWatch Alarm → SNS Topic → Lambda (this agent) → Slack
```

The agent code already accepts SNS alarm payloads via `run_triage(payload=event)`.

---

## ✅ Running Tests

```bash
# Unit tests (no AWS credentials needed)
cd tests/
python test_hooks.py

# Preview alarm scenarios
python simulate_alarm.py --scenario bad_deploy --dry-run
python simulate_alarm.py --scenario connection_leak --dry-run
```

```
✓ test_budget_cap passed
✓ test_fail_fast passed
✓ test_fail_fast_resets_on_success passed
✓ test_production_remediation_blocked passed
✓ test_non_production_remediation_allowed passed
✓ test_auth_error_sanitization passed

All hook tests passed! ✅
```

---

## 🧩 Strands SDK Features Used

| Feature | How It's Used |
|---------|--------------|
| `@tool` decorator | 6 custom tools wrapping AWS SDK calls |
| `HookProvider` + `HookRegistry` | Deterministic safety guardrails |
| `BedrockModel` | Amazon Nova Pro via Bedrock |
| System prompt as SOP | Markdown file loaded as agent instructions |
| `BeforeToolCallEvent` | Block dangerous calls before execution |
| `AfterToolCallEvent` | Sanitize results before model sees them |

---

## 🗺️ Roadmap

- [ ] 📟 PagerDuty integration (auto-acknowledge + enrich)
- [ ] 💬 Slack interactive buttons ("Approve Rollback" / "Escalate")
- [ ] 🔗 Multi-service correlation (trace across microservices)
- [ ] 🧠 Historical pattern matching ("this looks like the March 12 outage")
- [ ] ☁️ AgentCore Runtime deployment for managed hosting

---

## 🛠️ Built With

| Tool | Purpose |
|------|---------|
| [Strands Agents SDK](https://github.com/strands-agents/sdk-python) | Agent framework |
| [Amazon Bedrock](https://aws.amazon.com/bedrock/) | LLM inference (Nova Pro) |
| [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) | AWS SDK for Python |
| [CloudWatch](https://aws.amazon.com/cloudwatch/) | Metrics, Logs, Alarms |
| [CloudTrail](https://aws.amazon.com/cloudtrail/) | API audit trail (the secret weapon 🔫) |

---

## 📄 License

MIT

---

## ⭐ Star This Repo

If this saved you from a 3AM triage nightmare, consider giving it a ⭐. It helps others find it too.

---

## 👨‍💻 Author

<table>
  <tr>
    <td>
      <strong>Sarvar Nadaf</strong><br>
      Cloud Architect at Big 4 | 10+ Years in Cloud<br>
      AWS x7 | Azure x2 | GCP x1<br>
      AWS Community Builder (4 years) | Dev.to Moderator<br>
      200+ Articles | 15K+ Followers | 240K+ Readers<br><br>
      <a href="https://sarvarnadaf.com">🌐 sarvarnadaf.com</a> •
      <a href="https://www.linkedin.com/in/sarvar04/">💼 LinkedIn</a> •
      <a href="https://dev.to/sarvar_04">📝 Dev.to</a>
    </td>
  </tr>
</table>
