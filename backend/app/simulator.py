"""Simulated IoT telemetry feed.

Generates readings per machine on a fixed tick. Fault patterns ramp a metric
away from baseline over several ticks, so detection sees realistic trends
instead of single-point noise. Faults start randomly (seeded) or on demand
via POST /api/simulate/inject — the live-demo lever.

Machines with source="replay" are fed real recorded data by app.replay, not
by this module.
"""

import asyncio
import json
import os
import random

from .db import SessionLocal
from .detector import run_detection
from .models import Machine, TelemetryReading, utcnow

# type -> metric -> (baseline mean, noise sigma)
BASELINES = {
    "cnc_mill":   {"temperature_c": (55, 1.2), "vibration_mm_s": (2.5, 0.25), "pressure_kpa": (300, 5), "rpm": (8000, 60)},
    "compressor": {"temperature_c": (70, 1.5), "vibration_mm_s": (3.0, 0.3),  "pressure_kpa": (720, 8), "rpm": (1500, 12)},
    "pump":       {"temperature_c": (60, 1.2), "vibration_mm_s": (2.8, 0.25), "pressure_kpa": (400, 6), "rpm": (2900, 20)},
    "conveyor":   {"temperature_c": (45, 1.0), "vibration_mm_s": (2.0, 0.2),  "pressure_kpa": (101, 1), "rpm": (60, 1)},
}

# Signal roster for simulated machine types (seeded onto Machine.signals_json).
SIM_SIGNALS = [
    {"key": "temperature_c", "name": "Temperature", "unit": "°C"},
    {"key": "vibration_mm_s", "name": "Vibration velocity RMS", "unit": "mm/s"},
    {"key": "pressure_kpa", "name": "Pressure", "unit": "kPa"},
    {"key": "rpm", "name": "Shaft speed", "unit": "rpm"},
]

# Absolute engineering limits per simulated type (seeded onto Machine.limits_json).
# type -> metric -> (limit, direction)  direction +1 = too high, -1 = too low
SIM_LIMITS = {
    "cnc_mill":   {"temperature_c": (78, 1), "vibration_mm_s": (5.5, 1)},
    "compressor": {"temperature_c": (92, 1), "vibration_mm_s": (6.5, 1), "pressure_kpa": (640, -1)},
    "pump":       {"temperature_c": (82, 1), "vibration_mm_s": (6.0, 1), "pressure_kpa": (330, -1)},
    "conveyor":   {"temperature_c": (80, 1), "vibration_mm_s": (5.0, 1)},
}

# fault -> (metric, per-tick drift, direction)
FAULTS = {
    "bearing_wear":  ("vibration_mm_s", 0.35, +1),
    "overheat":      ("temperature_c", 2.2, +1),
    "pressure_loss": ("pressure_kpa", -9.0, +1),
    "cavitation":    ("vibration_mm_s", 0.5, +1),  # plus pressure oscillation, see below
}


class FleetSimulator:
    def __init__(self, seed: int = 42, spontaneous_fault_prob: float = 0.012):
        self.rng = random.Random(seed)
        self.active_faults: dict[str, dict] = {}  # machine_id -> {fault, ticks}
        self.spontaneous_fault_prob = spontaneous_fault_prob
        self.running = False

    def inject_fault(self, machine_id: str, fault: str):
        if fault not in FAULTS:
            raise ValueError(f"unknown fault '{fault}', options: {sorted(FAULTS)}")
        self.active_faults[machine_id] = {"fault": fault, "ticks": 0}

    def clear_fault(self, machine_id: str):
        self.active_faults.pop(machine_id, None)

    def _reading_for(self, machine: Machine) -> dict:
        base = BASELINES[machine.type]
        values = {m: self.rng.gauss(mu, sigma) for m, (mu, sigma) in base.items()}

        state = self.active_faults.get(machine.id)
        if state:
            fault = state["fault"]
            state["ticks"] += 1
            metric, drift, _ = FAULTS[fault]
            values[metric] += drift * state["ticks"]
            if fault == "cavitation":
                values["pressure_kpa"] += self.rng.choice([-1, 1]) * self.rng.uniform(20, 45)
            if fault == "bearing_wear":
                values["temperature_c"] += 0.4 * state["ticks"]  # friction heat rides along
            # a fault eventually plateaus so values stay physically plausible
            if state["ticks"] > 25:
                state["ticks"] = 25
        return {
            "temperature_c": round(values["temperature_c"], 2),
            "vibration_mm_s": round(max(0.0, values["vibration_mm_s"]), 2),
            "pressure_kpa": round(values["pressure_kpa"], 1),
            "rpm": round(values["rpm"], 1),
        }

    def tick(self) -> list[int]:
        """One simulation step. Returns ids of anomalies created by detection."""
        created: list[int] = []
        db = SessionLocal()
        try:
            machines = db.query(Machine).filter(Machine.source == "simulated").all()
            now = utcnow().isoformat()
            for m in machines:
                if m.id not in self.active_faults and self.rng.random() < self.spontaneous_fault_prob:
                    self.inject_fault(m.id, self.rng.choice(list(FAULTS)))
                reading = TelemetryReading(
                    machine_id=m.id, ts=now,
                    values_json=json.dumps(self._reading_for(m)),
                )
                db.add(reading)
                db.commit()
                state = self.active_faults.get(m.id)
                created += run_detection(db, m, reading,
                                         ground_truth_fault=state["fault"] if state else None)
        finally:
            db.close()
        return created


simulator = FleetSimulator(
    spontaneous_fault_prob=float(os.getenv("SPONTANEOUS_FAULT_PROB", "0.012"))
)


async def simulator_loop(interval_s: float, on_anomaly):
    from .replay import replayer  # late import; replay also imports models

    simulator.running = True
    while simulator.running:
        try:
            anomaly_ids = await asyncio.to_thread(simulator.tick)
            anomaly_ids += await asyncio.to_thread(replayer.tick)
            for aid in anomaly_ids:
                await on_anomaly(aid)
        except Exception as e:  # keep the feed alive; a dead simulator kills the demo
            print(f"[simulator] tick failed: {e}")
        await asyncio.sleep(interval_s)
