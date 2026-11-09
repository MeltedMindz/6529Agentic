---
name: 6529-memory
description: Learn from 6529 conversations and recall prior context before replying. Use when you want to remember what someone said, build on an earlier conversation, check what you know about a person or topic on 6529, or distil what you have read. Triggers include "what do I know about", "what did they say before", "remember this conversation", "learn from the wave", "recall", "have we discussed this".
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
```

`respond` already recalls automatically and returns `prior_context` alongside
the staged draft.

## Three separate jobs

| | |
|---|---|
| **observe** | keep what was said, verbatim, with provenance |
| **learn** | distil durable claims using a **local** model |
| **recall** | find what is relevant now |

Embedding and extraction run against local Ollama models, so public forum
content never leaves the machine and memory costs no API calls per drop.

## How to use recall in a reply

Recall returns claims with a citation string:

```
[0.476] Every day at 01:30 UTC this repository fetches every TDH entry
        from api.6529.io (@eduardocruz in 6529 for Developers)
```

- **Attribution is not endorsement.** A note records that someone *said*
  something, not that it is true. Say "eduardocruz mentioned that…", not
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
- If the embedding model is down, recall falls back to keyword matching rather
  than returning nothing.
