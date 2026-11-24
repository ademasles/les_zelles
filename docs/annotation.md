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

## Edge cases

Settled while keying the 12 train tenders. Each one is now a rule.

**What counts**

- **Mixed lots.** When a lot mixes joinery and metalwork, key every opening in
  the building envelope: windows, doors of any material (steel included),
  glazed walls, verrières and roof glazing, with their glazing, shutters and
  hardware. Railings, grilles, gates, stairs, ladders and canopies are left out.
- **General chapters.** In a multi-trade CCTP, search the general chapters
  (lot 00, "prescriptions communes") for what binds the joinery: regulation
  frameworks, thermal and acoustic targets, ERP and fire rules, seismic zone,
  accessibility, and standards cited for the joinery. Site organisation is
  left out.
- **Boilerplate.** A material or product the lot does not use is not keyed,
  even when a copied clause names it (`PVC` inside the acoustic clause of an
  aluminium lot). The inconsistency goes in `NOTES.md`.
- **Contradictions.** Two direct requirements that contradict each other are
  both keyed (`chêne massif` in the general clauses, `mélèze` in the
  description), and the conflict goes in `NOTES.md`.
- **Options.** Items to be priced as a variant or option (PSE, "à
  comptabiliser en variante") are keyed like the base offer, with a note.
  Items "pour mémoire" because another lot supplies them are not keyed.
- **Permissions.** A value the CCTP only allows ("pourra être utilisé",
  "possibilité de") is not a requirement and is not keyed. Standards are the
  exception (below).
- **Thresholds and alternatives.** A device required only above a threshold
  the tender does not reach is not keyed. Alternatives left to the architect
  are all keyed. A generic list of types that no article uses is not keyed (its
  standards are). An annex of indicative products declared non-contractual is
  not keyed.
- **General clause against the articles.** When a general clause states a
  material as a direct requirement and the articles contradict it, both are
  keyed (a contradiction, not boilerplate).
- **Air inlets from another lot.** When the joinery lot fits inlets another lot
  supplies, the fitting is keyed under `air_inlets`.
- **Interior doors.** In an exterior joinery lot, only openings in the
  building envelope are keyed. Interior doors (WC, technical rooms, fire
  doors between rooms) and their hardware are left out, unless the lot also
  covers interior joinery.
- **Existing joinery.** Work on existing joinery or cladding is not keyed, but
  existing hardware re-used on the new joinery (`crémones existantes`) is keyed
  under `hardware`.

**Where a value goes**

- Wood species go under `finish`, and `frame_material` stays `bois`.
- Heritage constraints (ABF, Monuments Historiques, PSMV, site classé) and
  regulation articles (`CO 48`) go under `regulation`.
- Fire classes go under `fire_rating` as written: resistance (`EI 30`, `E 30`,
  `pare-flammes 1/2 h`) and reaction to fire (`B-s2,d0`, `M1`).
- A figure with no numeric field of its own is written as text under the part
  it describes: a glass `Sg` under `glazing_type`, a shutter box `Uc` or a
  `gtot` under `shutters`. A glass `Sg` is never `sw`, and a `TLg` is never
  `tlw`.
- `uw` holds the U-value of the whole element, so `Ud` (doors) and `Ucw`
  (curtain walls) go there too.
- `acoustic` also holds a façade target that the CCTP sets for the joinery
  ("classement des façades de 35 dB"). One number stated both as `RA,tr` and
  as `DnT,A,tr` is one entry.
- `shutters` holds every shutter, blind and sun protection the lot supplies,
  outside, inside or within the glazing, with its controls (motor, crank,
  weather station) and named products.
- PMR requirements (threshold height, handle height and type, glazing
  markings, operating force) go under `accessibility`, one entry each, and are
  not repeated under `hardware`.
- `opening_type` holds how an opening opens, one entry per type as written:
  `oscillo-battant`, `coulissant`, `châssis fixe`, `soufflet`, `porte à 2
  vantaux`. Not the item's full description (`Porte vitrée à 2 vantaux égaux
  en aluminium`), and not its shape.
- Smoke-vent sashes go under `opening_type`. Wood profile shapes (`mouton et
  gueule de loup`) and `petits bois` go under `profile_system`.
- Performance classes awarded by a certification scheme, and acoustic `AC`
  classes with no figure, go under `certifications` as written (under
  `shutters` when they rate a shutter box).
- Partial thermal values: a frame-only `Uf` is text under `profile_system`;
  the U-value of an opaque infill panel is not keyed. A glass `TL` or `RL` is
  text under `glazing_type`, like `Sg`.
- Opening drives and automation (window motors, natural-ventilation controls,
  automatic or sectional door drives) go under `hardware`. A smoke vent's
  mechanism and product name go under `opening_type` with the sash.
- A door's durability or traffic class has no field yet: text under
  `profile_system`.
- A single pane's thickness (`4 mm`) goes under `glazing_composition` only when
  it is the whole build-up.

**How a value is written**

- **Standards.** Every code the joinery lot's own chapters cite is keyed,
  lists included and whatever the wording, one entry per code. From the
  general chapters, only codes cited for the joinery. A list that shares a
  prefix is split, repeating the prefix as the first code writes it:
  `NF P 85-530/540` gives `NF P 85-530` and `NF P 85-540`, and
  `D.T.U. n° 39.1, 39.4` gives `D.T.U. n° 39.1` and `D.T.U. n° 39.4`.
- **One value, two notations.** A standard or a build-up written twice in
  two notations is one entry. A code with several revision years is one entry
  as written. Alternative classes ("B-s2,d0 ou M1") are one `fire_rating` entry
  as written.
- **Tables.** Each distinct value in a table is its own entry (`33.2`, `44.2`,
  `55.2`, `66.2`).
- **Colours.** A colour name given with its RAL code is one entry, the RAL
  code. "Peinture blanche" gives a `finish` (`peinture`) and a `color`
  (`blanche`).
- **Hardware models** are written with their part (`ferme-porte DC700`).
  A hardware entry is the part with the words that identify it (model, maker,
  finish, function), cut at the first clause that adds another part or a
  location: `crémone pompier Vachette`, not the whole sentence.

## Process

1. **Draft.** For `train`, start from the rules' sheet
   (`expected.draft.json`, local only; never send a document to a cloud
   model). `validation` and `test` keys are written from the CCTP alone: a key
   drafted by the system under test would lean towards what the system already
   finds, and would favour the rules over any other reader. Their annotator
   never sees the rules, the drafts or the train results.
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

- **2026-11-24:** the validation annotator's doubts settled (certification
  classes, partial thermal values, drives, thresholds, one value in two
  notations), and the three fields where two annotators agreed least on a
  re-keyed train tender (`opening_type`, interior doors, hardware spans).
- **2026-11-19:** edge cases settled while keying the 12 train tenders (mixed
  lots, general chapters, options, permissions, figures without a field,
  standard lists, colours, hardware models), fire classes under `fire_rating`
  (#40), and validation keys written without a draft. The nine original keys
  predate these rules and are not updated.
- **2026-11-17:** test keys are written without a draft.
- **2026-11-13:** first version, from the conventions used for the nine
  original keys (shutter-box ratings, SNFQ as a certification, lacquered as a
  finish) and the hardware decision of 2026-11-10 (one entry per part).
