"""Offline evaluation of the triage agent against simulator ground truth.

The simulator already knows which fault it injected, so every anomaly it
produces is a labelled example. This package turns that free label into an
accuracy and calibration measurement, which is the only way to justify the
number the agent reports about itself (`confidence`).

Run it: `python -m app.eval --trials 24 --mode mock`
"""
