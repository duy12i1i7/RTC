from __future__ import annotations

import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from urllib.parse import quote

from fleetqox.public_quic_gateway_backend import (
    BackendProtocolError,
    BackendRequest,
    PublicQuicGatewayBackend,
    PublicQuicGatewayBackendServer,
    encode_backend_request,
    read_backend_request,
    read_backend_response,
)
from fleetqox.quic_gateway_state import DATA_FRAME_MAGIC, FleetQoxGatewayState


def frame(sequence: int, publisher_id: str = "stateful-gateway-publisher") -> bytes:
    payload = f"payload-{sequence}".encode()
    document = {
        "schema_version": "fleetrmw.data_frame.v1",
        "kind": "sidecar_packet_frame",
        "domain_id": 42,
        "route": {
            "robot_id": "robot-1",
            "topic": "/fleetqox/gateway",
        },
        "sample_envelope": {
            "robot_id": "robot-1",
            "topic": "/fleetqox/gateway",
            "publisher_id": publisher_id,
            "source_sequence_number": sequence,
            "source_timestamp_ns": sequence * 1000,
        },
        "serialized_payload": {
            "encoding": "hex",
            "size": len(payload),
            "data": payload.hex(),
        },
    }
    return DATA_FRAME_MAGIC + json.dumps(
        document, separators=(",", ":")
    ).encode()


class PublicQuicGatewayBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = FleetQoxGatewayState(max_frames_per_topic=4)
        self.backend = PublicQuicGatewayBackend(self.state)
        topic = quote("/fleetqox/gateway", safe="")
        self.path = (
            f"/fleetrmw/v1/frames?domain_id=42&topic={topic}"
            "&consumer_id=alpha"
        )

    def tearDown(self) -> None:
        self.state.close()

    def test_local_protocol_round_trips_binary_request(self) -> None:
        request = BackendRequest(
            method="POST",
            path=self.path,
            client_identity="stateful-gateway-publisher",
            body=frame(1),
        )
        encoded = encode_backend_request(request)
        self.assertEqual(read_backend_request(io.BytesIO(encoded)), request)
        with self.assertRaises(BackendProtocolError):
            read_backend_request(io.BytesIO(encoded[:-1]))

    def test_verified_identity_is_bound_before_state_mutation(self) -> None:
        accepted = self.backend.dispatch(
            BackendRequest(
                "POST",
                self.path,
                "stateful-gateway-publisher",
                frame(1),
            )
        )
        impersonated = self.backend.dispatch(
            BackendRequest(
                "POST",
                self.path,
                "different-publisher",
                frame(2),
            )
        )
        missing = self.backend.dispatch(
            BackendRequest("POST", self.path, "", frame(3))
        )
        self.assertEqual(accepted.status, 200)
        self.assertEqual(impersonated.status, 403)
        self.assertEqual(missing.status, 401)
        snapshot = self.state.snapshot()
        self.assertEqual(snapshot["accepted_frames"], 1)
        self.assertEqual(snapshot["retained_frames"], 1)
        self.assertEqual(self.backend.identity_rejections, 2)

    def test_unix_server_dispatches_shared_state_engine(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            socket_path = Path(temp) / "backend.sock"
            server = PublicQuicGatewayBackendServer(socket_path, self.backend)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            deadline = time.monotonic() + 2.0
            while not socket_path.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.connect(str(socket_path))
                    client.sendall(
                        encode_backend_request(
                            BackendRequest(
                                "POST",
                                self.path,
                                "stateful-gateway-publisher",
                                frame(1),
                            )
                        )
                    )
                    response = read_backend_response(
                        client.makefile("rb", buffering=0)
                    )
                self.assertEqual(response.status, 200)
                self.assertEqual(self.state.snapshot()["accepted_frames"], 1)
                self.assertEqual(socket_path.stat().st_mode & 0o777, 0o600)
            finally:
                server.stop()
                thread.join(timeout=2.0)
            self.assertFalse(thread.is_alive())
            self.assertFalse(socket_path.exists())


if __name__ == "__main__":
    unittest.main()
