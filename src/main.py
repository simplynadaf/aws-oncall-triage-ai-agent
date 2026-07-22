"""On-Call Triage Agent - Main Entry Point

Usage:
    python main.py --alarm "HighCPU-prod-api"
    python main.py --alarm "Lambda-Errors-payment-processor"
    python main.py --payload '{"alarm_name": "...", "state": "ALARM", ...}'
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from strands import Agent
from strands.models import BedrockModel

from config import AWS_REGION, MODEL_ID
from hooks import TriageAgentHooks
from tools import (
    get_alarm_details,
    query_metric_trend,
    search_logs,
    check_recent_changes,
    get_deployment_history,
    post_incident_report,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("triage_agent")


def load_sop() -> str:
    """Load the agent SOP from the markdown file."""
    sop_path = Path(__file__).parent / "sop.md"
    return sop_path.read_text()


def create_agent() -> Agent:
    """Create and configure the triage agent with tools and hooks."""

    # Load the natural language SOP as system prompt
    system_prompt = load_sop()

    # Configure Bedrock model
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=AWS_REGION,
    )

    # Create agent with tools and safety hooks
    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[
            get_alarm_details,
            query_metric_trend,
            search_logs,
            check_recent_changes,
            get_deployment_history,
            post_incident_report,
        ],
        hooks=[TriageAgentHooks()],
    )

    return agent


def run_triage(alarm_name: str = None, payload: dict = None) -> str:
    """Run the triage agent against an alarm.

    Args:
        alarm_name: Name of the CloudWatch alarm to investigate.
        payload: Full alarm payload (from SNS/Lambda trigger).

    Returns:
        The agent's triage report as a string.
    """
    agent = create_agent()

    if payload:
        prompt = (
            f"A CloudWatch alarm has fired. Here is the full alarm payload:\n\n"
            f"```json\n{json.dumps(payload, indent=2)}\n```\n\n"
            f"Follow your triage procedure to investigate this incident "
            f"and produce a structured report."
        )
    elif alarm_name:
        prompt = (
            f"A CloudWatch alarm named '{alarm_name}' has fired. "
            f"Follow your triage procedure to investigate this incident "
            f"and produce a structured report."
        )
    else:
        print("Error: Provide either --alarm or --payload")
        sys.exit(1)

    logger.info(f"Starting triage for: {alarm_name or 'payload'}")
    result = agent(prompt)
    logger.info("Triage complete")

    return str(result)


def main():
    parser = argparse.ArgumentParser(
        description="On-Call Triage Agent - Investigates CloudWatch alarms"
    )
    parser.add_argument(
        "--alarm", type=str, help="CloudWatch alarm name to investigate"
    )
    parser.add_argument(
        "--payload",
        type=str,
        help="JSON alarm payload (from SNS notification)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable debug logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    payload = None
    if args.payload:
        payload = json.loads(args.payload)

    result = run_triage(alarm_name=args.alarm, payload=payload)
    print(result)


if __name__ == "__main__":
    main()
