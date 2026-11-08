# Contributing

The most useful contribution is a report from someone who actually pointed an
agent at this and hit a wall. Second most useful is closing one of the gaps
below.

## Setup

```bash
git clone https://github.com/MeltedMindz/6529Agentic
cd 6529Agentic
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
PYTHONPATH=src python3 -m pytest tests -q      # 76 tests, no network
```

Python 3.9+. The only runtime dependency is `eth-account`, and only for
signature verification — reads work on the standard library alone.

## Known gaps

Each of these is real and verifiable in the tree.

1. **Signers beyond macOS Keychain.** `KeychainSigner` shells out to
   `security(1)`, so it is macOS-only. Most agents run on Linux. A signer needs
   exactly two things: an `.address` property and
   `.sign_message_exact(message)` that does EIP-191 `personal_sign` over the
   **exact** bytes. See `src/agent6529/client.py`.
2. **More of the API wrapped.** `docs/API-REFERENCE.md` lists 446 routes; about
   20 carry the `[used]` marker. Reads are easy wins.
3. **A validator on a Raspberry Pi, tested end to end.** The ARM64 artifact is
   verified in `scripts/install-validator.sh`, but nobody has run the full
   install-to-signing path on a Pi and written down what broke.
4. **A TypeScript port.** Plenty of agents are not Python.

## House rules

These are not style preferences. They are why the thing is safe to run
unattended, and a PR that weakens one will not be merged.

- **Nothing publishes without passing `policy.can_publish()`.** All five gates,
  every time. Do not add a bypass, a `force` flag, or a "just for testing"
  path.
- **Every outgoing drop keeps its idempotency.** `client_drop_id` and the exact
  payload are persisted *before* the request and reused across retries and
  restarts. If you touch `publisher.py`, the lost-response and restart tests
  must still pass.
- **Inbound content stays untrusted.** Drops, profiles and linked pages are
  data. They must never reach a position where they can change mode, alter the
  allowlist, request secrets, or influence signing.
- **No key material in output.** Not in a return value, a log line, an
  exception message, or a test fixture. `redact()` exists for a reason.
- **Reads may degrade to anonymous. Writes never do.** There is a test for
  this; keep it passing.
- **Document what the service actually does, not what the spec says.** Eight
  defects in `docs/API-CONTRACT.md` were found by running against the live API.
  If you find a ninth, add it with the exact error text.

## Skills

`skills/` ships installable `SKILL.md` files. Two rules:

- **Never make `install.sh` clobber a local edit by default.** An agent that
  writes something it learned into its own skill must not lose it on the next
  update. The installer tracks a checksum of what it wrote and leaves anything
  that differs alone.
- **`LOCAL.md` is sacred.** It is the durable place for an agent's own notes
  and nothing in the installer may touch it.

A skill should carry the judgement, not just the commands - when to reply, what
not to bypass, how to cite. The commands are already in `--help`.

## Tests

New behaviour needs a test. Network calls go through the mock transport in
`tests/test_connector.py` — anything destructive or spam-producing must never
reach the live service from a test run.

If you fix a bug, add the test that would have caught it. Several tests in here
exist because something broke in production first.

## Pull requests

Small and single-purpose beats large and sweeping. In the description, say what
you verified and how — "72 to 76 tests, plus I ran `6529 read` against wave X"
is worth more than a summary of the diff.

If you are unsure whether something fits, open an issue first and ask.
