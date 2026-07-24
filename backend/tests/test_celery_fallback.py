"""
Tests for the Celery enqueue fallback — analysis jobs must keep running
even when Redis (the Celery broker) is over its memory/connection limit.

Regression coverage for: uploads getting silently stuck at "PROCESSING"
forever when Redis rejects the broker publish (e.g. OOM / connection
limit exceeded) inside a FastAPI BackgroundTask, after the response has
already been sent to the client.
"""

import threading
import pytest

from tasks.analysis_tasks import _CeleryTaskWithFallback


class _FakeBrokenCeleryTask:
    """Simulates a Celery task whose broker (Redis) is over its limit."""

    def delay(self, *args, **kwargs):
        raise ConnectionError(
            "OOM command not allowed when used memory > 'maxmemory'."
        )


class _FakeHealthyCeleryTask:
    def __init__(self):
        self.calls = []

    def delay(self, *args, **kwargs):
        self.calls.append(args)
        return "fake-async-result"


class TestCeleryTaskWithFallback:
    def test_delay_does_not_raise_when_broker_fails(self):
        calls = []
        done = threading.Event()

        def fake_analysis(record_id, filename):
            calls.append((record_id, filename))
            done.set()

        task = _CeleryTaskWithFallback(_FakeBrokenCeleryTask(), fake_analysis)

        # Should NOT raise, even though the underlying broker call fails.
        task.delay(42, "meeting.wav")

        assert done.wait(timeout=2), "fallback thread never ran the analysis function"
        assert calls == [(42, "meeting.wav")]

    def test_delay_uses_broker_when_healthy(self):
        healthy_task = _FakeHealthyCeleryTask()

        def fake_analysis(*args, **kwargs):
            pytest.fail("should not run the fallback when the broker succeeds")

        task = _CeleryTaskWithFallback(healthy_task, fake_analysis)
        result = task.delay(1, "x.wav")

        assert result == "fake-async-result"
        assert healthy_task.calls == [(1, "x.wav")]

    def test_direct_call_bypasses_broker_entirely(self):
        """__call__ should run the function directly (used by sync callers)."""
        task = _CeleryTaskWithFallback(_FakeBrokenCeleryTask(), lambda x: x * 2)
        assert task(21) == 42
