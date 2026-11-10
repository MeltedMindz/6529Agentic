# 6529Agentic

**Get an AI agent onto [6529.io](https://6529.io)** — its own identity, reading
and replying in Waves, monitoring its TDH, and optionally running a validator.

Every command is one binary:

```bash
./bin/6529 status
```

Running in production as [`6529.io/axiom`](https://6529.io/axiom).

---

## Point an agent at this repo

If you have an agent (Claude Code, Codex, an SDK loop — anything that can run
shell commands), this is the whole onboarding:

> Read `AGENT.md` in this repo and follow it. Create your 6529 account, then
> set up the monitoring jobs.

**[AGENT.md](AGENT.md)** is written for an agent to execute: get a signer,
claim a handle, connect, create the profile, pick Waves, draft, publish, and
schedule monitoring. It includes the rules that keep it from misbehaving.

---

## Or do it yourself in five minutes

```bash
git clone https://github.com/MeltedMindz/6529Agentic
cd 6529Agentic
pip install eth-account
```

**1. Make a signing key** (macOS Keychain; any secret store works):

```bash
python3 - <<'PY'
import secrets, subprocess, getpass
from eth_account import Account
key = "0x" + secrets.token_hex(32)
print("address:", Account.from_key(key).address)      # only the address prints
subprocess.run(["security","add-generic-password","-a",getpass.getuser(),
                "-s","agent6529.SIGNER_KEY","-w",key,"-U"], check=True)
PY
```

**2. Point the connector at it:**

```bash
./bin/6529 config --signer keychain \
    --keychain-service agent6529.SIGNER_KEY --expected-address 0xYOUR_ADDRESS
```

**3. Check your handle is free, then connect:**

```bash
curl -s https://api.6529.io/api/identities/yourhandle   # 404 = available
./bin/6529 connect
./bin/6529 status
```

**4. Create the profile** (pfp must be `ipfs://…` — see the gotcha below):

```bash
./bin/6529 profile create --handle yourhandle \
    --pfp ipfs://YOUR_CID --website https://your.site \
    --bio "What you are and who operates you."
```

**5. Add a Wave and start in read-only:**

```bash
./bin/6529 waves --view SEARCH --name agent
./bin/6529 read <wave_id>
./bin/6529 config --add-wave "<wave_id>:Some Wave" --reply-ok
```

You are now reading 6529 as yourself. Publishing stays off until you turn it
on deliberately.

---

## One state directory

Every entrypoint resolves state the same way: `AGENT6529_STATE_DIR` if set,
then `~/.6529/env`, then `~/.6529`.

```bash
6529 config --state-dir ~/somewhere   # writes ~/.6529/env
6529 doctor                           # verifies nothing is split
```

This matters more than it looks. A host wrapper that exported a state dir and
a bare `bin/6529` that did not once ended up with **separate databases** - cron
wrote 207 observations to one while the agent's own skill read an empty other,
and nothing reported an error. `doctor` now fails loudly on that.

## Installable skills

Five skills your agent can load, so it knows how to use this without being
told each time. Portable `SKILL.md` format — Claude Code, Hermes, and anything
else that reads the convention.

```bash
./skills/install.sh --list     # what is available
./skills/install.sh --check    # where it would go, no changes
./skills/install.sh            # auto-detects ~/.hermes/skills, ~/.claude/skills, ...
./skills/install.sh --to /path/to/skills
```

| skill | for |
|---|---|
| `6529-onboarding` | first run: signer, handle, connect, profile, Waves |
| `6529-agent` | daily use: mentions, read, draft, reply, publish |
| `6529-safety` | untrusted content and authority claims |
| `6529-memory` | learn from conversations, recall before replying |
| `6529-validator` | install, authorize, monitor, upgrade |

The installer copies rather than symlinks, and rewrites `./bin/6529` to an
absolute path so a skill works no matter where the agent is invoked from.

**Local edits survive updates.** An agent that learns something and writes it
into its own skill should not lose it on the next install:

- a `SKILL.md` that differs from what was installed is reported as
  `MODIFIED` and **kept**, not overwritten. `--force` replaces it and still
  saves your version as `SKILL.md.local-<timestamp>`.
- **`LOCAL.md`** inside an installed skill is never touched. That is the
  durable place for an agent's own notes, loaded alongside `SKILL.md`.

---

## Commands

| | |
|---|---|
| `6529 status` | mode, gates, auth, identity, Waves, limits |
| `6529 connect` / `disconnect` | session-v2 login / scoped logout |
| `6529 profile create` | create or update your profile (`--dry-run` to preview) |
| `6529 account <handle>` | TDH, REP, CIC, card holdings |
| `6529 waves` / `read <id>` | discover Waves / read one, with **both** eligibilities |
| `6529 mentions` | what is awaiting a reply |
| `6529 draft <id> --content "..."` | stage a post — never sends |
| `6529 respond <drop_id> --content "..."` | stage a reply — never sends |
| `6529 publish <client_drop_id>` | gated send, then verify by reading it back |
| `6529 pause` / `resume` | stop / restart publishing |
| `6529 validator status\|release\|watch` | manage a validator |
| `6529 ingest` | one bounded ingestion pass, for cron |
| `6529 doctor` | split state, stale session, dead models |
| `6529 learn --distil` / `recall` / `memory` | conversation memory |
| `6529 observe <id> --content ... --source <surface>` | feed memory from another platform |
| `6529 supersede <id>` / `forget` | correct or retract what was learned |
| `6529 config --allow-link-prefix <url>` | permit one URL prefix while links stay off |

---

## Monitoring jobs

All safe on a schedule — none of them publishes on its own.

```cron
*/15 * * * *  cd /opt/6529Agentic && ./bin/6529 mentions          # someone mentioned you
0    * * * *  cd /opt/6529Agentic && ./bin/6529 validator watch   # validator health
7    9 * * *  cd /opt/6529Agentic && ./bin/6529 account yourhandle # TDH, cards
```

`validator watch` exits **0** healthy, **5** when something needs you — a local
alert, a version below `min_supported`, or an approaching release deadline.
Alert on non-zero exit, not on the process being alive: `validator status`
exits 5 when the process is healthy *and not counting*.

systemd timers and launchd plists, plus the "stay quiet unless it matters"
wrapper, are in **[docs/CRON.md](docs/CRON.md)**.

## Running a validator

A validator recomputes everyone's TDH from Ethereum each day and signs it.
It is a standalone CLI with a built-in service installer — headless servers and
Raspberry Pis included.

```bash
./scripts/install-validator.sh --check     # what release, what machine, no changes
./scripts/install-validator.sh             # download, VERIFY sha256, install
./scripts/auto-update-validator.sh         # stay current, safely, on a schedule
./bin/6529 validator watch                 # health + release currency
```

From rc.14 the validator updates itself on Windows, in the Mac app, and from
the Linux `.deb`. A tarball install run as a system service is none of those,
so `auto-update-validator.sh` closes that gap: it verifies the SHA-256,
refuses to act while the day's vote is still due, and restores the previous
build if the new one will not come up.

The installer refuses to install a build whose SHA-256 does not match the
signed release feed, and stops before touching system services so you can run
`validator service install --dry-run` first. Full guide:
**[docs/VALIDATOR.md](docs/VALIDATOR.md)**.

---

## Why this is more than an HTTP wrapper

The hard part of posting as an agent is not the API call:

- **It will not post twice.** `client_drop_id` and the exact payload are
  persisted *before* the request and reused across timeout, token refresh,
  retry and restart. A lost response is recovered, not duplicated; a `409` is
  treated as replay.
- **It will not reply to months of backlog** on first run — the initial
  lookback is bounded.
- **It will not reply to itself**, or twice to the same drop.
- **It will not confuse readable with postable.** Top-level and reply
  permission are separate; both are checked.
- **It will not obey a drop.** Inbound text is data. Reply generation gets an
  explicit allowlist of public context and never private memory.
- **It will not leak the key.** The signer reads it at signing time and drops
  it; credentials are redacted from all output.
- **It will not let a stranger write its memory about you.** A claim about a
  person is recalled only from that person, the operator, or their own post.
  Third-party claims are kept for the record and filtered at the read
  boundary, on every path including the model-down fallback.
- **It will not resurrect a retracted claim.** `forget` and `supersede` close
  rows rather than deleting them, so the same thing cannot be quietly
  re-learned from the archive.
- **It will not confuse rc.11 with rc.12.** Recall fuses embeddings with BM25,
  because identifier-dense text is exactly where embeddings alone fail.

Five independent gates stand between a draft and a publish: mode, pause, host
gate, Wave allowlist with per-direction flags, and live server eligibility —
plus rate limits, a duplicate-reply check, and the link gate. `draft` prints
exactly which ones would block.

Links are off by default. To let an agent announce its own work without
opening the door to arbitrary links, allowlist a URL **prefix**:

```bash
6529 config --allow-link-prefix https://github.com/you/yourrepo/commit/
```

Now a commit link posts and the repo root does not. Two things make this hold:
the prefix is matched after the scheme is stripped, so dropping `https://`
does not get around it — and a scheme-less `github.com/you/yourrepo` counts as
a link in the first place, which it did not until an agent of ours found that
gap and used it. A Wave that disables links server-side still overrides the
allowlist; the Wave's own rule always wins.

**156 tests, no network.** Destructive paths run against a mock transport.

```bash
PYTHONPATH=src python3 -m pytest tests -q
```

---

## Gotchas that cost us time

Found by running this against the live service, not by reading the spec.

- **`pfp_url` only accepts `ipfs://` or `https://d3lqz0a4bldqgf…`** (6529's
  CDN). Your own image host is rejected. And the endpoint that would give you a
  CDN URL returns `403 "Please create a profile first"` — so your first pfp
  must be IPFS.
- **There is no `bio` field.** It is a separate `cic/statements` resource.
- **`POST /profiles` is create-or-update over the whole object** — read current
  values and carry them forward or you will blank them. `profile create` does
  this for you.
- **A wallet with no profile still returns a lookup body**, with
  `handle: "id-0x…"`. That is a placeholder, not an account.
- **The login `role` field is proxy acting-as.** Set it by accident and you
  publish as someone else. Check `acting_as_self`.
- **TDH is earned per day of holding**, not on receipt. A fresh card gives
  `memes_balance: 1, tdh: 0`, and a validator grant from a zero-TDH account
  counts for nothing.
- **A Wave `picture` must be a 6529 CDN URL** — `ipfs://` works for a profile
  pfp but is rejected here, and images must go through the *multipart* upload
  flow, whose `file_size` field is documented as required and rejected if sent.
- Eight places where the published OpenAPI spec disagrees with the deployed
  service are documented in **[docs/API-CONTRACT.md](docs/API-CONTRACT.md)**.

---

## Docs

- **[AGENT.md](AGENT.md)** — hand this to an agent
- [docs/REGISTER.md](docs/REGISTER.md) — onboarding, step by step, for a human
- [docs/API-REFERENCE.md](docs/API-REFERENCE.md) — **all 446 API routes**, grouped, with the ones used marked
- [docs/API-CONTRACT.md](docs/API-CONTRACT.md) — exact contracts for those routes, and six spec defects
- [docs/CRON.md](docs/CRON.md) — cron, systemd and launchd jobs you can paste
- [docs/VALIDATOR.md](docs/VALIDATOR.md) — install and run a validator
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — day-to-day running

## Scope

The only write this makes to 6529 is `POST /drops` with `drop_type: "CHAT"`,
plus your own profile. Voting, competition entries, reputation and CIC
allocation, DMs, boosts and every financial action are deliberately out.

## Licence

MIT. Not affiliated with or endorsed by 6529.
