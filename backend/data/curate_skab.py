"""Curate SKAB testbed recordings into replay episodes.

SKAB (Skoltech Anomaly Benchmark, https://github.com/waico/SKAB, GPL-3.0) is
real multivariate telemetry from a water-circulation pump testbed: each
experiment file carries per-row anomaly labels for a physically induced fault
(valve closures, rotor imbalance, cavitation). This script trims the raw
files to the app's canonical episode format; the outputs in episodes/ are
committed so the app never downloads anything at runtime.

Usage:
    python curate_skab.py --raw /path/to/raw-skab-csvs --out episodes/

Episode format (comma CSV): t_offset_s, <signal columns>, label
  label is "" on healthy rows and the episode's fault class on labelled rows.
The raw anomaly flag is the SKAB team's markup, not ours — curation only
renames columns and attaches the experiment's fault class to flagged rows.
"""

import argparse
import csv
import json
import statistics
from pathlib import Path

# canonical signal key -> (SKAB column, label, unit)
SIGNALS = {
    "vibration_g": ("Accelerometer1RMS", "Vibration accel RMS", "g"),
    "current_a": ("Current", "Motor current", "A"),
    "pressure_bar": ("Pressure", "Loop pressure", "bar"),
    "temp_motor_c": ("Temperature", "Motor body temp", "°C"),
    "temp_fluid_c": ("Thermocouple", "Fluid temp", "°C"),
    "flow_lpm": ("Volume Flow RateRMS", "Flow rate", "L/min"),
}

# raw file -> (episode name, fault class for labelled rows)
# Fault classes follow the SKAB experiment descriptions in data/README.md.
EPISODES = {
    "other_6.csv": ("imbalance-linear", "rotor_imbalance"),
    "other_13.csv": ("cavitation-two-phase", "cavitation"),
    "valve2_0.csv": ("discharge-restriction-a", "discharge_restriction"),
    "valve2_1.csv": ("discharge-restriction-b", "discharge_restriction"),
    "valve1_2.csv": ("suction-restriction", "suction_restriction"),
}


def curate(raw_dir: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    episode_meta = []
    for raw_name, (episode, fault) in EPISODES.items():
        rows = list(csv.DictReader((raw_dir / raw_name).open(), delimiter=";"))
        out_path = out_dir / f"skab-{episode}.csv"
        n_anom = 0
        with out_path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t_offset_s", *SIGNALS.keys(), "label"])
            for i, r in enumerate(rows):
                labelled = float(r.get("anomaly", 0)) >= 1
                n_anom += labelled
                w.writerow([i]
                           + [round(float(r[col]), 4) for col, _, _ in SIGNALS.values()]
                           + [fault if labelled else ""])
        first_anom = next((i for i, r in enumerate(rows) if float(r.get("anomaly", 0)) >= 1), None)
        episode_meta.append({
            "file": out_path.name, "fault": fault, "rows": len(rows),
            "labelled_rows": n_anom, "first_labelled_row": first_anom,
            "source_file": f"data/{raw_name.replace('_', '/', 1)}",
        })
        print(f"{out_path.name}: {len(rows)} rows, {n_anom} labelled ({fault})")

    descriptor = {
        "dataset": "SKAB v0.9 (Skoltech Anomaly Benchmark)",
        "url": "https://github.com/waico/SKAB",
        "license": "GPL-3.0",
        "description": "Real telemetry from a water-circulation pump testbed; "
                       "anomaly labels mark physically induced faults.",
        # "name" (not "label") for the display string: "label" is reserved for
        # evaluation ground truth, and the containment test bans it from any
        # agent-visible field.
        "signals": [{"key": k, "name": name, "unit": unit}
                    for k, (_, name, unit) in SIGNALS.items()],
        "episodes": episode_meta,
    }
    (out_dir / "skab_pump.json").write_text(json.dumps(descriptor, indent=2))
    print(f"wrote {out_dir / 'skab_pump.json'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--raw", required=True, type=Path)
    p.add_argument("--out", default=Path(__file__).parent / "episodes", type=Path)
    args = p.parse_args()
    curate(args.raw, args.out)
