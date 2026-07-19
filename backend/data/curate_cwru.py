"""Build compact bearing replay episodes from official CWRU recordings.

The source files are not committed. Download the four official MATLAB files
listed in ``CWRU_PROVENANCE.md`` and pass their directory with ``--raw``.
Each output concatenates a healthy steady-state recording with one faulty
steady-state recording and computes 0.1-second vibration feature frames. This
tests ingestion, detection, schema-OOD handling, and the coarse ``bearing_wear``
family; it is not presented as a natural run-to-failure trajectory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.stats import kurtosis


SAMPLE_RATE = 12_000
FRAME = 1_200  # 0.1 second
HEALTHY_FRAMES = 70
FAULT_FRAMES = 80
EXPECTED_SHA256 = {
    "97.mat": "16bf48babcf1c7ac224bc1a81cd9eafdb27e42d5cf559761907e067e8eeadf3c",
    "105.mat": "f80b0ea04fd06b372a0eaec7c056543ea37e4bb4727a5b173d2a5bacd2aa9cab",
    "118.mat": "b00628f8dd8d1d930af77fa465d1e5cdb385fe259489053f91f3680bda7f640e",
    "130.mat": "35a095307d0971477049b343a1b5981dde465a58fb7f233ad89b035068c1717d",
}
FAULTS = {
    "105.mat": ("inner-race-007", "inner-race fault, 0.007 inch EDM defect"),
    "118.mat": ("ball-007", "ball fault, 0.007 inch EDM defect"),
    "130.mat": ("outer-race-007", "outer-race fault at 6 o'clock, 0.007 inch EDM defect"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def matlab_vector(path: Path) -> tuple[np.ndarray, float]:
    data = loadmat(path)
    vector_key = next(key for key in data if key.endswith("DE_time"))
    rpm_key = next(key for key in data if key.endswith("RPM"))
    return np.asarray(data[vector_key]).reshape(-1), float(data[rpm_key].reshape(-1)[0])


def frames(values: np.ndarray, rpm: float, n: int) -> list[dict[str, float]]:
    result = []
    for start in range(0, min(len(values), n * FRAME), FRAME):
        frame = values[start:start + FRAME]
        if len(frame) != FRAME:
            break
        rms = float(np.sqrt(np.mean(np.square(frame))))
        peak = float(np.max(np.abs(frame)))
        result.append({
            "vibration_rms_g": rms,
            "vibration_kurtosis": float(kurtosis(frame, fisher=False, bias=False)),
            "vibration_crest_factor": peak / rms if not math.isclose(rms, 0.0) else 0.0,
            "rpm": rpm,
        })
    return result


def curate(raw: Path, out: Path) -> None:
    for name, expected in EXPECTED_SHA256.items():
        actual = sha256(raw / name)
        if actual != expected:
            raise ValueError(f"checksum mismatch for {name}: {actual}")
    normal, normal_rpm = matlab_vector(raw / "97.mat")
    healthy = frames(normal, normal_rpm, HEALTHY_FRAMES)
    out.mkdir(parents=True, exist_ok=True)
    episodes = []
    for filename, (stem, detail) in FAULTS.items():
        faulty, rpm = matlab_vector(raw / filename)
        abnormal = frames(faulty, rpm, FAULT_FRAMES)
        output = out / f"cwru-{stem}.csv"
        with output.open("w", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["t_offset_s", *healthy[0].keys(), "label"],
            )
            writer.writeheader()
            for i, values in enumerate([*healthy, *abnormal]):
                writer.writerow({
                    "t_offset_s": round(i * 0.1, 1), **values,
                    "label": "" if i < len(healthy) else "bearing_wear",
                })
        episodes.append({
            "file": output.name, "fault": "bearing_wear",
            "fault_detail": detail, "rows": len(healthy) + len(abnormal),
            "labelled_rows": len(abnormal), "first_labelled_row": len(healthy),
            "source_files": ["97.mat", filename],
            "construction": "healthy and fault steady-state feature frames concatenated",
        })
    descriptor = {
        "dataset": "Case Western Reserve University Bearing Data Center",
        "url": "https://engineering.case.edu/bearingdatacenter/download-data-file",
        "license": "No explicit dataset license found on the official source pages",
        "description": "Real accelerometer recordings from a 2 hp motor bearing test stand; "
                       "single-point faults were introduced by EDM.",
        "use_restriction": "Research/evaluation only until redistribution and commercial terms are confirmed.",
        "signals": [
            {"key": "vibration_rms_g", "name": "Drive-end vibration RMS", "unit": "g"},
            {"key": "vibration_kurtosis", "name": "Vibration kurtosis", "unit": "ratio"},
            {"key": "vibration_crest_factor", "name": "Vibration crest factor", "unit": "ratio"},
            {"key": "rpm", "name": "Motor speed", "unit": "rpm"},
        ],
        "episodes": episodes,
    }
    (out / "cwru_bearing.json").write_text(json.dumps(descriptor, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--out", default=Path(__file__).parent / "episodes", type=Path)
    arguments = parser.parse_args()
    curate(arguments.raw, arguments.out)

