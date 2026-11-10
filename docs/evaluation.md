# Evaluation

Extraction quality is measured, not assumed. `zelles eval` runs the full pipeline on every case in `evals/golden/` and compares the result to the expected requirements.

```bash
uv run zelles eval                         # rules only
uv run zelles eval -m ollama:qwen3:8b      # with a model
uv run zelles eval --min-f1 0.85           # exit 1 below this strict F1 (used in CI)
uv run zelles eval --blind --json r.json   # counts only, for a held-out set
```

## A golden case

```
evals/golden/<case>/
  cctp.md | cctp.pdf | cctp.docx   the source
  expected.json                     {"requirements": [{"field": "uw", "numeric": 1.3}, {"field": "frame_material", "value": "PVC"}, ...]}
```

A prediction matches an expected requirement when the field is the same and either the number is equal (`numeric`) or the expected text appears, after folding wording variants (accents, case, plurals, "D.T.U. n°39" = "DTU 39"), in the predicted value (`value`).

Matching is **one to one** (scorer v2, November 2026):

- Predictions are first grouped by field and value. A key lists a value once per tender, while the sheet repeats it for every article that states it, so "PVC" found in three articles is one prediction.
- Groups and expected requirements are then paired by maximum bipartite matching. One long value that contains two expected values is credited once, and two near-duplicate values for one expected requirement count as one hit and one extra.
- Scope is not scored yet.

The **strict** score, the headline, looks at the extracted value only. The **lenient** score also accepts the expected text in the cited quote, which credits a correct line whose value is garbled ("laqué blanc placé entre 0" from a line that says RAL 9016). It shows how much is lost in cutting values, not in finding them.

Each report carries a **run manifest**: scorer version, code commit (marked `+dirty` when modified), a hash of the answer keys, the model and the start time. Two scores are comparable only when the scorer version and the key hash are the same.

## Metrics

- **Precision, recall, F1** per case and micro-averaged, strict and lenient, with misses and extras per field.
- **95 % interval** of micro F1, by bootstrap over cases. Tenders are the unit of evidence, so with three held-out tenders the interval is wide; a change inside it is not a measured improvement.
- **Grounded:** the share of predicted requirements whose quote was found in the source.
- **Cost:** tokens and USD for the run.

## Current state

**Public case.** `evals/golden/residence_tilleuls` is a synthetic Lot 05 (PVC dwellings, an aluminium hall, shutters and air inlets). Rules alone find every expected requirement on it; strict F1 is 0.87 under scorer v2 because the sheet repeats some values in longer forms. It was written alongside the rules, so it is a regression gate in CI (`--min-f1 0.85`), not a quality claim.

**Private set.** Nine real joinery CCTPs from public tenders (16 to 73 pages, Word exports with a text layer), each with a hand-checked answer key. The documents are confidential and are not in this repository; the keys live next to them. Six cases are used for development and three are held out: their scores are reported, their misses are not read while tuning.

History, strict micro F1 under scorer v1 (many-to-one matching):

| Configuration | Held-out (3) | Dev (6) |
|---|---|---|
| First strict measure, 6 November | 0.775 | 0.922 |
| Rules + granite4.2 8B, gap-fill | 0.799 | 0.932 |
| Rules + qwen3:8b, gap-fill | 0.801 | 0.937 |
| Current rules, 10 November | **0.819** | 0.973 |

Same rules (commit `d7c60d6`), re-scored with scorer v2 on 10 November:

| Set | Strict P | Strict R | Strict F1 (95 % CI) | v1 strict F1 |
|---|---|---|---|---|
| Held-out (3) | 0.747 | 0.793 | **0.769** (0.690–0.822) | 0.819 |
| Dev (6) | 0.826 | 0.994 | 0.902 (0.870–0.944) | 0.988 |

Recall barely moves; precision falls because near-duplicate values (shutters, hardware, installation) no longer hide behind one key entry. With three held-out tenders the interval is about ±0.07, so the held-out score cannot yet rank two close variants; growing the set to 30 or more tenders with a sealed test split is the next step.

**Labelling choices.** Answer keys follow the estimator's reading where a value could go to two fields: shutter-box Dn,e,w ratings are acoustic requirements (apart from facade and air-inlet ratings), quality labels such as SNFQ are certifications, and a lacquered finish is a finish, not a colour.

## Adding a case

Three to five more real cases covering wood, renovation and curtain walls would make model comparisons sharper. A case can be shared publicly only once it is anonymised (no project, client or address).
