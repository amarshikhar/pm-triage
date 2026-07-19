# CWRU bearing-data provenance

Source: Case Western Reserve University Bearing Data Center.

- Official data index: https://engineering.case.edu/bearingdatacenter/download-data-file
- Apparatus and procedures: https://engineering.case.edu/bearingdatacenter/apparatus-and-procedures
- Normal 0 hp file: `https://engineering.case.edu/sites/default/files/97.mat`
- Inner-race 0.007 inch, 0 hp: `https://engineering.case.edu/sites/default/files/105.mat`
- Ball 0.007 inch, 0 hp: `https://engineering.case.edu/sites/default/files/118.mat`
- Outer-race 0.007 inch at 6 o'clock, 0 hp: `https://engineering.case.edu/sites/default/files/130.mat`

The curation script verifies the official downloads with SHA-256 checksums
before producing compact 0.1-second feature episodes. Raw MATLAB files are not
committed. The official pages describe the data and apparatus but do not state
an explicit dataset license. Therefore these derived episodes are marked
research/evaluation only; redistribution and commercial use need confirmation
from CWRU. This is a release limitation, not a guessed permission.

Each replay concatenates real healthy steady-state frames with real faulty
steady-state frames. It is valid for testing ingestion, anomaly detection, and
cross-testbed abstention, but it is not a natural fault-onset recording and is
never described as one.

