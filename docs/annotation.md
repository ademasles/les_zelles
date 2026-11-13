# Annotation guide

An answer key says what an estimator must take from a joinery CCTP. Scores are
only comparable when every key follows the same rules, so this guide is the
reference for writing, reviewing and changing keys. A rule that changes here
is applied to **every** split at once, with a note in the change log at the end.

## The corpus

- **Unit:** one tender, one joinery lot. When the DCE holds one CCTP for all
  lots, only the exterior joinery lot's chapters and the common chapters that
  bind it (general clauses, thermal and acoustic studies) are read.
- **Source:** public DCEs downloaded anonymously from the buyer's platform
  (`zelles corpus find`). The documents are third-party works: they stay on
  the annotator's machine, outside any repository, and are never sent to a
  cloud service.
- **Splits:** `zelles corpus split manifest.csv -o splits.json` draws
  `train` (40 %), `validation` (20 %) and `test` (40 %), with all the tenders
  of one buyer in the same split. Re-running it with more tenders keeps every
  earlier assignment.
  - `train`: read freely, tune rules and prompts on it.
  - `validation`: scores and per-field counts only; read a miss only to
    decide whether a change generalises, and never write a rule from it.
  - `test`: sealed. Its folder holds a `SEALED` file, so `zelles eval` reports
    counts only and appends each run to that file. Run it once per milestone,
    and report the number of runs with the score.

## Case layout

```
<split>/<idweb>/
  cctp.pdf | cctp.docx | cctp.md      the joinery CCTP, as downloaded
  expected.json                       {"description": "...", "requirements": [...]}
  NOTES.md                            optional: doubts, pages read, time spent
```

Each requirement is `{"field": "<spec field>", "value": "<text>"}`, or
`{"field": "<spec field>", "numeric": <number>}` for numeric fields. The fields
and their meaning are the catalogue in `src/zelles/domain/spec.py`.

## What to write down

1. **Only what binds the joinery lot.** A requirement in another lot's
   chapter, a quote from a regulation that sets no value, or a general
   sentence ("les menuiseries seront de qualité") is not written.
2. **Once per tender.** A value stated in five articles is one entry. Two
   different values for one field are two entries (Uw ≤ 1.3 for dwellings and
   Uw ≤ 1.6 for the hall).
3. **As written, shortest complete span.** Copy the words of the CCTP, cut to
   what identifies the value: `PVC blanc`, not `Les menuiseries seront en PVC
   blanc teinté masse`. Keep a qualifier only when it changes the requirement
   (`RAL 7016 extérieur / blanc intérieur`).
4. **Numbers as numbers.** For `uw`, `ug`, `ujn`, `sw`, `tlw` and `acoustic`
   write `numeric` with the bound (`1.3`, not `≤ 1,3 W/m².K`). One entry per
   distinct bound.
5. **No inference.** If the CCTP says "double vitrage 4/16/4 argon" there is no
   `ug` entry, even though a Ug follows from it. If it says "conforme à la
   RE2020" with no figure, `regulation` gets `RE2020` and nothing more.
6. **Equivalence clauses** ("ou techniquement équivalent") are not values.
   The named reference is written under `profile_system`.

## Field conventions

These follow the estimator's reading where a value could belong to two
fields.

| Field | Write | Do not write |
|---|---|---|
| `frame_material` | `PVC`, `aluminium`, `bois`, `bois-aluminium` | the colour or finish |
| `profile_system` | the named range: `Schüco AWS 70`, `Kömmerling 76` | the supplier alone |
| `color` | RAL codes or named colours, bi-colour as one entry | `laqué` (that is a finish) |
| `finish` | `thermolaqué`, `anodisé`, `plaxé`, wood species and stain, `Qualicoat` | the colour |
| `glazing_composition` | the build-up as written: `44.2/16/4` | the gas or coating |
| `glazing_type` | `double vitrage`, `faible émissivité`, `argon`, `contrôle solaire` | the build-up |
| `safety_glazing` | `44.2`, `SP10`, `P2A`, `feuilleté`, `trempé` | |
| `aev` | the classes as written: `A*3 E*7B V*A2` | the standard number |
| `acoustic` | joinery ratings (Ra,tr, Rw) and shutter-box Dn,e,w | air-inlet ratings (under `air_inlets`) |
| `security_class` | `RC2`, `CR2`, the standard's class | hardware items |
| `hardware` | one entry per part named: handle, hinge, lock, closer, strike | general "quincaillerie de qualité" |
| `shutters` | type, box, slat material, drive: `volet roulant`, `coffre tunnel`, `manœuvre électrique` | the acoustic rating of the box |
| `air_inlets` | type, airflow module, acoustic rating, `hygroréglable` | the ventilation system of the building |
| `installation` | `pose en applique`, `pose en tunnel`, `rénovation sur dormant existant`, `dépose totale`, sealing | site logistics |
| `standards` | each code as cited: `NF DTU 36.5`, `NF EN 14351-1` | the year unless the CCTP gives it |
| `certifications` | marks and labels: `CE`, `NF`, `Avis Technique`, `CEKAL`, `Acotherm`, `SNFQ`, `PEFC` | |
| `regulation` | frameworks: `RE2020`, `RT existant`, `ERP`, `sismique` | standards |

## Process

1. **Draft.** Run `zelles analyze` on the CCTP (rules, local model at most)
   and start from its sheet. Never send a document to a cloud model.
2. **Read.** Read the joinery lot end to end and add what the draft missed.
   Delete what it found but the rules above exclude.
3. **Check.** One pass per field against the table above. Write doubts in
   `NOTES.md` rather than guessing.
4. **Freeze.** Once a key is written its split decides who may read it.
   `zelles eval` prints a hash of all keys; a score is quoted with that hash.
5. **Agreement.** Every tenth tender is keyed twice, the second time without
   seeing the first. Agreement under the strict scorer is reported with the
   corpus; a field below 0.8 means this guide needs a clearer rule for it.

## Change log

- **2026-11-13:** first version, from the conventions used for the nine
  original keys (shutter-box ratings, SNFQ as a certification, lacquered as a
  finish) and the hardware decision of 2026-11-10 (one entry per part).
