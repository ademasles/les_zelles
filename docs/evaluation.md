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

The **strict** score drops the quote: the expected text must appear in the extracted value itself. The lenient score credits a correct line whose value is garbled ("laqué blanc placé entre 0" from a line that says RAL 9016); the strict score does not, and it is closer to what an estimator reads in the sheet. Both are reported.

## Metrics

- **Precision, recall, F1** per case and micro-averaged, lenient and strict, plus the list of misses.
- **95 % interval** of micro F1, by bootstrap over cases. Tenders are the unit of evidence, so with three held-out tenders the interval is wide; a change inside it is not a measured improvement.
- **Grounded:** the share of predicted requirements whose quote was found in the source.
- **Cost:** tokens and USD for the run.

## Current state

**Public case.** `evals/golden/residence_tilleuls` is a synthetic Lot 05 (PVC dwellings, an aluminium hall, shutters and air inlets). Rules alone score 1.00 on it. It was written alongside the rules, so it is a regression gate in CI (`--min-f1 0.9`), not a quality claim.

**Private set.** Nine real joinery CCTPs from public tenders (16 to 73 pages, Word exports with a text layer), each with a hand-checked answer key. The documents are confidential and are not in this repository; the keys live next to them. Six cases are used for development and three are held out: their scores are reported, but their misses are never read while tuning, so the held-out score estimates performance on a tender nobody has seen.

| Configuration | Held-out micro F1 | Held-out precision | Dev micro F1 |
|---|---|---|---|
| Rules only, before tuning on the nine tenders | 0.648 | | 0.716 |
| Rules only, current | **0.860** | **0.871** | 0.973 |
| Rules + granite4.2 8B (Ollama, local) | 0.847 | about 4 pts lower | |

The local model recovers a few requirements the rules miss but adds more false positives, so rules-only stays the default. Run `zelles eval -m <model>` on your own cases before switching.

**Labelling choices.** Answer keys follow the estimator's reading where a value could go to two fields: shutter-box Dn,e,w ratings are acoustic requirements (apart from facade and air-inlet ratings), quality labels such as SNFQ are certifications, and a lacquered finish is a finish, not a colour.

## Adding a case

Three to five more real cases covering wood, renovation and curtain walls would make model comparisons sharper. A case can be shared publicly only once it is anonymised (no project, client or address).
