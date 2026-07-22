"""Configuration for the On-Call Triage Agent."""

import os

# AWS Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Bedrock Model
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")

# Triage Configuration
METRIC_LOOKBACK_MINUTES = 60  # How far back to check metric trends
LOG_SEARCH_WINDOW_MINUTES = 10  # Window around alarm time for log search
CLOUDTRAIL_LOOKBACK_HOURS = 24  # How far back to check for changes
MAX_LOG_RESULTS = 50  # Max log lines to return

# Safety Thresholds
CONFIDENCE_THRESHOLD_FOR_ACTION = 70  # Minimum confidence to recommend auto-fix
PRODUCTION_SERVICES = [
    "prod-",
    "production-",
    "prd-",
]

# Slack Configuration (optional)
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

# Hook Configuration
MAX_TOOL_CALLS_PER_INVOCATION = 15
MAX_CONSECUTIVE_FAILURES = 3
