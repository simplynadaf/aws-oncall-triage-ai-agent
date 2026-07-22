"""
On-Call Triage Agent - Custom Tools

Six @tool decorated functions that give the agent the ability to investigate
incidents by querying AWS services: CloudWatch Alarms, Metrics, Logs,
CloudTrail, ECS, and Lambda.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import boto3
from strands import tool

from config import (
    AWS_REGION,
    CLOUDTRAIL_LOOKBACK_HOURS,
    LOG_SEARCH_WINDOW_MINUTES,
    MAX_LOG_RESULTS,
    METRIC_LOOKBACK_MINUTES,
)

logger = logging.getLogger(__name__)

# AWS clients (initialized once, reused across tool calls)
cloudwatch = boto3.client("cloudwatch", region_name=AWS_REGION)
logs_client = boto3.client("logs", region_name=AWS_REGION)
cloudtrail = boto3.client("cloudtrail", region_name=AWS_REGION)
ecs = boto3.client("ecs", region_name=AWS_REGION)
lambda_client = boto3.client("lambda", region_name=AWS_REGION)


@tool
def get_alarm_details(alarm_name: str) -> dict:
    """Get details about a CloudWatch alarm including its current state, metric, threshold, and when it fired.

    Args:
        alarm_name: The name of the CloudWatch alarm to investigate.

    Returns:
        Dictionary with alarm state, metric details, threshold, and timestamps.
    """
    try:
        response = cloudwatch.describe_alarms(AlarmNames=[alarm_name])

        if not response["MetricAlarms"]:
            return {"error": f"Alarm '{alarm_name}' not found"}

        alarm = response["MetricAlarms"][0]
        return {
            "alarm_name": alarm["AlarmName"],
            "state": alarm["StateValue"],
            "state_reason": alarm.get("StateReason", ""),
            "metric_name": alarm.get("MetricName", ""),
            "namespace": alarm.get("Namespace", ""),
            "statistic": alarm.get("Statistic", ""),
            "threshold": alarm.get("Threshold"),
            "comparison_operator": alarm.get("ComparisonOperator", ""),
            "evaluation_periods": alarm.get("EvaluationPeriods"),
            "period_seconds": alarm.get("Period"),
            "dimensions": alarm.get("Dimensions", []),
            "state_updated": alarm.get("StateUpdatedTimestamp", "").isoformat()
            if alarm.get("StateUpdatedTimestamp")
            else "",
        }
    except Exception as e:
        logger.error(f"Error getting alarm details: {e}")
        return {"error": str(e)}


@tool
def query_metric_trend(
    metric_name: str, namespace: str, dimensions: list, period_minutes: int = 60
) -> dict:
    """Query CloudWatch metric data to see the trend leading up to and during the incident.

    Args:
        metric_name: The metric name (e.g., CPUUtilization, Duration, Errors).
        namespace: The CloudWatch namespace (e.g., AWS/ECS, AWS/Lambda, AWS/EC2).
        dimensions: List of dimension dicts with Name and Value keys.
        period_minutes: How many minutes of history to retrieve. Defaults to 60.

    Returns:
        Dictionary with metric data points showing the trend over time.
    """
    try:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=period_minutes)

        # Use 1-minute granularity for recent data
        response = cloudwatch.get_metric_data(
            MetricDataQueries=[
                {
                    "Id": "m1",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": namespace,
                            "MetricName": metric_name,
                            "Dimensions": dimensions,
                        },
                        "Period": 60,  # 1-minute intervals
                        "Stat": "Average",
                    },
                    "ReturnData": True,
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            ScanBy="TimestampAscending",
        )

        results = response["MetricDataResults"][0]
        data_points = []
        for ts, val in zip(results["Timestamps"], results["Values"]):
            data_points.append({"timestamp": ts.isoformat(), "value": round(val, 2)})

        # Calculate trend summary
        values = results["Values"]
        if values:
            current = values[-1] if values else 0
            avg = sum(values) / len(values)
            peak = max(values)
            trend = "rising" if len(values) > 5 and values[-1] > values[-5] else "stable_or_falling"
        else:
            current, avg, peak, trend = 0, 0, 0, "no_data"

        return {
            "metric_name": metric_name,
            "namespace": namespace,
            "period_minutes": period_minutes,
            "data_points_count": len(data_points),
            "current_value": round(current, 2),
            "average": round(avg, 2),
            "peak": round(peak, 2),
            "trend": trend,
            "recent_data_points": data_points[-10:],  # Last 10 minutes
        }
    except Exception as e:
        logger.error(f"Error querying metric: {e}")
        return {"error": str(e)}


@tool
def search_logs(log_group: str, query: str, minutes_window: int = 10) -> dict:
    """Search CloudWatch Logs using Logs Insights to find errors and relevant log entries around the incident time.

    Args:
        log_group: The CloudWatch Log Group name to search.
        query: CloudWatch Logs Insights query string. Use 'fields @timestamp, @message | filter @message like /ERROR/' style syntax.
        minutes_window: How many minutes around now to search. Defaults to 10.

    Returns:
        Dictionary with matching log entries and summary statistics.
    """
    try:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=minutes_window)

        response = logs_client.start_query(
            logGroupName=log_group,
            startTime=int(start_time.timestamp()),
            endTime=int(end_time.timestamp()),
            queryString=query,
            limit=MAX_LOG_RESULTS,
        )

        query_id = response["queryId"]

        # Poll for results (max 30 seconds)
        import time

        for _ in range(30):
            result = logs_client.get_query_results(queryId=query_id)
            if result["status"] in ("Complete", "Failed", "Cancelled"):
                break
            time.sleep(1)

        if result["status"] != "Complete":
            return {"error": f"Query did not complete: {result['status']}"}

        # Parse results
        log_entries = []
        for row in result["results"][:MAX_LOG_RESULTS]:
            entry = {}
            for field in row:
                entry[field["field"]] = field["value"]
            log_entries.append(entry)

        return {
            "log_group": log_group,
            "query": query,
            "window_minutes": minutes_window,
            "total_results": len(log_entries),
            "entries": log_entries[:20],  # Return top 20 for context
            "statistics": result.get("statistics", {}),
        }
    except Exception as e:
        logger.error(f"Error searching logs: {e}")
        return {"error": str(e)}


@tool
def check_recent_changes(service_name: str, hours: int = 24) -> dict:
    """Query CloudTrail to find recent API changes related to a service. This helps identify if a deployment or config change caused the incident.

    Args:
        service_name: The service or resource name to filter changes for (e.g., 'prod-api', 'my-lambda').
        hours: How many hours back to look for changes. Defaults to 24.

    Returns:
        Dictionary with recent changes including who made them and when.
    """
    try:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours)

        # Strategy 1: Try ResourceName lookup
        try:
            response = cloudtrail.lookup_events(
                LookupAttributes=[
                    {"AttributeKey": "ResourceName", "AttributeValue": service_name}
                ],
                StartTime=start_time,
                EndTime=end_time,
                MaxResults=20,
            )
            events = response.get("Events", [])
        except Exception:
            events = []

        # Strategy 2: If no results, try broader search by EventSource
        if not events:
            event_sources = {
                "lambda": "lambda.amazonaws.com",
                "ecs": "ecs.amazonaws.com",
                "ec2": "ec2.amazonaws.com",
            }
            source = None
            for key, val in event_sources.items():
                if key in service_name.lower():
                    source = val
                    break

            if source:
                try:
                    response = cloudtrail.lookup_events(
                        LookupAttributes=[
                            {"AttributeKey": "EventSource", "AttributeValue": source}
                        ],
                        StartTime=start_time,
                        EndTime=end_time,
                        MaxResults=20,
                    )
                    events = response.get("Events", [])
                except Exception:
                    events = []

        # Strategy 3: If still nothing, do unfiltered lookup
        if not events:
            try:
                response = cloudtrail.lookup_events(
                    StartTime=start_time,
                    EndTime=end_time,
                    MaxResults=20,
                )
                events = response.get("Events", [])
            except Exception:
                events = []

        changes = []
        for event in events:
            cloud_trail_event = json.loads(event.get("CloudTrailEvent", "{}"))
            changes.append(
                {
                    "event_time": event["EventTime"].isoformat(),
                    "event_name": event.get("EventName", ""),
                    "username": event.get("Username", "unknown"),
                    "source_ip": cloud_trail_event.get("sourceIPAddress", ""),
                    "user_agent": cloud_trail_event.get("userAgent", "")[:100],
                    "read_only": cloud_trail_event.get("readOnly", True),
                    "resources": [
                        r.get("resourceName", "") for r in event.get("Resources", [])
                    ],
                }
            )

        # Filter to write events (actual changes)
        write_changes = [c for c in changes if not c["read_only"]]

        return {
            "service_name": service_name,
            "hours_searched": hours,
            "total_events": len(changes),
            "write_events": len(write_changes),
            "changes": write_changes[:10],  # Most recent 10 changes
        }
    except Exception as e:
        logger.error(f"Error checking CloudTrail: {e}")
        return {"error": str(e)}


@tool
def get_deployment_history(service_name: str, cluster: str = "") -> dict:
    """Check recent ECS deployments or Lambda function updates to identify if a bad deploy caused the incident.

    Args:
        service_name: The ECS service name or Lambda function name.
        cluster: ECS cluster name. Leave empty for Lambda functions.

    Returns:
        Dictionary with recent deployments, their status, and timing.
    """
    try:
        # Try ECS first if cluster is provided
        if cluster:
            response = ecs.describe_services(
                cluster=cluster, services=[service_name]
            )
            if response["services"]:
                service = response["services"][0]
                deployments = []
                for dep in service.get("deployments", []):
                    deployments.append(
                        {
                            "id": dep.get("id", ""),
                            "status": dep.get("status", ""),
                            "task_definition": dep.get("taskDefinition", "").split("/")[-1],
                            "desired_count": dep.get("desiredCount", 0),
                            "running_count": dep.get("runningCount", 0),
                            "created_at": dep.get("createdAt", "").isoformat()
                            if dep.get("createdAt")
                            else "",
                            "updated_at": dep.get("updatedAt", "").isoformat()
                            if dep.get("updatedAt")
                            else "",
                        }
                    )
                return {
                    "service_type": "ECS",
                    "service_name": service_name,
                    "cluster": cluster,
                    "status": service.get("status", ""),
                    "desired_count": service.get("desiredCount", 0),
                    "running_count": service.get("runningCount", 0),
                    "deployments": deployments,
                    "events": [
                        {"message": e["message"], "created_at": e["createdAt"].isoformat()}
                        for e in service.get("events", [])[:5]
                    ],
                }

        # Try Lambda
        response = lambda_client.get_function(FunctionName=service_name)
        config = response["Configuration"]

        # Get recent versions
        versions_response = lambda_client.list_versions_by_function(
            FunctionName=service_name, MaxItems=5
        )

        versions = []
        for v in versions_response.get("Versions", []):
            versions.append(
                {
                    "version": v.get("Version", ""),
                    "last_modified": v.get("LastModified", ""),
                    "runtime": v.get("Runtime", ""),
                    "memory": v.get("MemorySize", 0),
                    "timeout": v.get("Timeout", 0),
                }
            )

        return {
            "service_type": "Lambda",
            "function_name": service_name,
            "runtime": config.get("Runtime", ""),
            "last_modified": config.get("LastModified", ""),
            "memory_mb": config.get("MemorySize", 0),
            "timeout_seconds": config.get("Timeout", 0),
            "state": config.get("State", ""),
            "recent_versions": versions,
        }
    except Exception as e:
        logger.error(f"Error getting deployment history: {e}")
        return {"error": str(e)}


@tool
def post_incident_report(report: str, channel: str = "console") -> dict:
    """Post the structured incident triage report to Slack or console output.

    Args:
        report: The formatted incident report text to post.
        channel: Where to post - 'console' for stdout or 'slack' for Slack webhook.

    Returns:
        Dictionary confirming the report was posted successfully.
    """
    try:
        if channel == "console" or not config_slack_url():
            print("\n" + "=" * 60)
            print(report)
            print("=" * 60 + "\n")
            return {"status": "posted", "channel": "console", "length": len(report)}

        # Post to Slack
        import requests

        payload = {"text": report, "mrkdwn": True}
        response = requests.post(
            config_slack_url(), json=payload, timeout=10
        )
        response.raise_for_status()

        return {"status": "posted", "channel": "slack", "length": len(report)}
    except Exception as e:
        logger.error(f"Error posting report: {e}")
        return {"error": str(e), "fallback": "printed to console"}


def config_slack_url():
    """Get Slack webhook URL from config."""
    from config import SLACK_WEBHOOK_URL
    return SLACK_WEBHOOK_URL
