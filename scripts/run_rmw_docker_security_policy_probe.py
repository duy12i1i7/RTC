"""Build and run the FleetRMW opt-in security policy enforcement probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rmw_docker_allocation_probe import DEFAULT_IMAGE, parse_json_rows  # noqa: E402
from scripts.run_rmw_docker_shared_memory_probe import parse_last_json  # noqa: E402


SCHEMA_VERSION = "fleetrmw.docker_security_policy_probe.v1"
DEFAULT_POLICY = (
    "publish_allow=/fleetqox/security_allowed;"
    "publish_deny=/fleetqox/security_denied"
)


def security_policy_probe_ok(probe: dict[str, Any]) -> bool:
    return (
        probe.get("status") == "ok"
        and probe.get("policy_configured") is True
        and probe.get("allowed_taken") is True
        and probe.get("allowed_payload_ok") is True
        and int(probe.get("allowed_publish_returncode", -1)) == 0
        and int(probe.get("denied_publish_returncode", 0)) != 0
        and probe.get("denied_taken") is False
        and int(probe.get("security_policy_denied_delta", 0)) == 1
        and probe.get("fleetqox_security_policy_enforcement_claim") is True
        and probe.get("sros2_policy_enforcement_claim") is False
    )


def run_probe(
    *,
    root: Path,
    image: str,
    policy: str,
    iterations: int = 1,
) -> dict[str, Any]:
    run_count = max(iterations, 1)
    command = (
        "source /opt/ros/jazzy/setup.bash && "
        "rm -rf /tmp/fq-security-policy-build /tmp/fq-security-policy-install "
        "/tmp/fq-security-policy-log && "
        "colcon --log-base /tmp/fq-security-policy-log build --base-paths ros2_ws/src "
        "--packages-select rmw_fleetqox_cpp --build-base /tmp/fq-security-policy-build "
        "--install-base /tmp/fq-security-policy-install --cmake-args -DCMAKE_BUILD_TYPE=Release "
        ">/dev/null && source /tmp/fq-security-policy-install/setup.bash && "
        f"export FLEETQOX_RMW_SECURITY_POLICY={shlex.quote(policy)} && "
        f"for i in $(seq 1 {run_count}); do "
        "/tmp/fq-security-policy-install/rmw_fleetqox_cpp/lib/rmw_fleetqox_cpp/"
        "fleetrmw_security_policy_probe || exit $?; done"
    )
    completed = subprocess.run(
        [
            "docker", "run", "--rm", "--entrypoint", "bash",
            "-v", f"{root}:/work", "-w", "/work", image, "-lc", command,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    rows = parse_json_rows(completed.stdout)
    probe = rows[-1] if rows else parse_last_json(completed.stdout)
    ok_run_count = sum(1 for row in rows if security_policy_probe_ok(row))
    ok = (
        completed.returncode == 0
        and len(rows) == run_count
        and ok_run_count == run_count
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok" if ok else "failed",
        "image": image,
        "returncode": completed.returncode,
        "run_count": run_count,
        "ok_run_count": ok_run_count,
        "policy": policy,
        "policy_configured": bool(probe.get("policy_configured")),
        "fleetqox_security_policy_enforcement_claim": ok,
        "security_policy_enforcement_scope": "fleetqox_publish_allow_deny_env_policy",
        "security_policy_repeated_enforcement_claim": ok and run_count >= 5,
        "allowed_publish_returncode": probe.get("allowed_publish_returncode"),
        "allowed_taken": probe.get("allowed_taken"),
        "denied_publish_returncode": probe.get("denied_publish_returncode"),
        "denied_taken": probe.get("denied_taken"),
        "security_policy_denied_delta": probe.get("security_policy_denied_delta"),
        "sros2_policy_enforcement_claim": False,
        "production_security_hardening_claim": False,
        "probe": probe,
        "runs": rows,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--policy", default=DEFAULT_POLICY)
    parser.add_argument(
        "--summary-json",
        default="results_rmw_socket/docker_security_policy_probe_summary.json",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run_probe(
        root=ROOT,
        image=args.image,
        policy=args.policy,
        iterations=args.iterations,
    )
    output = ROOT / args.summary_json
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"status={summary['status']} ok_runs={summary['ok_run_count']}/"
            f"{summary['run_count']} denied_delta={summary.get('security_policy_denied_delta')}"
        )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
