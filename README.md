# AI Researcher R1: rota puzzles under a fixed weak model

Dagani Jesu Sanihit

**One-line summary.** The weak model (`granite-4.2-8b`) only *reads*: it turns each note line into one constraint from a nine-atom language, or SKIP. An exact solver does all the reasoning: it counts consistent rotas, returns them, and extracts a minimal conflicting set. On the 60 visible items this scores about 94 to 98% macro exact match at 1x, against 0% when the model answers directly.

## Run it

    python -m venv .venv && .venv\Scripts\activate
    pip install -r requirements.txt          # Python [FILL: python --version]
    copy .env.example .env                   # add the key
    python run items.json --budget 1x --out answers.json
    python score.py visible_key.json answers.json
    python ablate.py --runs 2 --budgets 1x,3x --out ablation.md

Offline check of the solver with no model (a regex stand-in for the model, in `dev/`): `python tests/oracle_check.py` gives 1.0 on all 60 items. The stand-in is **not** used by `./run`.

## Architecture

    notes -> [header parser] -> [Granite, 1 call = 1 pass] -> [parse + ground atoms]
          -> [exact solver over all 720 worlds] -> unique / ambiguous / inconsistent

- `header.py`: the header is templated, so ordinary code reads staff, blocks and stations.
- `extract.py`: one call per pass. The prompt has category rules (what a statement is *about* decides the atom), a worked invented example with 32 lines, and an explicit SKIP list. The model echoes the first words of each line to stay aligned.
- Grounding: names, stations and blocks are snapped onto the item's vocabulary. If a person is paired with a station name but the atom is `AT`, it is repaired to `STATION` (and the reverse). Anything still invalid is dropped.
- `solver.py`: every constraint is a boolean mask over all (block order x station holder) worlds. Counting solutions and deletion-based minimal conflict extraction are mask operations.
- `pipeline.py`: with more than one call, atoms are voted per statement. If the result has an impossible shape (more than 4 solutions, or a conflict citing fewer than 3 statements, which the brief rules out), one statement is swapped for an alternative that another pass produced. At 1x, a 1-2 statement conflict is treated as an extraction error and the set is searched for the genuine 3+ statement conflict.

**Is extraction model-based or symbolic?** Model-based. The visible phrasings are templated, so a regex parser reaches 100% on them (it is in `dev/` and used only as a test oracle), but it would fail on held-out wording, so `./run` never uses it. The prompt describes categories and direction rules rather than listing the visible sentences, and its examples use invented names and wording.

## Characterising the model before designing around it

Asked for the final answer, Granite scores 0%. Asked for one constraint per line, it is much better but not perfect. I measured **per-statement accuracy** against the regex oracle on the visible set, and used the error categories to decide what to build:

| Version | Main change | Macro (1x) | Statements right | Items with every statement right |
|---|---|---|---|---|
| v1 | first prompt | 33.3% | 84% | 5/60 |
| v2 | echoed lines, direction rules | 53.3% | 87% | 14/60 |
| v3 | no commentary, one atom per line, station rules | 85.0% | 96% | 32/60 |
| v4 | atom-family repair, refused-request examples | 98.3% / 95.0% | 98% | 43/60 |
| v5 | small-conflict repair | 95.0% / 98.3% | not measured | not measured |

An item is only right if all ~19 of its statements are, which is why 87% per statement still gave 53%. The recurring failures were: rambling reasoning that ate the token budget and lost later lines, reversed `BEFORE` direction, wrong middle person in `BETWEEN`, and refused or past requests ("put in for X and was turned down", "last month Y was on intake") read as real constraints.

## Ablation (macro exact match, visible set; mean +- std over n runs)

| variant | 1x | 3x |
|---|---|---|
| full system | 95.0% (+-0.0, n=2) | 93.3% (+-0.0, n=2) |
| - guided prompt (bare instruction) | 6.7% (+-1.7) | 17.5% (+-2.5) |
| - vote (extra calls unused) | 94.2% (+-0.8) | 90.8% (+-0.8) |
| - grounding of atoms | 95.0% (+-0.0) | 93.3% (+-0.0) |
| - core minimisation (cite all) | 65.8% (+-0.8) | 60.8% (+-0.8) |
| - solver-guided repair | 90.0% (+-1.7) | 95.0% (+-0.0) |
| - solver (model answers directly) | 0.0% | 0.0% |

Further full-system runs: 1x gave 92.8% +- 1.6 (n=3) in this table's configuration, and 10x gave 98.3% in both of two runs. This table was produced before the small-conflict step in `pipeline.py` was added (that step is an addition for one failure I diagnosed; I did not re-run the whole table).

**What is real and what is noise.** At 1x the repair step cannot act, so "full system" and "- repair" are the same code there, yet they differ by 5 points. That gap is the noise floor at n=2 (`temperature=1.0`). So:
- Real: the solver (0% to ~95%), the guided prompt (7-18% to ~95%; the bare prompt also uses a different output format, so part of that gap is format failure), and minimal-core citation (~30 points).
- Not measurable: voting, the 3x budget, grounding and repair. I built them, and they showed no benefit on this set. Granite's mistakes repeat across samples, so independent samples cannot vote them away. 10x scoring 98.3% twice is suggestive, but one 1x run also hit 98.3%, so I do not claim a budget effect.

## What I built and removed or kept for nothing
- Early stopping when the answer looked plausible: it lost ~20 points in simulation (a wrong answer can look plausible), so repair now runs only after all calls are used.
- Voting, grounding and repair stay in, because they are cheap and the harness is meant to be general, but the table shows I cannot demonstrate a gain from them here.

## Where it breaks
- **Distractors read as constraints.** Refused requests become `NOT_AT`. Usually harmless to the final answer, but not guaranteed.
- **Repair side effect (item B2-049).** "Last month Tomas was on intake" was written as `AT(Tomas, intake)`. Before the atom-family repair that atom was invalid and dropped; after it, it became a valid false `STATION` constraint that contradicted another line and produced a 2-statement conflict, so the minimal conflict cited the wrong lines even though the real 3-statement cycle was extracted correctly. A rule using the brief's "at least 3 statements" fixed this item; I verified it on this item only.
- **Same-set tuning.** I tuned on these 60 items. Held-out wording will be harder, and I have no held-out number. Treat 94-98% as an upper bound.
- **Scale.** The solver enumerates every world (720 here). That is fine for 5 people and 3 stations, but it will not scale to large rotas.
- **Reliance on the brief's structure** (2-4 ambiguous solutions, conflicts of 3+ statements) in the repair logic.

## With a month
1. Build a held-out paraphrase set, written by several people, and report extraction accuracy on it.
2. Replace resampling with diverse prompts and per-line confidence, since identical prompts repeat the same mistakes.
3. Use weighted MaxSAT repair instead of single swaps.
4. Make SKIP decisions a separate, evaluated classification step, since distractors are the dominant error.
5. Scale the solver with a SAT/CP backend.
