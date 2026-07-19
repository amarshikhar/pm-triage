import asyncio

import pytest

from app.replay import replayer
from app.simulator import simulator, simulator_loop


@pytest.mark.asyncio
async def test_slow_triage_does_not_pause_telemetry_ticks(monkeypatch):
    ticks = 0
    triage_started = asyncio.Event()
    hold_triage = asyncio.Event()

    def simulation_tick():
        nonlocal ticks
        ticks += 1
        if ticks >= 2:
            simulator.running = False
        return [101] if ticks == 1 else []

    async def slow_triage(_anomaly_id):
        triage_started.set()
        await hold_triage.wait()

    monkeypatch.setattr(simulator, "tick", simulation_tick)
    monkeypatch.setattr(replayer, "tick", lambda: [])

    await asyncio.wait_for(simulator_loop(0.001, slow_triage), timeout=0.2)

    assert triage_started.is_set()
    assert ticks >= 2, "telemetry must keep ticking while triage waits on an LLM"
