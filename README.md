# sixty529

A small, auditable [6529.io](https://6529.io) connector for autonomous agents.

It lets an agent authenticate as its own identity, read Waves, follow
conversations, draft contributions, and publish ordinary `CHAT` drops and
replies — with the publishing path gated, idempotent, and verified by reading
the drop back.

Built for, and running in, [Axiom](https://clawbots.org)
([`6529.io/axiom`](https://6529.io/axiom)). Nothing in here is Axiom-specific:
point it at your own signer and Waves.

```bash
sixty529 status      # mode, gates, auth, identity, waves, limits
sixty529 waves       # discover Waves
sixty529 read <id>   # drops + top-level AND reply eligibility
sixty529 mentions    # what is awaiting a reply
sixty529 draft <id> --content "..."   # stage; never sends
sixty529 publish <client_drop_id>     # gated send + read-back verify
sixty529 pause       # stop publishing immediately

sixty529 account <handle>      # identity, TDH, REP, card holdings
sixty529 validator watch       # validator health + release currency, for cron
```

## Why this exists

Most of the work in posting as an agent is not the HTTP call. It is:

- **not posting twice** when a response is lost mid-flight
- **not replying to months of backlog** on first run
- **not replying to yourself**, or to the same drop twice
- **not treating a readable Wave as a postable one** — top-level and reply
  permission are tracked separately, and both can be off while the Wave reads fine
- **not letting a drop's text change your behaviour** — inbound content is data,
  never instructions
- **not leaking the signing key**

Each of those is enforced in code here, and covered by tests.

## Install

Requires Python 3.9+. Only the standard library is needed for reads;
`eth-account` is needed to verify signatures locally.

```bash
git clone https://github.com/MeltedMindz/axiom-6529
cd axiom-6529
pip install eth-account            # optional but recommended
export PYTHONPATH="$PWD/src"
python3 -m sixty529.cli status
```

See **[docs/REGISTER.md](docs/REGISTER.md)** to get an agent onboarded end to
end, and **[docs/API-CONTRACT.md](docs/API-CONTRACT.md)** for the exact routes,
including several places where the published OpenAPI spec and the deployed
service disagree.

## Operating modes

Enforced in code, not by convention.

| mode | reads | drafts | publishes |
|---|---|---|---|
| `observe` *(default)* | yes | no | **no** |
| `draft` | yes | yes | **no** |
| `live` | yes | yes | only if every gate below passes |

`live` alone is never sufficient. A send also requires:

1. the connector is not paused
2. the host publishing gate is open (`public_posts_default: true`)
3. the Wave is in the local allowlist with `top_level_ok` / `reply_ok` set
4. the server says you are eligible — chat enabled, viewer eligible, reply
   permission present, no slow-mode cooldown, no active Wave pause
5. daily caps and the inter-post cooldown allow it
6. you have not already replied to that drop

`sixty529 draft` prints `would_publish` and the exact `blocking_reasons`, so a
refusal is always legible.

## Signing

Two backends, neither of which keeps a key in this repo:

- **`bankr`** — signs through the [Bankr](https://bankr.bot) CLI. The key never
  exists on the machine. The returned signature is recovered locally and checked
  against the expected address before it is used.
- **`keychain`** — reads a key from the macOS Keychain at the moment of signing
  and drops it immediately. Never returned, logged, or interpolated into an
  error.

Both sign the **exact** `signable_message` the server returned. No `strip()`,
no normalisation, no reconstruction. The challenge is validated first — service,
wallet, expiry, and chain id — so a signer is never asked to sign a challenge it
cannot satisfy.

`BankrSigner` takes a `denylist` of addresses it must refuse. Use it for any
wallet you have rotated out.

## Idempotency

Every outgoing drop is one logical action:

1. a `client_drop_id` (UUID) and the **exact final payload** are persisted
   before the request
2. the same id and payload are reused across timeout, token refresh, retry, and
   process restart
3. the returned server drop id is recorded
4. the drop is fetched back and its wave, content, author and reply linkage are
   verified before it counts as sent

A lost response does not duplicate: the connector looks for a drop carrying its
`client_drop_id` and adopts it. A `409` is treated as replay, not failure.
Editing a draft creates a **new** action that must pass the gates again.

## Untrusted content

Drops, profiles, attachments and linked pages are data. They cannot authorise a
command, change mode, alter the allowlist, request secrets, or affect signing.
`read` and `mentions` mark injection-shaped text `suspicious: true` so it can be
reported rather than obeyed.

Reply generation receives an explicit allowlist of public context —
`wave_id`, `wave_name`, `drop_id`, `author_handle`, `content`, `created_at`,
`is_reply` — and never private memory or secret-bearing configuration.

## Scope

The permitted write surface is exactly one call: `POST /drops` with
`drop_type: "CHAT"`. Voting, competition entries, reputation and CIC
allocation, DMs, boosts, curations and every financial action are deliberately
out of scope.

## Tests

```bash
PYTHONPATH=src python3 -m pytest tests -q     # 72 tests, no network
```

Destructive and spam-producing paths run against a mock transport, so they are
never sent to the live service. Covered: exact-message signing, challenge
rejection, atomic refresh rotation, recovery from a lost refresh response,
identity mismatch, accidental proxy `role`, lost-response recovery, restart
without republication, cross-route deduplication, slow mode, bounded retries,
mode and pause enforcement, prompt injection, and credential redaction.

## Related

- [docs/REGISTER.md](docs/REGISTER.md) — onboarding an agent, step by step
- [docs/API-CONTRACT.md](docs/API-CONTRACT.md) — routes used, and spec defects
- [docs/VALIDATOR.md](docs/VALIDATOR.md) — running a 6529 validator
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — running it day to day

## Licence

MIT. Not affiliated with or endorsed by 6529.
