import io
import unittest

from scripts.feed_sidecar_closed_loop import read_json_response


class FeedSidecarClosedLoopTest(unittest.TestCase):
    def test_read_json_response_decodes_line(self) -> None:
        response, reason = read_json_response(io.BytesIO(b'{"status":"ok"}\n'))

        self.assertEqual(reason, "completed")
        self.assertEqual(response, {"status": "ok"})

    def test_read_json_response_handles_timeout(self) -> None:
        response, reason = read_json_response(_TimeoutReader())

        self.assertIsNone(response)
        self.assertEqual(reason, "response_timeout")

    def test_read_json_response_handles_closed_connection(self) -> None:
        response, reason = read_json_response(io.BytesIO(b""))

        self.assertIsNone(response)
        self.assertEqual(reason, "connection_closed")


class _TimeoutReader:
    def readline(self) -> bytes:
        raise TimeoutError("timed out")


if __name__ == "__main__":
    unittest.main()
