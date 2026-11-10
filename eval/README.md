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

## After the embedding fix, 2026-11-10 (`after-lowercase-20261110.json`)

```
retrieval    P@1 1.000   recall@5 1.00   MRR 1.000   35 ms/query
identifiers  2/2 discriminated        (was 1/2)
ABSTENTION   6/6 out-of-scope queries returned something   <- still broken
timings      scan 20.2 us/vector -> 202 ms at 10k notes    (was 57.8 / 578)
```

One `.lower()` did most of that. The local GGUF of nomic-embed-text uses the
**uncased** BERT vocabulary but never lowercases its input, so every token
carrying a capital missed the vocab and became `[UNK]`. Measured on this
machine: `"Axiom"`, `"Melted"`, `"Soulforge"`, `"Bankr"` and a full `0x`
address all returned the **byte-identical vector** — eight distinct inputs
collapsing to four. Two unrelated notes, *"Agent Tree is a paid Pro item"* and
*"Trace Waterfall is a paid Pro item"*, scored cosine **1.000000**; lowercased
they separate to 0.716.

This corpus is handles, version strings and addresses, so the defect was
hitting nearly every note — and the `[wave / @author / date]` header added by
`contextualize()` was itself almost entirely `[UNK]`, which is why that header
underperformed when it was first measured.

Abstention is untouched by this and is the next thing to fix.

## Known limit: cosine cannot see negation

Measured on the re-embedded corpus, a claim against its own negation:

| cosine | claim vs negation |
|---|---|
| 0.9843 | device keys *can not* move funds / *can* move funds |
| 0.9798 | home validators connect *outbound* only / *inbound* only |
| 0.9714 | tor is *on* by default / *off* by default |
| 0.9347 | signed posts *expire after 180 days* / *never expire* |

Retrieval is unharmed — asked "can device keys move funds", it returns the
note that answers it, which is correct. The consequence is narrower and
sharper: **no note-to-note similarity rule can be trusted to mean agreement.**
Any dedup, auto-supersession or corroboration-counting threshold below ~0.985
would fuse a claim with its opposite. That is why `supersede()` takes an
explicit id and deduplication is the exact `UNIQUE(drop_id, text)` constraint,
and it should stay that way.
