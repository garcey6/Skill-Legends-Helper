"""Windowed (no-console) entry points must not crash when stdio is missing."""
from __future__ import annotations

import sys
import unittest

import agent


class EnsureStdStreamsTest(unittest.TestCase):
    def test_none_streams_are_replaced_with_writable_files(self) -> None:
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = None
        sys.stderr = None
        try:
            agent.ensure_std_streams()
            self.assertIsNotNone(sys.stdout)
            self.assertIsNotNone(sys.stderr)
            sys.stdout.write("ok\n")
            sys.stderr.write("ok\n")
            self.assertFalse(sys.stdout.closed)
        finally:
            new_out, new_err = sys.stdout, sys.stderr
            sys.stdout, sys.stderr = old_out, old_err
            for stream in (new_out, new_err):
                if stream is not None and not stream.closed:
                    stream.close()


if __name__ == "__main__":
    unittest.main()
