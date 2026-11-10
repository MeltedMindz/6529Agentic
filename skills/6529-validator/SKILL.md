---
name: 6529-validator
description: Install, authorize, monitor and upgrade a 6529 validator, which recomputes TDH from Ethereum daily and signs it. Use for validator setup, health checks, release deadlines, grants, and TDH questions. Triggers include "install the validator", "is my validator healthy", "validator status", "do I need to upgrade", "authorize my validator key", "sign the grant", "why is my TDH zero", "validator deadline".
allowed-tools: Bash(./bin/6529:*), Bash(6529:*), Bash(validator:*), Bash(./scripts/install-validator.sh:*)
---

# 6529-validator

A validator recomputes everyone's TDH from Ethereum once a day and signs the
result. It stakes nothing, and **its key cannot move NFTs or funds**. Tor is
on by default.

## Monitor

```bash
./scripts/auto-update-validator.sh  # stay on the current release, safely
./bin/6529 validator watch     # exit 0 healthy, 5 needs attention
./bin/6529 validator status    # local health
./bin/6529 validator release   # installed vs the signed feed
```

**Alert on non-zero exit, never on the process being alive.** `validator
status` exits `5` when the process is perfectly healthy *and not counting* — a
liveness check cannot see that.

| exit | meaning |
|---|---|
| `0` | running, nothing needs you |
| `5` | running, an open AL1/AL2/AL3 alert or a missing key/grant |
| `3` | not running |

If status cannot read the data directory, that is a permissions note, not an
alarm: the directory is mode 0700 and owned by the service account. The tool
prints the exact `sudo -u …` command to use.

## Install

```bash
./scripts/install-validator.sh --check   # what release, what machine, no changes
./scripts/install-validator.sh           # download, VERIFY sha256, install
```

The installer reads the signed release feed, verifies the digest against both
`SHA256SUMS` and the feed, and **refuses to install on a mismatch**. It stops
before touching system services so you can read `validator service install
--dry-run` first.

Then:

```bash
sudo validator service install --dry-run
sudo validator service install
sudo -u <svc user> validator init   --data-dir <data dir>
sudo -u <svc user> validator keygen --data-dir <data dir> --label "this machine"
sudo validator service install      # again: now it starts
```

## The grant

A key signs nothing until a wallet of the account authorizes it. The grant is
**EIP-712 typed data**, names no chain, costs nothing, and moves nothing.

Headless, no browser:

```bash
validator grant draft --account 0xWALLET --key <keycode> --json
# sign the typed-data file with eth_signTypedData_v4
validator grant import --account 0xWALLET --signature 0x...
```

Or `validator grant sign-page` for the browser path.

The validator must be running first — it supplies the finalized Ethereum block
the draft references.

## TDH is earned, not granted

A validator's weight is the TDH of the account that granted it.

**TDH accrues per day of holding, not on receipt.** An account that just got
its first card shows `memes_balance: 1` and `tdh: 0`, and the validator will
refuse to draft a grant for it:

> *"holds no TDH on <date> … an authorization it signs wouldn't count"*

That is correct behaviour. Wait for the next daily computation.
`./bin/6529 account <handle>` reports both numbers and says so.

The same applies **after** a grant is in force. `status --verbose` may show
the key authorized but "not counted today: holds no TDH". The grant is fine;
the account simply had no TDH at that day's snapshot. TDH counts whole days
held against a snapshot just after 00:00 UTC, so a card received during the
day contributes nothing until the following cycle.

## Urgency is not only min_supported

A release can be flagged `severity: urgent` while your installed version is
still at or above `min_supported`. Comparing versions alone misses it. The
feed carries `severity` and `reason` per release, and `validator release`
surfaces both; `validator watch` exits 5 on either signal.

When upgrading, note that releases in the same line unpack to the **same**
folder name, so copying the new one over the old destroys your rollback. Move
the old folder aside first if you want one.

## Deadlines are real

Poll `min_supported` and `deadline` from the release feed and alert **ahead**
of them. A version below `min_supported` stops counting. Keep the previous
version's folder until the new one has signed a day, so you can roll back.

## The one unrecoverable mistake

**Never copy a validator data directory to another machine.** Two machines
signing with one key is a double vote, and the excluded grant's keys *never
count for that account again*. On a new machine, install fresh and make a new
key.

## Staying current without being asked

From rc.14 the validator installs its own updates, but only on Windows, in
the Mac app, and from the Linux `.deb`. A tarball install run as a system
service is none of those and will sit on an old release forever, which is how
a validator quietly drops below `min_supported` and stops counting.

`scripts/auto-update-validator.sh` is the daily job for that shape. It
verifies the SHA-256 against the signed feed, **defers while the day's vote is
still due** - and defers rather than guessing if it cannot read the ledger at
all - and restores the previous build if the new one will not start or its
status is unreadable. Builds install side by side, so a rollback is a symlink
change.

Exit `0` current or updated, `4` deferred, `5` a human is needed. Alert on 5.

Do not report an update as done without reading back the version and the
service state. The point of the job is that nobody is watching.
