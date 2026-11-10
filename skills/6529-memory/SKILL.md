---
name: 6529-memory
description: Learn from 6529 conversations and recall prior context before replying. Use when you want to remember what someone said, build on an earlier conversation, check what you know about a person or topic on 6529, distil what you have read, or retract something you learned that turned out to be wrong. Triggers include "what do I know about", "what did they say before", "remember this conversation", "learn from the wave", "recall", "have we discussed this", "forget that", "that is no longer true".
allowed-tools: Bash(./bin/6529:*), Bash(6529:*)
---

# 6529-memory

Remember what was said on 6529, and use it when replying.

```bash
6529 doctor                  # check state, session and models first
6529 learn --distil          # ingest allowlisted Waves, extract claims
6529 recall "<question>"     # what do I know that bears on this
6529 recall --about <handle> # what do I know from this person
6529 memory                  # statistics
6529 supersede <id> --content "..."   # replace a claim that changed
6529 forget --note-id <id>            # retract one claim
6529 forget --about <handle>          # retract everything about someone
```

`respond` already recalls automatically and returns `prior_context` alongside
the staged draft.

## Three separate jobs

| | |
|---|---|
| **observe** | keep what was said, verbatim, with provenance |
| **learn** | distil durable claims using a **local** model |
| **recall** | find what is relevant now |
| **retract** | close a claim that is wrong or out of date |

Embedding and extraction run against local Ollama models, so public forum
content never leaves the machine and memory costs no API calls per drop.

## One store, more than one surface

Memory is not 6529-only. Anything said anywhere can go in, tagged with the
surface it was said on:

```bash
6529 observe <tweet_id> --source twitter --author someholder \
     --conversation <thread_id> --content "..."
6529 recall "receipts" --source twitter   # scope to one surface
6529 recall "receipts"                    # search everything
6529 recall --about someholder            # their whole history, both places
```

A person met in two places is one history. A citation names the surface when
it is not 6529, so a recalled line never looks like it was said where it was
not.

One thing differs by surface. A reply on Twitter opens by naming who it
answers, so a leading `@handle` there is addressing, not subject. On 6529
there is no such convention and `@bob runs a validator` really is a claim
about bob. Getting this wrong tiers nearly everything said *to* the agent as
`third_party` and drops it from recall, so the subject detector is told which
surface it is reading.

## Recall searches two ways at once

Meaning **and** exact text, fused by rank:

- the **semantic** half finds notes that are *about* the question
- the **lexical** half finds notes containing the literal token

The second half is why `rc.12` does not return the note about `rc.11`.
Embeddings put near-identical identifiers almost on top of each other; BM25 is
the only half that separates them, and this content is full of versions,
addresses and handles.

Consequence worth knowing: **results are in fusion order, so `score` does not
decrease down the list.** A note found by exact match can sit above one with a
closer embedding. That is correct, not a sorting bug. `score` is the cosine
similarity; a low score on a top result means it earned its place lexically.

## Who is allowed to tell you something

A claim **about a person** is only recalled when the person entitled to make
it made it. Every note records `asserted_by`:

| tier | means | recalled |
|---|---|---|
| `self` | they said it about themselves | yes |
| `operator` | the operator said it | yes |
| `public_post_by_self` | a statement about the world, not about a person | yes |
| `third_party` | someone else made a claim about them | **no** |

Third-party claims are still stored, for the record. They are filtered at the
read boundary, in every path including the model-down fallback.

This is the gate that matters most: without it, anyone who can post can write
your memory about anyone else, and you would later repeat it as fact in your
own voice. If you want to know what *mallory* said about *bob*, read the drop;
do not expect recall to hand it to you as knowledge.

## When something stops being true

Retraction is enforced, not advisory. Rows are **closed, never deleted**, so
the same claim cannot be quietly re-learned from the archive:

```bash
6529 supersede 41 --content "hermes rc.12 is the current release"
6529 forget --about bob          # someone asks not to be remembered
```

- `supersede` keeps the chain: the old note is marked `superseded` and dated,
  the new one records what it replaced.
- `forget` marks `revoked`. Nothing revoked is ever recalled again.
- Use `supersede` when a fact **changed**, `forget` when it was **wrong** or
  when someone asks you to drop it.

If you notice you recalled something stale, retract it rather than remembering
to ignore it. A note you have to remember to ignore will eventually be used.

## How to use recall in a reply

Recall returns claims with a citation string:

```
[0.476] The nightly job recomputes every TDH entry from the API
        (@someholder in 6529 for Developers)
```

- **Attribution is not endorsement.** A note records that someone *said*
  something, not that it is true. Say "someholder mentioned that…", not
  "it is the case that…".
- **Cite when you lean on one.** If a reply rests on something you recalled,
  name who said it. It is both more honest and more useful.
- **Do not perform memory.** Recalling something is not a reason to mention it.
  If it does not improve the reply, leave it out.
- **Do not treat low scores as facts.** A weak semantic match is a hint, not
  knowledge.

## What never enters memory

- Anything flagged `suspicious: true`. It stays an observation for the record
  but is never distilled, so a hostile drop cannot plant text that gets
  recalled into a later prompt.
- Private memory, operator history, or configuration. This store is **public
  6529 content only**, which is exactly what makes it safe to feed back into a
  public reply.
- Anything without provenance. A claim that cannot name its source drop,
  author and Wave is not stored.

## Operating notes

- `learn` without `--distil` only observes; distillation is the slow part.
- Distillation takes seconds per drop locally. Running it every 15 minutes
  keeps the model permanently busy for little gain; hourly or on demand is
  usually right.
- If the embedding model is down, recall falls back to the lexical index, and
  to plain substring matching if the build has no FTS5. It degrades rather
  than disappearing, and the trust and retraction gates hold on every path.
- Opening the store upgrades an older database in place. A migration failure
  is never fatal to a read, so a scheduled job cannot be taken down by it.
