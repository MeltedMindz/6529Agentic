# Measuring the memory

Every optimisation claim here should be a number. This is how to get one.

```bash
AGENT6529_STATE_DIR=~/path/to/state ./eval/eval-memory.py
./eval/eval-memory.py --json after.json      # then diff against a baseline
```

Read-only against the database.

## What it measures, and why each one is here

| metric | why |
|---|---|
| `P@1`, `recall@k`, `MRR` | does it find the right thing |
| identifier discrimination | `rc.13` must not return the `rc.12` note. This is the whole reason the lexical half exists |
| **abstention** | out-of-scope queries must return NOTHING. A memory that answers everything cannot be trusted on anything |
| extraction miss rate | share of substantive posts that produced no note at all |
| hygiene | duplicate texts, fragments, lost referents (`"The author ..."` instead of a handle) |
| timings | embed latency cold and warm, scan cost per vector, and where brute force stops working |

## Baseline, 2026-11-10 (`baseline-20261110.json`)

131 notes, 319 observations, 0.85 MB.

```
retrieval    P@1 0.917   recall@5 1.00   MRR 0.958   34 ms/query
identifiers  1/2 discriminated
ABSTENTION   6/6 out-of-scope queries returned something   <- broken
extraction   miss rate 0.696 (48/69 substantive observations produced nothing)
hygiene      5 fragments under 25 chars, 5 lost referents
timings      embed 21 ms warm, scan 58 us/vector -> 578 ms at 10k notes
```

Read that together: **finding things works, knowing when to stay silent does
not.** Two of the six leaks scored *above* the 0.50 cosine floor (0.597 for
"what is the capital of France"), and the other four arrived through the
lexical path, which deliberately bypasses the floor. Measured separately, this
embedding model scores unrelated text pairs at median 0.441 and p95 0.519 — so
a 0.50 floor sits barely above the middle of noise and was never a real
decision boundary.

The extraction miss rate and the hygiene counts are the same defect seen from
two sides: the extractor abstains on 70% of real content, and on thin input it
invents. A post whose entire content was the heading
`**6529 Validator Hardware Recommendations**` produced three fabricated
"The validator should ..." claims, stored as trusted and recallable.

Junk notes are not inert. `RC9` ranked its own note first at 94 notes and, at
131, returns "Agent Tree is a paid Pro item" instead. Retrieval quality decays
as unfiltered material accumulates, so extraction precision is a retrieval
problem too.
