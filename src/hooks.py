"""On-Call Triage Agent - Safety Hooks

Hooks that enforce deterministic safety rules the LLM cannot bypass:
1. Block destructive actions on production services
2. Cap total tool calls to prevent runaway loops
3. Fail-fast on consecutive errors
4. Require human approval for any remediation action
"""

import logging
from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent, AfterToolCallEvent

from config import (
    MAX_TOOL_CALLS_PER_INVOCATION,
    MAX_CONSECUTIVE_FAILURES,
    PRODUCTION_SERVICES,
    CONFIDENCE_THRESHOLD_FOR_ACTION,
)

logger = logging.getLogger(__name__)


class TriageAgentHooks(HookProvider):
    """Safety hooks for the on-call triage agent.

    These hooks enforce rules that system prompts cannot guarantee:
    - No auto-remediation on production services without human approval
    - Budget cap on tool calls to prevent infinite investigation loops
    - Fail-fast when AWS APIs are consistently failing
    """

    def __init__(self):
        self.tool_call_count = 0
        self.consecutive_failures = 0
        self.remediation_blocked = False

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self._before_tool)
        registry.add_callback(AfterToolCallEvent, self._after_tool)

    def _before_tool(self, event: BeforeToolCallEvent, **kwargs) -> None:
        """Pre-tool-call checks: budget cap, fail-fast, production guard."""
        self.tool_call_count += 1
        tool_name = event.tool_use.get("name", "")
        tool_input = event.tool_use.get("input", {}) or {}

        # Never block the report tool - it's the final output step
        ALWAYS_ALLOW_TOOLS = ("post_incident_report",)
        if tool_name in ALWAYS_ALLOW_TOOLS:
            return

        # --- Budget Cap ---
        if self.tool_call_count > MAX_TOOL_CALLS_PER_INVOCATION:
            logger.warning(
                f"Hooks: tool call limit reached (count={self.tool_call_count})"
            )
            event.cancel_tool = (
                f"BUDGET: Tool call limit ({MAX_TOOL_CALLS_PER_INVOCATION}) reached. "
                "You have enough information to produce a triage report. "
                "Summarize your findings so far and present the incident report. "
                "Do NOT attempt further investigation."
            )
            return

        # --- Fail-Fast ---
        if self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            logger.warning(
                f"Hooks: fail-fast triggered after {self.consecutive_failures} "
                f"consecutive failures"
            )
            event.cancel_tool = (
                f"FAIL_FAST: {MAX_CONSECUTIVE_FAILURES} consecutive tool failures. "
                "Something is fundamentally broken (permissions? connectivity?). "
                "Stop calling tools. Tell the user that investigation is blocked "
                "due to repeated API failures. Report what you found so far. "
                "Do NOT improvise or guess answers."
            )
            return

        # --- Production Remediation Guard ---
        if tool_name == "rollback_deployment":
            service = tool_input.get("service_name", "")
            is_production = any(
                prefix in service.lower() for prefix in PRODUCTION_SERVICES
            )

            if is_production:
                logger.warning(
                    f"Hooks: BLOCKED remediation on production service '{service}'"
                )
                self.remediation_blocked = True
                event.cancel_tool = (
                    "BLOCKED: Remediation actions on production services require "
                    "human approval. You are in INVESTIGATION-ONLY mode. "
                    "Include your recommended action in the triage report with "
                    "confidence level, but do NOT execute it. "
                    "Mark it as: AWAITING HUMAN APPROVAL."
                )
                return

    def _after_tool(self, event: AfterToolCallEvent, **kwargs) -> None:
        """Post-tool-call: track failures, sanitize error messages."""
        result = event.result or {}
        result_content = str(result.get("content", ""))
        tool_name = event.tool_use.get("name", "") if event.tool_use else ""

        # Don't count the report tool toward failures
        if tool_name == "post_incident_report":
            return

        # Check for actual errors (not empty results)
        is_error = (
            event.exception is not None
            or result.get("status") == "error"
            or '"error":' in result_content.lower()[:200]
        )

        if is_error:
            self.consecutive_failures += 1
            logger.info(
                f"Hooks: tool failure "
                f"(consecutive_failures={self.consecutive_failures})"
            )

            # Sanitize authorization errors - don't leak IAM details to the model
            auth_markers = (
                "AccessDenied",
                "AccessDeniedException",
                "is not authorized to perform",
                "UnauthorizedAccess",
            )
            if any(marker in result_content for marker in auth_markers):
                logger.warning(
                    f"Hooks: auth failure detected. "
                    f"Original: {result_content[:200]}"
                )
                event.result["content"] = [
                    {
                        "text": (
                            "[AUTHORIZATION FAILURE] A permission issue blocked this "
                            "operation. Note this in your report as a limitation. "
                            "Do NOT relay IAM action names or ARNs. "
                            "Continue investigating with other tools if possible."
                        )
                    }
                ]
        else:
            # Reset failure counter on success
            self.consecutive_failures = 0
