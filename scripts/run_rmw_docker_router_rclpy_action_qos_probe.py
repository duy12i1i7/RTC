"""Run fresh and expired router-mediated rclpy.action QoS rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.run_rmw_docker_router_rclpy_action_probe import (
        DEFAULT_ACTION,
        DEFAULT_IMAGE,
        run_probe,
    )
except ModuleNotFoundError:
    from run_rmw_docker_router_rclpy_action_probe import (
        DEFAULT_ACTION,
        DEFAULT_IMAGE,
        run_probe,
    )


SCHEMA_VERSION = "fleetrmw.rmw_docker_router_rclpy_action_qos_probe.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--action", default=DEFAULT_ACTION)
    parser.add_argument("--fresh-delay-ms", type=int, default=1)
    parser.add_argument("--fresh-lifespan-ms", type=int, default=100)
    parser.add_argument("--expired-delay-ms", type=int, default=30)
    parser.add_argument("--expired-lifespan-ms", type=int, default=5)
    parser.add_argument("--feedback-deadline-ms", type=int, default=5)
    parser.add_argument("--status-deadline-ms", type=int, default=100)
    parser.add_argument("--scheduler-window-ms", type=int, default=100)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_rmw_router_rclpy_action_qos_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    summary = run_matrix(
        root=root,
        image=args.image,
        action=args.action,
        fresh_delay_ms=args.fresh_delay_ms,
        fresh_lifespan_ms=args.fresh_lifespan_ms,
        expired_delay_ms=args.expired_delay_ms,
        expired_lifespan_ms=args.expired_lifespan_ms,
        feedback_deadline_ms=args.feedback_deadline_ms,
        status_deadline_ms=args.status_deadline_ms,
        scheduler_window_ms=args.scheduler_window_ms,
    )
    output = root / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("fleetrmw-router-rclpy-action-qos-probe")
        print(f"  status: {summary['status']}")
        for row in summary["rows"]:
            print(
                f"  {row['name']}: status={row['status']} "
                f"qos_dropped={row.get('router', {}).get('qos_dropped_frames')}"
            )
    return 0 if summary["status"] == "ok" else 1


def run_matrix(
    *,
    root: Path,
    image: str,
    action: str,
    fresh_delay_ms: int,
    fresh_lifespan_ms: int,
    expired_delay_ms: int,
    expired_lifespan_ms: int,
    feedback_deadline_ms: int,
    status_deadline_ms: int,
    scheduler_window_ms: int,
) -> dict[str, Any]:
    fresh = run_probe(
        root=root,
        image=image,
        action=action,
        forward_delay_ms=fresh_delay_ms,
        feedback_lifespan_ms=fresh_lifespan_ms,
        status_lifespan_ms=fresh_lifespan_ms,
        expect_observation_delivery=True,
        expected_qos_drops=0,
    )
    fresh["name"] = "fresh"

    expired = run_probe(
        root=root,
        image=image,
        action=action,
        forward_delay_ms=expired_delay_ms,
        feedback_lifespan_ms=expired_lifespan_ms,
        status_lifespan_ms=expired_lifespan_ms,
        expect_observation_delivery=False,
        expected_qos_drops=2,
    )
    expired["name"] = "expired_observation"

    feedback_topic = action + "/_action/feedback"
    status_topic = action + "/_action/status"
    dropped_by_topic = expired.get("router", {}).get("qos_dropped_topic_counts", {})
    expired["expected_drop_topics"] = [feedback_topic, status_topic]
    expired["drop_topics_verified"] = (
        dropped_by_topic.get(feedback_topic, 0) >= 1 and
        dropped_by_topic.get(status_topic, 0) >= 1
    )

    deadline_priority = run_probe(
        root=root,
        image=image,
        action=action,
        feedback_deadline_ms=feedback_deadline_ms,
        status_deadline_ms=status_deadline_ms,
        scheduler_window_ms=scheduler_window_ms,
        expected_data_frames=3,
        expect_observation_delivery=True,
        expected_qos_drops=0,
    )
    deadline_priority["name"] = "deadline_priority"
    forwarded_action_topics = [
        topic for topic in deadline_priority.get("router", {}).get("forwarded_topics", [])
        if topic.startswith(action + "/_action/")
    ]
    deadline_priority["forwarded_action_topics"] = forwarded_action_topics
    deadline_priority["deadline_order_verified"] = (
        len(forwarded_action_topics) >= 3 and
        forwarded_action_topics[0] == feedback_topic
    )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "pending",
        "action_name": action,
        "rows": [fresh, expired, deadline_priority],
    }
    summary["status"] = "ok" if (
        fresh.get("status") == "ok" and
        fresh.get("client", {}).get("feedback_callbacks") == ["success", "cancel"] and
        fresh.get("client", {}).get("status_observed") is True and
        expired.get("status") == "ok" and
        expired.get("client", {}).get("feedback_callbacks") == [] and
        expired.get("client", {}).get("status_observed") is False and
        expired.get("client", {}).get("success_result_status") == 4 and
        expired.get("client", {}).get("cancel_result_status") == 5 and
        expired["drop_topics_verified"] is True and
        deadline_priority.get("status") == "ok" and
        deadline_priority["deadline_order_verified"] is True
    ) else "failed"
    return summary


if __name__ == "__main__":
    raise SystemExit(main())
