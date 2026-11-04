# Evaluation

Extraction quality is measured, not assumed. `zelles eval` runs the full pipeline on every case in `evals/golden/` and compares the result to the expected requirements.

```bash
uv run zelles eval                         # rules only
uv run zelles eval -m ollama:qwen3:8b      # with a model
uv run zelles eval --min-f1 0.9            # exit 1 below the threshold (used in CI)
```

## A golden case

```
evals/golden/<case>/
  cctp.md | cctp.pdf | cctp.docx   the source
  expected.json                     {"requirements": [{"field": "uw", "numeric": 1.3}, {"field": "frame_material", "value": "PVC"}, ...]}
```

A prediction matches an expected requirement when the field is the same and either the number is equal (`numeric`) or the expected text appears, accent- and case-insensitively, in the predicted value or its quote (`value`). Scope is not scored yet.

## Metrics

- **Precision, recall, F1** per case and micro-averaged, plus the list of misses.
- **Grounded:** the share of predicted requirements whose quote was found in the source.
- **Cost:** tokens and USD for the run.

## Current state

There is one synthetic case (`residence_tilleuls`, a Lot 05 with PVC dwellings, an aluminium hall, shutters and air inlets). Rules alone score a micro F1 of 0.97 on it. This number is optimistic: the case was written alongside the rules.

The most useful contribution to this project is a real CCTP, anonymised, with its `expected.json`. Three to five real cases covering PVC, aluminium and wood, renovation and new build, are enough to make model comparisons meaningful.
