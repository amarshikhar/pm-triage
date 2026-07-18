# Asset economics — where the dollar figures come from

Every triage case shows a business exposure: `expected downtime hours × the
asset's hourly downtime cost`. Those hourly costs live in the machine catalog
(`Machine.hourly_downtime_cost`), and this note is their provenance.

## Published anchors

- **Siemens/Senseye, "The True Cost of Downtime 2024"** ([report PDF][tcod24],
  [analysis][tcod-blog]): Fortune Global 500 industrials lose **~$1.4T/year**
  (≈11% of revenue) to unplanned downtime; an automotive plant loses
  **~$2.3M per hour**; surveyed outages average ~4 hours. Discrete
  manufacturing sits far below automotive, commonly quoted at
  **$10k–$50k per plant-hour**.
- The same programme's 2022 edition ([PDF][tcod22]) carries the prior
  survey wave, useful for the trend (costs roughly doubled since 2019).

[tcod24]: https://assets.new.siemens.com/siemens/assets/api/uuid:1b43afb5-2d07-47f7-9eb7-893fe7d0bc59/TCOD-2024_original.pdf
[tcod22]: https://assets.new.siemens.com/siemens/assets/api/uuid:3d606495-dbe0-43e4-80b1-d04e27ada920/dics-b10153-00-7600truecostofdowntime2022-144.pdf
[tcod-blog]: https://blog.siemens.com/2024/07/the-true-cost-of-an-hours-downtime-an-industry-analysis/

## Allocation method

The published figures are **plant-hour** numbers. A single asset's downtime
only costs the plant-hour rate when the asset takes the line down with it, so
the catalog allocates per asset:

1. Take a conservative discrete-manufacturing plant rate of **$10k/hour**
   (the bottom of the published range — this artifact under-claims on purpose).
2. A **line-down asset** (criticality 5: the main conveyor, the plant air
   supply) carries 35–40% of the plant rate — losing it stops the line.
3. Machines with redundancy or buffers carry their marginal contribution:
   parallel CNC capacity, a standby compressor, an off-line test loop.

| Asset | Criticality | $/hr | Rationale |
|---|---|---|---|
| CNV-01 Main Conveyor | 5 | 4,000 | Single point of failure for Line B |
| CMP-01 Air Compressor 01 | 5 | 3,500 | Plant air; brief ride-through from receivers |
| CNC-01 Mill 01 | 4 | 1,800 | Bottleneck share of Line A throughput |
| PMP-01 Coolant Pump 01 | 4 | 1,600 | Stops CNC-01/02 cutting when down |
| CNC-02 Mill 02 | 3 | 1,200 | Parallel capacity absorbs part of the loss |
| PMP-02 Hydraulic Pump 02 | 3 | 1,100 | Line B auxiliaries |
| PMP-03 Circulation Pump (SKAB) | 3 | 900 | Test-loop availability, no production stop |
| CNV-02 Packing Conveyor | 2 | 600 | Manual packing workaround exists |
| CMP-02 Air Compressor 02 | 2 | 400 | Standby unit; exposure is lost redundancy |

**These are illustrative allocations, not measurements.** The method (published
plant rate × structural share) is the point: in a deployment, the finance
figures come from the customer's own cost accounting, and only this table
changes. The rest of the system treats the cost as an opaque business input —
it is deliberately shown next to the P1–P4 governance score, never folded
into it.
