import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fleetqox.udp_metrics import analyze_udp_trace


class UdpMetricsTest(unittest.TestCase):
    def test_analyze_udp_trace_counts_loss_and_deadline(self) -> None:
        with TemporaryDirectory() as tmpdir:
            trace = Path(tmpdir) / "trace.csv"
            received = Path(tmpdir) / "received.jsonl"
            trace.write_text(
                "event_id,timestamp_ms,policy,flow_id,flow_class,topic,robot_id,src,dst,"
                "action,bytes,original_bytes,degraded,deadline_ms,lifespan_ms,reliability,"
                "priority,semantic_utility,age_ms,link_capacity_bytes_per_tick,link_loss,"
                "link_jitter_ms,link_rtt_ms\n"
                "0,0,fifo,f0,control,/cmd,r0,a,b,send,100,100,False,10,20,reliable,0,1,0,0,0,0,0\n"
                "1,0,fifo,f1,state,/state,r0,a,b,send,100,100,False,100,200,reliable,0,2,0,0,0,0,0\n",
                encoding="utf-8",
            )
            received.write_text(
                json.dumps(
                    {
                        "policy": "fifo",
                        "bytes": 100,
                        "latency_ms": 15,
                        "deadline_ms": 10,
                        "flow_class": "control",
                        "semantic_utility": 1,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            records = analyze_udp_trace(trace, received)

        self.assertEqual(records[0]["tx"], 2)
        self.assertEqual(records[0]["rx"], 1)
        self.assertEqual(records[0]["lost"], 1)
        self.assertEqual(records[0]["control_starvation_events"], 1)


if __name__ == "__main__":
    unittest.main()
