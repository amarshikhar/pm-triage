"""Replay real recorded telemetry through the live pipeline.

Machines with source="replay" stream curated episodes of a real dataset
(see data/episodes/) one row per tick, through the same detector and agent as
the simulated fleet. The episode's per-row label — the dataset authors'
anomaly markup, not ours — rides along as ground truth for evaluation, exactly
like the simulator's injected-fault label. Detection never reads it.

Demo lever: replaying an 18-minute recording in real time is a long wait for a
fault, so `jump_to_fault` moves the cursor to shortly before the labelled
window of a chosen episode — enough healthy lead-in remains to rebuild the
detector's rolling baseline honestly before the excursion arrives.
"""

import csv
import json
from pathlib import Path

from .db import SessionLocal
from .detector import WINDOW
from .models import Machine, TelemetryReading, utcnow

EPISODES_DIR = Path(__file__).resolve().parent.parent / "data" / "episodes"

# Healthy rows to keep ahead of the labelled window when jumping: the full
# detector baseline plus a margin, so the z-rule's history is real pre-fault
# data and not a discontinuity of our making.
JUMP_LEAD_ROWS = WINDOW + 15


class Episode:
    def __init__(self, path: Path, fault: str):
        self.name = path.stem
        self.fault = fault
        self.rows: list[tuple[dict, str | None]] = []
        with path.open() as f:
            for r in csv.DictReader(f):
                label = r.pop("label") or None
                r.pop("t_offset_s", None)
                self.rows.append(({k: float(v) for k, v in r.items()}, label))
        self.first_labelled = next(
            (i for i, (_, lab) in enumerate(self.rows) if lab), None)


class DatasetReplayer:
    """Feeds every source="replay" machine from its curated episode set."""

    def __init__(self, episodes_dir: Path = EPISODES_DIR):
        self.episodes_dir = episodes_dir
        self._sets: dict[str, list[Episode]] = {}   # descriptor stem -> episodes
        self._state: dict[str, dict] = {}           # machine_id -> {set, ep, row}

    def _load_set(self, descriptor: str) -> list[Episode]:
        if descriptor not in self._sets:
            meta = json.loads((self.episodes_dir / f"{descriptor}.json").read_text())
            self._sets[descriptor] = [
                Episode(self.episodes_dir / ep["file"], ep["fault"])
                for ep in meta["episodes"]
            ]
        return self._sets[descriptor]

    def _state_for(self, machine: Machine) -> dict | None:
        if machine.id not in self._state:
            descriptor = json.loads(machine.dataset_json or "{}").get("episode_set")
            if not descriptor:
                return None
            # warmup: readings to stream before detection re-arms. Every episode
            # is a separate physical run at its own operating point, so at any
            # boundary (start, jump, rollover) the detector's rolling baseline
            # still holds the previous run — the z-rule would fire on the regime
            # change itself. Suppress detection until the window refills with
            # same-run data; the discontinuity is ours, not the machine's.
            self._state[machine.id] = {"set": descriptor, "ep": 0, "row": 0,
                                       "warmup": WINDOW}
        return self._state[machine.id]

    def active_fault(self, machine_id: str) -> str | None:
        """The label under the cursor right now (drives the UI fault pill)."""
        st = self._state.get(machine_id)
        if not st:
            return None
        episodes = self._sets.get(st["set"])
        if not episodes:
            return None
        _, label = episodes[st["ep"]].rows[st["row"] - 1 if st["row"] else 0]
        return label

    def available_faults(self, machine: Machine) -> list[str]:
        st = self._state_for(machine)
        if not st:
            return []
        return sorted({ep.fault for ep in self._load_set(st["set"])})

    def available_episodes(self, machine: Machine) -> list[dict[str, str]]:
        """Every physical recording, including repeated fault classes."""
        st = self._state_for(machine)
        if not st:
            return []
        return [{"name": ep.name, "fault": ep.fault}
                for ep in self._load_set(st["set"])]

    def jump_to_episode(self, machine: Machine, episode_name: str) -> str:
        """Cue one exact recording rather than the first recording of a class."""
        st = self._state_for(machine)
        if not st:
            raise ValueError(f"{machine.id} is not a replay machine")
        episodes = self._load_set(st["set"])
        idx = next((i for i, ep in enumerate(episodes) if ep.name == episode_name), None)
        if idx is None:
            raise ValueError(
                f"no episode '{episode_name}', options: {[ep.name for ep in episodes]}")
        ep = episodes[idx]
        st["ep"] = idx
        st["row"] = max(0, (ep.first_labelled or 0) - JUMP_LEAD_ROWS)
        st["warmup"] = WINDOW
        return ep.name

    def jump_to_fault(self, machine: Machine, fault: str) -> str:
        """Demo lever: cue up the episode for `fault` just before its labelled
        window. Returns the episode name. Raises ValueError on unknown fault."""
        st = self._state_for(machine)
        if not st:
            raise ValueError(f"{machine.id} is not a replay machine")
        episodes = self._load_set(st["set"])
        candidates = [i for i, ep in enumerate(episodes) if ep.fault == fault]
        if not candidates:
            raise ValueError(
                f"no episode with fault '{fault}', options: "
                f"{sorted({ep.fault for ep in episodes})}")
        return self.jump_to_episode(machine, episodes[candidates[0]].name)

    def tick(self) -> list[int]:
        """Advance every replay machine one row; returns new anomaly ids."""
        from .detector import run_detection

        created: list[int] = []
        db = SessionLocal()
        try:
            machines = db.query(Machine).filter(Machine.source == "replay").all()
            now = utcnow().isoformat()
            for m in machines:
                st = self._state_for(m)
                if not st:
                    continue
                episodes = self._load_set(st["set"])
                ep = episodes[st["ep"]]
                values, label = ep.rows[st["row"]]
                st["row"] += 1
                if st["row"] >= len(ep.rows):        # episode over: next one
                    st["ep"] = (st["ep"] + 1) % len(episodes)
                    st["row"] = 0
                    st["warmup"] = WINDOW
                reading = TelemetryReading(
                    machine_id=m.id, ts=now, values_json=json.dumps(values))
                db.add(reading)
                db.commit()
                if st["warmup"] > 0:
                    st["warmup"] -= 1
                    continue
                created += run_detection(db, m, reading, ground_truth_fault=label)
        finally:
            db.close()
        return created


replayer = DatasetReplayer()
