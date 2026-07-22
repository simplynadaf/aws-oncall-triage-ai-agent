"""Unit tests for the safety hooks."""

import sys
sys.path.insert(0, "../src")

from unittest.mock import MagicMock
from hooks import TriageAgentHooks


def make_before_event(tool_name: str, tool_input: dict = None):
    """Create a mock BeforeToolCallEvent."""
    event = MagicMock()
    event.tool_use = {"name": tool_name, "input": tool_input or {}}
    event.cancel_tool = None
    return event


def make_after_event(tool_name: str, result_content: str, status: str = "success"):
    """Create a mock AfterToolCallEvent."""
    event = MagicMock()
    event.tool_use = {"name": tool_name}
    event.result = {"content": [{"text": result_content}], "status": status}
    event.exception = None
    return event


def test_budget_cap():
    """Budget cap fires after MAX_TOOL_CALLS."""
    hooks = TriageAgentHooks()

    # Simulate 15 successful tool calls (should all pass)
    for i in range(15):
        event = make_before_event("get_alarm_details")
        hooks._before_tool(event)
        assert event.cancel_tool is None, f"Call {i+1} should pass"

    # 16th call should be blocked
    event = make_before_event("get_alarm_details")
    hooks._before_tool(event)
    assert event.cancel_tool is not None
    assert "BUDGET" in event.cancel_tool


def test_fail_fast():
    """Fail-fast triggers after 3 consecutive failures."""
    hooks = TriageAgentHooks()

    # Simulate 3 consecutive failures via _after_tool
    for _ in range(3):
        event = make_before_event("search_logs")
        hooks._before_tool(event)  # increment counter

        after_event = make_after_event("search_logs", "error occurred", status="error")
        hooks._after_tool(after_event)

    # Next before_tool should trigger fail-fast
    event = make_before_event("search_logs")
    hooks._before_tool(event)
    assert event.cancel_tool is not None
    assert "FAIL_FAST" in event.cancel_tool


def test_fail_fast_resets_on_success():
    """Consecutive failure counter resets after a successful call."""
    hooks = TriageAgentHooks()

    # 2 failures
    for _ in range(2):
        event = make_before_event("search_logs")
        hooks._before_tool(event)
        after_event = make_after_event("search_logs", "error", status="error")
        hooks._after_tool(after_event)

    # 1 success resets the counter
    event = make_before_event("get_alarm_details")
    hooks._before_tool(event)
    after_event = make_after_event("get_alarm_details", "alarm info here")
    hooks._after_tool(after_event)

    assert hooks.consecutive_failures == 0

    # 2 more failures should NOT trigger fail-fast (need 3 consecutive)
    for _ in range(2):
        event = make_before_event("search_logs")
        hooks._before_tool(event)
        after_event = make_after_event("search_logs", "error", status="error")
        hooks._after_tool(after_event)

    event = make_before_event("search_logs")
    hooks._before_tool(event)
    assert event.cancel_tool is None  # Still at 2, not 3


def test_production_remediation_blocked():
    """Rollback on production services is blocked."""
    hooks = TriageAgentHooks()

    event = make_before_event(
        "rollback_deployment",
        {"service_name": "prod-api-server", "target_version": "v2.4.1"},
    )
    hooks._before_tool(event)

    assert event.cancel_tool is not None
    assert "BLOCKED" in event.cancel_tool
    assert "HUMAN APPROVAL" in event.cancel_tool


def test_non_production_remediation_allowed():
    """Rollback on non-production services is allowed."""
    hooks = TriageAgentHooks()

    event = make_before_event(
        "rollback_deployment",
        {"service_name": "dev-api-server", "target_version": "v2.4.1"},
    )
    hooks._before_tool(event)

    assert event.cancel_tool is None


def test_auth_error_sanitization():
    """Authorization errors are sanitized before reaching the model."""
    hooks = TriageAgentHooks()

    # Simulate tool call
    event = make_before_event("search_logs")
    hooks._before_tool(event)

    # Simulate auth error in result
    after_event = make_after_event(
        "search_logs",
        "An error occurred (AccessDeniedException) when calling StartQuery: "
        "You are not authorized to perform: logs:StartQuery on resource: "
        "arn:aws:logs:us-east-1:123456789:log-group:/prod/api",
        status="error",
    )
    hooks._after_tool(after_event)

    # Result should be sanitized
    sanitized_text = after_event.result["content"][0]["text"]
    assert "AUTHORIZATION FAILURE" in sanitized_text
    assert "arn:aws:logs" not in sanitized_text
    assert "StartQuery" not in sanitized_text


if __name__ == "__main__":
    test_budget_cap()
    print("\u2713 test_budget_cap passed")

    test_fail_fast()
    print("\u2713 test_fail_fast passed")

    test_fail_fast_resets_on_success()
    print("\u2713 test_fail_fast_resets_on_success passed")

    test_production_remediation_blocked()
    print("\u2713 test_production_remediation_blocked passed")

    test_non_production_remediation_allowed()
    print("\u2713 test_non_production_remediation_allowed passed")

    test_auth_error_sanitization()
    print("\u2713 test_auth_error_sanitization passed")

    print("\nAll hook tests passed!")
