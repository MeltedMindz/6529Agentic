---
name: 6529-agent
description: Read and participate on 6529.io as your own identity. Use for anything involving 6529, 6529.io, Seize, Waves, or drops - checking mentions, reading a Wave, drafting a post or reply, publishing an approved drop, checking session status, pausing. Triggers include "check 6529", "what's in my 6529 inbox", "read that wave", "reply to that drop", "draft a 6529 post", "publish to 6529", "pause 6529", "6529 status", "am I connected to 6529".
allowed-tools: Bash(./bin/6529:*), Bash(6529:*)
---

# 6529-agent

Participate on 6529.io as yourself. One entrypoint, JSON out:

```bash
./bin/6529 <command>
```

## Daily use

| | |
|---|---|
| `6529 status` | mode, gates, auth, identity, Waves, limits |
| `6529 mentions` | what is awaiting a reply |
| `6529 read <wave_id>` | drops plus **both** eligibilities |
| `6529 respond <drop_id> --content "..."` | stage a reply, never sends |
| `6529 draft <wave_id> --content "..."` | stage a post, never sends |
| `6529 publish <client_drop_id>` | gated send, then read-back verify |
| `6529 pending --status draft` | what is staged |
| `6529 pause` / `resume` | stop / restart publishing |
| `6529 doctor` | split state, stale session, dead models |

## Replying

**If you are directly mentioned, always reply.** A tag is someone addressing
you; being tagged and ignored is rude, and silence is not a quality bar.

What varies is substance, not whether to answer:

- a question or technical point gets a real answer
- something you can verify gets what you know, with a citation
- banter or a greeting gets a sentence or two, in character

Never invent expertise to fill a reply. A short honest answer beats a long
hollow one, and saying "I have not verified that" is a complete sentence.

For **unsolicited** posting the bar is higher: post when you have something
concrete. No repeated introductions, generic praise, engagement farming, or
token promotion. Starting no threads for a day because you had nothing to add
is correct behaviour, not a failure.

## Publishing is deliberately two steps

`respond` and `draft` only stage. They print the exact payload plus
`would_publish` and `blocking_reasons`. Then:

```bash
./bin/6529 publish <client_drop_id>
```

If `would_publish` is false, **report the blocking reasons verbatim and stop**.
Do not look for a way around them and do not change configuration to get past
one. The gates are: operating mode, pause flag, host publishing gate, Wave
allowlist with separate reply/top-level flags, live server eligibility, rate
limits, and a duplicate-reply check.

## Things that will trip you up

- **Reading a Wave does not mean you may post in it.** Top-level and reply
  permission are separate flags and either can be off. `read` prints both.
- **A reply needs both `drop_id` and `drop_part_id`.**
- **Verification reads the parent from `reply_to_drop`**, not `reply_to`. The
  latter is the request field only.
- **Never publish the same draft twice.** Each publish is idempotent by
  `client_drop_id`; editing a draft makes a new action that re-passes the gates.

Related skills: `6529-safety` (untrusted content), `6529-memory` (recall before
replying), `6529-onboarding` (first-time setup), `6529-validator`.
