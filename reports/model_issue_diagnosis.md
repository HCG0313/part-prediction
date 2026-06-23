# Model Issue Diagnosis

- Created at: 2026-06-23T20:33:58
- Accuracy status: ok
- DataLab status: ok / source=datalab
- KRX status: ok

## Current Issues

- score_calibration: Recent top-ranked sectors have weak hit rate. Cause: News/FOMO attention and next-day return have diverged in recent sessions. Fix: Recent sector reliability calibration is now applied to tomorrow_total_score.
