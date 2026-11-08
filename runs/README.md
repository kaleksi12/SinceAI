# Runs

Each folder is one run of `scripts/run_single.py`: predictions, the organisers' evaluator report (`report.txt`) and run metadata.

## Final results

| Folder | What | Safe-action pass |
|---|---|---|
| `20261108-001633_final_dev_588_single` | 588 dev cases, single-turn | 86.6 % |
| `20261108-060102_final_dev_588_multi` | 588 dev cases, multi-turn | 86.2 % |
| `20261108-000431_test_335_single_v3` | 335 test inputs, source of `test_predictions.jsonl` | scored by organisers |

All other folders are experiments: model comparisons, held-out checks, small trial runs and interrupted runs. Not every run we made is committed here; some trial and interrupted runs stayed on our own machines. 
The `…_optimized` runs tested an early prompt optimizer that automatically rewrote the analysis guidelines. It gave a small gain on 60 held-out cases (33.3 % → 38.3 % single-turn, 61.7 % → 63.3 % multi-turn), but later rule changes helped far more, so the final code does not use it and its files were removed from the repository.
