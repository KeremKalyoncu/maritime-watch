# Eval report

_generated 2026-09-12 18:46 UTC · `py eval/run_eval.py`_

| Bileşen | Precision | Recall | F1 | TP | FP | FN |
| :-- | --: | --: | --: | --: | --: | --: |
| News keyword filter | 1.00 | 1.00 | 1.00 | 8 | 0 | 0 |
| Text extractor (field accuracy) | 1.00 | 1.00 | 1.00 | 9 | 0 | 0 |
| AIS anomaly rules | 1.00 | 0.83 | 0.91 | 5 | 0 | 1 |

### AIS anomaly rules — kaçırılanlar
- sharp turn while under way -> course-spike: got [] exp ['course-spike']

> Sentetik + az sayıda örnek; mutlak sayı değil, regresyon takibi için.
