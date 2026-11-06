# DNA Digital Security Assistant — simulation and test set v2.0.1

Synthetic practice and test data, a simulated user and an evaluator for the DNA challenge at Since AI Hackathon 2026: **Digital Security Assistant: What Should I Do Now?**

**Start with `START_HERE.html`** (or `START_HERE.md`).

```bash
python3 tools/validate.py
python3 baselines/rules_baseline.py --cases data/dev/cases.jsonl --out b.jsonl
python3 eval/evaluate.py --cases data/dev/cases.jsonl --submission b.jsonl
```

588 dev cases with ground truth · 335 test inputs · 58 scenario families · five journeys · Finnish, English and Swedish users · Python 3.10+, no dependencies.

Synthetic. Not DNA's advice. Code MIT, data CC BY 4.0, © 2026 Since AI ry.
