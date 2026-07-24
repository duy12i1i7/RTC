"""Map terminal ROS 2 task results into FleetQoX application outcomes."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


APPLICATION_OUTCOME_SCHEMA_VERSION = (
    "fleetrmw.quic_gateway_application_outcome.v1"
)
TASK_KINDS = frozenset({"generic", "nav2", "rmf"})
TERMINAL_STATUSES = frozenset(
    {"succeeded", "aborted", "canceled", "rejected", "failed", "timed_out"}
)
NAV2_TERMINAL_STATUS = {
    4: "succeeded",
    5: "canceled",
    6: "aborted",
}


@dataclass(frozen=True)
class TaskOutcomeCorrelation:
    """Accepted FleetRMW frame identity to which one terminal result belongs."""

    domain_id: int
    topic: str
    publisher_id: str
    source_sequence_number: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.domain_id, int)
            or isinstance(self.domain_id, bool)
            or self.domain_id < 0
        ):
            raise ValueError("task outcome domain_id is invalid")
        if not isinstance(self.topic, str) or not self.topic.startswith("/"):
            raise ValueError("task outcome topic is invalid")
        if not isinstance(self.publisher_id, str) or not self.publisher_id:
            raise ValueError("task outcome publisher_id is invalid")
        if (
            not isinstance(self.source_sequence_number, int)
            or isinstance(self.source_sequence_number, bool)
            or self.source_sequence_number <= 0
        ):
            raise ValueError("task outcome source sequence is invalid")


def build_task_application_outcome(
    correlation: TaskOutcomeCorrelation,
    *,
    task_kind: str,
    terminal_status: str,
    observed_latency_ms: float,
    deadline_ms: float,
    result_received: bool = True,
) -> dict[str, Any]:
    """Build a gateway outcome while keeping transport and task success distinct."""

    if task_kind not in TASK_KINDS:
        raise ValueError("unsupported task outcome kind")
    if terminal_status not in TERMINAL_STATUSES:
        raise ValueError("unsupported terminal task status")
    if not isinstance(result_received, bool):
        raise ValueError("task outcome result_received must be boolean")
    if not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        for value in (observed_latency_ms, deadline_ms)
    ):
        raise ValueError("task outcome latency/deadline must be finite numeric")
    if observed_latency_ms < 0.0 or deadline_ms <= 0.0:
        raise ValueError("task outcome latency/deadline is invalid")
    if not result_received and terminal_status != "timed_out":
        raise ValueError("a missing task result must use terminal status timed_out")
    task_succeeded = result_received and terminal_status == "succeeded"
    return {
        "schema_version": APPLICATION_OUTCOME_SCHEMA_VERSION,
        "domain_id": correlation.domain_id,
        "topic": correlation.topic,
        "publisher_id": correlation.publisher_id,
        "source_sequence_number": correlation.source_sequence_number,
        "delivered": result_received,
        "deadline_met": result_received and observed_latency_ms <= deadline_ms,
        "observed_latency_ms": float(observed_latency_ms),
        "deadline_ms": float(deadline_ms),
        "task_kind": task_kind,
        "terminal_status": terminal_status,
        "task_succeeded": task_succeeded,
    }


def nav2_application_outcome(
    correlation: TaskOutcomeCorrelation,
    *,
    goal_status: int,
    observed_latency_ms: float,
    deadline_ms: float,
) -> dict[str, Any]:
    """Map action_msgs/GoalStatus terminal values for NavigateToPose."""

    if (
        not isinstance(goal_status, int)
        or isinstance(goal_status, bool)
        or goal_status not in NAV2_TERMINAL_STATUS
    ):
        raise ValueError("Nav2 goal status is not terminal")
    return build_task_application_outcome(
        correlation,
        task_kind="nav2",
        terminal_status=NAV2_TERMINAL_STATUS[goal_status],
        observed_latency_ms=observed_latency_ms,
        deadline_ms=deadline_ms,
    )


def rmf_application_outcome(
    correlation: TaskOutcomeCorrelation,
    *,
    response_received: bool,
    response_success: bool,
    observed_latency_ms: float,
    deadline_ms: float,
) -> dict[str, Any]:
    """Map an RMF SubmitTask-style terminal service response."""

    if not isinstance(response_received, bool) or not isinstance(
        response_success, bool
    ):
        raise ValueError("RMF response flags must be boolean")
    terminal_status = (
        "succeeded"
        if response_received and response_success
        else "rejected"
        if response_received
        else "timed_out"
    )
    return build_task_application_outcome(
        correlation,
        task_kind="rmf",
        terminal_status=terminal_status,
        observed_latency_ms=observed_latency_ms,
        deadline_ms=deadline_ms,
        result_received=response_received,
    )
