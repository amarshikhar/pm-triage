"""Seed the fleet catalog and the historical maintenance-log 'legacy CMMS'."""

import json
from pathlib import Path

from sqlalchemy.orm import Session

# Import registers the CMMS work-order table on the shared metadata so that
# every Base.metadata.create_all() site (app startup, tests, the eval harness)
# creates it without each having to know the CMMS module exists.
from .cmms.models import CmmsWorkOrder  # noqa: F401
from .models import Machine, MaintenanceLog
from .simulator import SIM_LIMITS, SIM_SIGNALS

EPISODES_DIR = Path(__file__).resolve().parent.parent / "data" / "episodes"

# (id, name, type, location, criticality 1..5, hourly_downtime_cost USD)
# Cost is a business input, not a guess in code: a line-down asset (CNV-01, the
# main conveyor; CMP-01, the plant air supply) costs thousands per idle hour,
# while a standby unit costs little. It turns P1..P4 into money on the case.
MACHINES = [
    ("CNC-01", "CNC Mill 01 (Line A)", "cnc_mill", "Hall 1 / Line A", 4, 1800),
    ("CNC-02", "CNC Mill 02 (Line A)", "cnc_mill", "Hall 1 / Line A", 3, 1200),
    ("CMP-01", "Air Compressor 01", "compressor", "Utility Room", 5, 3500),
    ("CMP-02", "Air Compressor 02 (standby)", "compressor", "Utility Room", 2, 400),
    ("PMP-01", "Coolant Pump 01", "pump", "Hall 1 / Line A", 4, 1600),
    ("PMP-02", "Hydraulic Pump 02", "pump", "Hall 2 / Line B", 3, 1100),
    ("CNV-01", "Main Conveyor (Line B)", "conveyor", "Hall 2 / Line B", 5, 4000),
    ("CNV-02", "Packing Conveyor", "conveyor", "Packing Area", 2, 600),
]

# (id, machine_id, machine_type, date, failure_mode, symptoms, root_cause, action, downtime_h, safety)
LOGS = [
    ("WO-1001", "CNC-01", "cnc_mill", "2025-03-02", "spindle bearing wear",
     "vibration rising over several shifts, from 2.8 to 6.5 mm/s; audible whine at high rpm",
     "worn spindle bearing (DE side), grease breakdown",
     "replaced spindle bearing set, regreased, laser alignment check", 9.5, 0),
    ("WO-1002", "CNC-01", "cnc_mill", "2025-06-14", "coolant flow restriction",
     "spindle temperature climbing above 78C during heavy cuts; coolant pressure slightly low",
     "clogged coolant filter reduced flow to spindle jacket",
     "replaced coolant filter, flushed lines", 2.0, 0),
    ("WO-1003", "CNC-02", "cnc_mill", "2025-01-21", "tool holder imbalance",
     "sudden vibration spike to 8 mm/s after tool change; surface finish defects",
     "unbalanced tool holder assembly after incorrect tool seating",
     "re-seated and balanced tool holder, operator retraining", 1.5, 0),
    ("WO-1004", "CMP-01", "compressor", "2025-02-11", "discharge valve leak",
     "discharge pressure sagging from 750 to 640 kPa; longer load cycles; head temperature high",
     "worn discharge valve plates leaking back into cylinder",
     "replaced valve plate kit, checked unloader", 6.0, 0),
    ("WO-1005", "CMP-01", "compressor", "2024-11-30", "cooling fan failure",
     "head temperature spiked above 95C within one shift; thermal trip",
     "seized cooling fan motor bearing",
     "replaced fan motor, cleaned intercooler fins", 4.0, 1),
    ("WO-1006", "CMP-02", "compressor", "2025-04-05", "air intake filter clogging",
     "gradual pressure drop and higher duty cycle over two weeks",
     "clogged intake filter in dusty season",
     "replaced intake filter, added weekly inspection", 1.0, 0),
    ("WO-1007", "PMP-01", "pump", "2025-05-19", "cavitation",
     "erratic pressure oscillation, vibration up to 7 mm/s, gravel-like noise",
     "suction strainer partially blocked causing cavitation",
     "cleaned strainer, verified NPSH margin", 3.0, 0),
    ("WO-1008", "PMP-01", "pump", "2024-12-08", "mechanical seal failure",
     "coolant leak at shaft, temperature rise, pressure loss",
     "mechanical seal worn out past service life",
     "replaced mechanical seal, set up seal replacement schedule", 5.0, 1),
    ("WO-1009", "PMP-02", "pump", "2025-03-27", "bearing lubrication starvation",
     "bearing housing temperature above 85C, vibration trending up",
     "auto-luber cartridge empty for ~3 weeks",
     "replaced bearing, refilled auto-luber, added level check to rounds", 7.0, 0),
    ("WO-1010", "CNV-01", "conveyor", "2025-02-25", "belt misalignment",
     "belt tracking off-center, motor current and gearbox vibration elevated",
     "idler roller seized, dragging belt sideways",
     "replaced idler roller, re-tracked belt", 3.5, 1),
    ("WO-1011", "CNV-01", "conveyor", "2024-10-12", "gearbox overheating",
     "gearbox temperature above 90C, oil smell",
     "low gearbox oil due to slow leak at output seal",
     "replaced seal, refilled oil, monthly oil level check", 6.5, 0),
    ("WO-1012", "CNV-02", "conveyor", "2025-06-01", "drive chain wear",
     "speed hunting under load, vibration and noise at drive end",
     "elongated drive chain past wear limit",
     "replaced chain and sprockets", 2.5, 0),
    ("WO-1013", "CNC-02", "cnc_mill", "2025-07-02", "spindle bearing wear",
     "vibration trending 3 -> 5.9 mm/s over a week, temperature slightly elevated",
     "early-stage spindle bearing wear confirmed by vibration spectrum",
     "scheduled bearing replacement in planned window, avoided line stop", 0.0, 0),
    ("WO-1014", "CMP-01", "compressor", "2025-06-20", "unloader valve sticking",
     "pressure oscillating between 600 and 780 kPa, frequent load/unload cycling",
     "sticking unloader valve due to carbon buildup",
     "cleaned unloader, changed oil grade", 2.0, 0),
    ("WO-1015", "PMP-02", "pump", "2025-01-15", "impeller erosion",
     "gradual head loss over months, mild vibration increase",
     "impeller erosion from abrasive particles",
     "replaced impeller, installed better filtration", 8.0, 0),
    # PMP-03 — the circulation pump on the test loop (real SKAB telemetry).
    ("WO-1016", "PMP-03", "pump", "2025-04-14", "suction line restriction",
     "flow rate sagging below setpoint, motor body temperature slightly down as load fell; "
     "no vibration change",
     "inlet-side valve found partially closed after maintenance on the loop, starving suction",
     "reopened and lock-tagged inlet valve, added valve-position check to lineup sheet", 1.5, 0),
    ("WO-1017", "PMP-03", "pump", "2025-02-03", "discharge flow restriction",
     "flow rate stepped down several L/min while pressure held; motor current eased off",
     "outlet valve throttled against procedure, pump running back on its curve",
     "restored valve lineup, briefed operators on throttling risk", 1.0, 0),
    ("WO-1018", "PMP-03", "pump", "2024-12-19", "rotor imbalance",
     "vibration acceleration climbing steadily to nearly 3x baseline within minutes, "
     "flow and pressure unaffected",
     "imbalance mass on the rotor (blade fouling); confirmed by runout check",
     "cleaned and rebalanced rotor, verified vibration back at baseline", 4.0, 0),
    ("WO-1019", "PMP-03", "pump", "2025-05-30", "cavitation",
     "flow rate oscillating wildly with gravel-like noise, vibration slightly elevated; "
     "pressure jittery",
     "air entrained at pump inlet (two-phase flow) causing cavitation",
     "vented loop, fixed suction-side air ingress, verified NPSH margin", 3.0, 0),
    # --- corpus noise (record_type="routine", appended as 11th element) ------
    # A real CMMS is mostly NOT failure forensics: preventive routes, calibra-
    # tions, inspections that found nothing, false alarms. These entries share
    # vocabulary with the fault classes (vibration, pressure, valve, filter)
    # without carrying their signatures, so retrieval has to rank, not just
    # match — and citing one of these for a live fault is a scored miss.
    ("WO-1020", "CNC-01", "cnc_mill", "2025-05-06", "preventive maintenance",
     "quarterly PM route: lubrication, filter set, backlash check — no defects noted",
     "n/a — scheduled preventive work, machine healthy",
     "completed PM checklist, replaced consumables on schedule", 0.0, 0, "routine"),
    ("WO-1021", "CMP-02", "compressor", "2025-03-18", "instrument recalibration",
     "discharge pressure transmitter reading 15 kPa high against test gauge",
     "transmitter drift beyond tolerance — process pressure itself was normal",
     "recalibrated transmitter, logged as-found/as-left values", 0.0, 0, "routine"),
    ("WO-1022", "PMP-01", "pump", "2025-06-27", "false vibration alarm",
     "vibration alert from online monitor; readings normal on handheld meter",
     "accelerometer mounting stud loose — instrumentation fault, pump healthy",
     "re-torqued sensor mount, verified against handheld baseline", 0.0, 0, "routine"),
    ("WO-1023", "CNV-02", "conveyor", "2025-04-22", "safety interlock replacement",
     "pull-cord interlock intermittently failing to latch during weekly test",
     "worn interlock mechanism past cycle life",
     "replaced interlock switch, function-tested E-stop chain", 0.5, 1, "routine"),
    ("WO-1024", "CMP-01", "compressor", "2025-01-09", "scheduled valve inspection",
     "borescope inspection of suction/discharge valves per OEM interval",
     "n/a — no defect found, wear within limits",
     "documented valve condition, next inspection scheduled", 0.0, 0, "routine"),
    ("WO-1025", "PMP-02", "pump", "2025-02-14", "motor insulation test",
     "annual megger test of pump motor windings",
     "n/a — insulation resistance well above minimum",
     "recorded readings, returned to service", 0.0, 0, "routine"),
    ("WO-1026", "CNC-02", "cnc_mill", "2025-04-30", "way lube service",
     "way lubrication pressure warning lamp during rapid moves",
     "way lube reservoir low and inline filter partially clogged",
     "topped up reservoir, replaced lube filter, cycled axes", 0.5, 0, "routine"),
    ("WO-1027", "CNV-01", "conveyor", "2025-05-11", "planned belt replacement",
     "belt at end of scheduled service life; surface cracking on inspection",
     "n/a — planned wear-out replacement in maintenance window",
     "replaced belt in planned window, aligned and tensioned", 0.0, 0, "routine"),
    ("WO-1028", "PMP-03", "pump", "2025-03-08", "coupling alignment check",
     "laser alignment verification after drive motor swap on the test loop",
     "n/a — alignment within tolerance after correction shims",
     "shimmed motor feet, recorded final alignment figures", 1.0, 0, "routine"),
    ("WO-1029", "CMP-01", "compressor", "2025-05-24", "condensate drain service",
     "aftercooler drain trap passing air continuously",
     "drain trap float worn, venting compressed air to atmosphere",
     "rebuilt drain trap, verified cycling", 0.5, 0, "routine"),
    ("WO-1030", "CNC-01", "cnc_mill", "2025-02-19", "spindle chiller service",
     "chiller low-refrigerant warning; spindle temperatures still in range",
     "slow refrigerant leak at service valve",
     "repaired valve, recharged circuit, verified cooling capacity", 1.0, 0, "routine"),
    ("WO-1031", "PMP-01", "pump", "2025-04-03", "packing gland adjustment",
     "slightly elevated drip rate at stuffing box, within pump spec but trending",
     "packing bedding in after last repack",
     "adjusted gland nuts evenly, drip rate back to spec", 0.0, 0, "routine"),
    ("WO-1032", "BRG-01", "motor", "2025-02-18", "bearing defect",
     "drive-end vibration RMS and impulsiveness rose sharply while motor speed held",
     "localized rolling-element bearing damage confirmed by vibration spectrum",
     "isolated motor, replaced drive-end bearing, aligned and baseline-tested", 3.0, 0),
]


def _skab_machine() -> Machine | None:
    """The real-data machine: a pump whose telemetry replays SKAB testbed
    recordings (see data/episodes/). Signal roster and provenance come from
    the curated descriptor so catalog and data cannot drift apart."""
    descriptor_path = EPISODES_DIR / "skab_pump.json"
    if not descriptor_path.exists():
        return None
    meta = json.loads(descriptor_path.read_text())
    return Machine(
        id="PMP-03", name="Circulation Pump (SKAB testbed)", type="pump",
        location="Test Loop / Skid 1", criticality=3, hourly_downtime_cost=900,
        source="replay",
        signals_json=json.dumps(meta["signals"]),
        limits_json="{}",  # operating point varies run to run; the z-rule detects
        dataset_json=json.dumps({
            "episode_set": "skab_pump",
            "dataset": meta["dataset"], "url": meta["url"],
            "license": meta["license"], "description": meta["description"],
        }),
    )


def _cwru_machine() -> Machine | None:
    """Independent bearing-testbed replay used for cross-domain evaluation."""
    descriptor_path = EPISODES_DIR / "cwru_bearing.json"
    if not descriptor_path.exists():
        return None
    meta = json.loads(descriptor_path.read_text())
    return Machine(
        id="BRG-01", name="Motor Bearing Rig (CWRU testbed)", type="motor",
        location="Independent Bearing Test Stand", criticality=2,
        hourly_downtime_cost=500, source="replay",
        signals_json=json.dumps(meta["signals"]), limits_json="{}",
        dataset_json=json.dumps({
            "episode_set": "cwru_bearing", "dataset": meta["dataset"],
            "url": meta["url"], "license": meta["license"],
            "description": meta["description"],
            "use_restriction": meta.get("use_restriction"),
        }),
    )


def seed_if_empty(db: Session) -> bool:
    """Add missing reference rows without replacing operational/user data.

    The original demo seeded only when the whole machine table was empty. That
    meant a newly shipped replay testbed never appeared in an established
    Supabase database. This additive form is safe on every startup: primary keys
    make it idempotent, and existing rows are never overwritten.
    """
    changed = False
    for mid, name, mtype, loc, crit, cost in MACHINES:
        if db.get(Machine, mid) is None:
            db.add(Machine(id=mid, name=name, type=mtype, location=loc, criticality=crit,
                           hourly_downtime_cost=cost,
                           source="simulated",
                           signals_json=json.dumps(SIM_SIGNALS),
                           limits_json=json.dumps(SIM_LIMITS.get(mtype, {}))))
            changed = True
    for replay_machine in (_skab_machine(), _cwru_machine()):
        if replay_machine and db.get(Machine, replay_machine.id) is None:
            db.add(replay_machine)
            changed = True
    for row in LOGS:
        if db.get(MaintenanceLog, row[0]) is None:
            db.add(
                MaintenanceLog(
                    id=row[0], machine_id=row[1], machine_type=row[2], date=row[3],
                    failure_mode=row[4], symptoms=row[5], root_cause=row[6],
                    action_taken=row[7], downtime_hours=row[8], safety_related=row[9],
                    record_type=row[10] if len(row) > 10 else "corrective",
                )
            )
            changed = True
    if changed:
        db.commit()
    return changed
