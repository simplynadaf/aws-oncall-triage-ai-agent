"""Simulate a CloudWatch alarm to test the triage agent end-to-end.

This script creates a synthetic alarm scenario for testing without
needing real AWS alarms to fire. It mocks the AWS API responses
to simulate a realistic incident.

Usage:
    python simulate_alarm.py
    python simulate_alarm.py --scenario bad_deploy
    python simulate_alarm.py --scenario connection_leak
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

sys.path.insert(0, "../src")


# --- Scenario Definitions ---

SCENARIOS = {
    "bad_deploy": {
        "description": "ECS deployment causes CPU spike due to connection leak",
        "alarm": {
            "AlarmName": "HighCPU-prod-api-server",
            "StateValue": "ALARM",
            "StateReason": "Threshold Crossed: 3 out of 3 datapoints were greater than the threshold (80.0).",
            "MetricName": "CPUUtilization",
            "Namespace": "AWS/ECS",
            "Statistic": "Average",
            "Threshold": 80.0,
            "ComparisonOperator": "GreaterThanThreshold",
            "EvaluationPeriods": 3,
            "Period": 60,
            "Dimensions": [
                {"Name": "ClusterName", "Value": "prod-cluster"},
                {"Name": "ServiceName", "Value": "prod-api-server"},
            ],
        },
        "metric_values": [45, 48, 52, 55, 60, 72, 85, 91, 94, 94],
        "log_entries": [
            {"@timestamp": "2026-07-22T03:12:00Z", "@message": "ERROR: Connection pool exhausted - max connections (100) reached"},
            {"@timestamp": "2026-07-22T03:12:15Z", "@message": "ERROR: Connection pool exhausted - max connections (100) reached"},
            {"@timestamp": "2026-07-22T03:12:30Z", "@message": "FATAL: Unable to acquire connection from pool after 30000ms timeout"},
            {"@timestamp": "2026-07-22T03:13:00Z", "@message": "ERROR: Request timeout on /api/v2/search - handler exceeded 30s"},
            {"@timestamp": "2026-07-22T03:13:15Z", "@message": "ERROR: Connection pool exhausted - max connections (100) reached"},
        ],
        "cloudtrail_events": [
            {
                "EventName": "UpdateService",
                "Username": "ci-pipeline-role",
                "Resources": [{"resourceName": "prod-api-server"}],
            }
        ],
    },
    "connection_leak": {
        "description": "Lambda function hitting connection timeout after dependency outage",
        "alarm": {
            "AlarmName": "Lambda-Errors-payment-processor",
            "StateValue": "ALARM",
            "StateReason": "Threshold Crossed: 5 out of 5 datapoints were greater than the threshold (5.0).",
            "MetricName": "Errors",
            "Namespace": "AWS/Lambda",
            "Statistic": "Sum",
            "Threshold": 5.0,
            "ComparisonOperator": "GreaterThanThreshold",
            "EvaluationPeriods": 5,
            "Period": 60,
            "Dimensions": [
                {"Name": "FunctionName", "Value": "prod-payment-processor"},
            ],
        },
        "metric_values": [0, 0, 1, 3, 8, 15, 22, 31, 28, 25],
        "log_entries": [
            {"@timestamp": "2026-07-22T03:10:00Z", "@message": "ERROR: ConnectionRefusedError: [Errno 111] Connection refused - payments-api.internal:443"},
            {"@timestamp": "2026-07-22T03:10:05Z", "@message": "ERROR: Task timed out after 30.00 seconds"},
            {"@timestamp": "2026-07-22T03:10:30Z", "@message": "ERROR: ConnectionRefusedError: [Errno 111] Connection refused - payments-api.internal:443"},
            {"@timestamp": "2026-07-22T03:11:00Z", "@message": "ERROR: Max retries exceeded for url: https://payments-api.internal/v1/charge"},
        ],
        "cloudtrail_events": [],
    },
}


def print_scenario_info(scenario_name: str, scenario: dict):
    """Print info about the scenario being simulated."""
    print(f"\n{'='*60}")
    print(f"SIMULATING SCENARIO: {scenario_name}")
    print(f"Description: {scenario['description']}")
    print(f"Alarm: {scenario['alarm']['AlarmName']}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Simulate alarm scenarios for testing")
    parser.add_argument(
        "--scenario",
        type=str,
        default="bad_deploy",
        choices=list(SCENARIOS.keys()),
        help="Which incident scenario to simulate",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print scenario details without running the agent",
    )

    args = parser.parse_args()
    scenario = SCENARIOS[args.scenario]

    print_scenario_info(args.scenario, scenario)

    if args.dry_run:
        print("Alarm details:")
        print(json.dumps({k: str(v) for k, v in scenario["alarm"].items()}, indent=2))
        print(f"\nLog entries: {len(scenario['log_entries'])}")
        print(f"CloudTrail events: {len(scenario['cloudtrail_events'])}")
        return

    print("To run with mocked AWS APIs, use:")
    print(f"  python -m pytest test_tools.py --scenario {args.scenario}")
    print("\nTo run against real AWS (requires alarm to exist):")
    print(f"  python main.py --alarm \"{scenario['alarm']['AlarmName']}\"")


if __name__ == "__main__":
    main()
