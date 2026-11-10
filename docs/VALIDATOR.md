# Running a 6529 validator

Verified **2026-11-07** against release `0.1.0-rc.10`, by downloading the Linux
x86-64 build, checking its SHA-256 against the signed release feed, and reading
the install guide shipped inside it (`docs/install/linux.md`,
`docs/install/operations.md`).

> **Correction.** An earlier version of this file said the validator was a
> desktop-only app with "no verified unattended install path". That was wrong.
> It ships as a **standalone CLI binary with a built-in systemd installer** and
> explicit support for headless servers and Raspberry Pis. Everything below is
> from the official docs in the release, not inferred.

## What it is

Once a day it computes everyone's TDH (TDH v1.4) from Ethereum and signs the
result with a key held on that machine.

Two things worth knowing up front, both stated by the project:

- **The validator key cannot move NFTs or funds.** It only signs TDH results.
- **Tor is on by default**, so Ethereum servers and other validators do not see
  your address.

Apache-2.0. The binary is `validator`; run `validator --help`.

## Keeping it current, unattended

From **rc.14** the validator installs its own updates - but only on Windows,
in the Mac app, and from the Linux `.deb`. A **tarball install under
`/usr/local`, run as a system service, is none of those** and will sit on an
old release indefinitely. If that is your shape, schedule this:

```bash
./scripts/auto-update-validator.sh --check   # report only
./scripts/auto-update-validator.sh           # update if there is one
```

```cron
30 8 * * *  cd /opt/6529Agentic && SUDO_ASKPASS=/path/to/askpass ./scripts/auto-update-validator.sh
```

What it refuses to do matters more than what it does:

- **It will not install an unverified build.** It calls
  `install-validator.sh`, which checks SHA-256 against `SHA256SUMS` *and* the
  signed feed, and stops on a mismatch.
- **It will not update while today's vote is due.** Signing comes first. If
  the ledger cannot be read at all it defers rather than proceeding blind -
  an unknown signing state is a reason to wait, not a reason to go.
- **It will not leave you on a broken release.** If the new binary will not
  report its version, the service will not come back, or its status is
  unreadable, the previous build is restored and the exit code says a human
  is needed. Builds install side by side, so rollback is a symlink change.

Exit codes: `0` current or updated and verified, `4` deferred (try later),
`5` needs a human.

### Root, with no terminal

Installing needs root, and cron has no terminal for `sudo` to prompt on.
Either give the cron user a `NOPASSWD` rule for the install, or point
`SUDO_ASKPASS` at a helper that prints the password:

```sh
#!/bin/sh
# reads it from a secret store at prompt time; never stored in the job,
# the environment, or a log
exec security find-generic-password -a "$USER" -s validator.SUDO -w
```

`chmod 700` it. Without one, the job says so and exits rather than failing
silently every morning.

### Choose the hour deliberately

Pick a time clear of both ends of the day: the validator signs shortly after
00:00 UTC and the day is final at 19:30 UTC. A restart in between is safe; one
just before finalisation is not worth the risk. 08:30 local worked for us.

## The signed release feed — the automation surface

`https://6529.io/validator/releases.json` (+ `releases.json.sig`)

This is the piece that makes agent-operated validators tractable. Verified live:

| field | value on 2026-11-07 | use |
|---|---|---|
| `sequence` | `1794058121` | change detection |
| `min_supported` | `0.1.0-rc.9` | **alert when your version drops below this** |
| `deadline` | `2026-11-08T00:00:00Z` | hard consensus cutover |
| `deadline_reason` | *"signed TDH counts only on the new chain…"* | why |
| `releases[].files[]` | `name`, `size`, `sha256` | verify before running |
| `checkpoints`, `beacon_checkpoint` | chain anchors | — |

The validator reads this itself once an hour, through Tor, and checks the
signature with 6529's key built into every release. Other validators relay the
same signed list, so you still hear about a release when 6529.io is unreachable.

**Nothing is ever downloaded or installed for you.** There are no automatic
updates by design (P36) — you decide, after reading the notes.

Artifacts live at a predictable path:

```
https://6529.io/validator/download/<version>/<filename>
```

e.g. `…/download/0.1.0-rc.10/validator-0.1.0-x86_64-unknown-linux-gnu.tar.gz`
(46,277,777 bytes, sha256 `7ed3affa…4f33c1` — matched the feed exactly).

Builds available: `x86_64`/`aarch64` Linux tarballs, `.deb` (amd64, arm64),
`.dmg`, `.msi`, `.exe`, `.AppImage`, plus macOS/Windows tarballs and
`SHA256SUMS`.

## Install, headless

Requires 64-bit Linux, **glibc 2.35+** (Ubuntu 22.04, Debian 12/13, Raspberry
Pi OS 64-bit Bookworm/Trixie, Fedora 36+), systemd, `sudo`, `curl`. Check with
`ldd --version | head -1`. Over SSH is explicitly fine.

```bash
VERSION=0.1.0
TARGET=$([ "$(uname -m)" = aarch64 ] && echo aarch64-unknown-linux-gnu \
                                     || echo x86_64-unknown-linux-gnu)
REL=0.1.0-rc.10          # read this from releases.json, do not hardcode
BASE=https://6529.io/validator/download/$REL

mkdir -p ~/validator-download && cd ~/validator-download
curl -fL -O "$BASE/validator-$VERSION-$TARGET.tar.gz"
curl -fL -O "$BASE/SHA256SUMS"

# Never run an unverified build.
grep " validator-$VERSION-$TARGET.tar.gz\$" SHA256SUMS | sha256sum -c -

tar -xzf "validator-$VERSION-$TARGET.tar.gz"
sudo mkdir -p /opt/6529-validator
sudo cp -R "validator-$VERSION-$TARGET" /opt/6529-validator/
sudo ln -sfn "/opt/6529-validator/validator-$VERSION-$TARGET/validator" \
             /usr/local/bin/validator
validator --version
```

The symlink is the upgrade seam: a new version only moves that pointer.

### Let the binary install its own service

```bash
sudo validator service install --dry-run   # see every change first
sudo validator service install
```

That creates the `validator6529` account (cannot log in), the data directory
`/var/lib/6529-validator` readable only by it, and a systemd unit
`6529-validator` locked down to the network and that directory. It does **not**
start yet — the data directory is empty.

```bash
sudo -u validator6529 validator init   --data-dir /var/lib/6529-validator
sudo -u validator6529 validator keygen --data-dir /var/lib/6529-validator \
     --label "closet pi"
sudo validator service install     # now enables and starts it
sudo validator service status      # expect: running
journalctl -u 6529-validator -f
```

`keygen` prints an 8-character key code. Your wallet shows the same 8
characters when it signs the grant — check they match. The key never leaves the
machine.

### Authorize the key (the one step needing a wallet)

```bash
sudo -u validator6529 validator grant sign-page \
     --data-dir /var/lib/6529-validator \
     --account 0xYOUR_WALLET --bind 127.0.0.1:6530 --no-open
```

It prints a **one-time** link including `?token=…`. Open that whole link in a
browser with your wallet. The bare address will not sign. On a headless box,
SSH-tunnel to it and open the link locally. Run the command again for a new
link.

## Monitoring — use the documented contract, not liveness

`validator status` has defined exit codes:

| exit | meaning |
|---|---|
| `0` | running, nothing needs you (including waiting for the day's data) |
| `5` | running, **something needs you** — an open AL1/AL2/AL3 alert, or a key/authorization still to make |
| `3` | not running (prints the last snapshot it wrote) |

```bash
validator status --json | jq .alerts
```

Alert levels: **AL1** needs you now, **AL2** today, **AL3** worth a look, **AL4**
information (DEBUG log only).

A process-liveness check is not coverage here — exit `5` means the process is
healthy *and* not counting. Alert on **non-zero**, and separately on
`min_supported` from the feed moving past your installed version.

Common states: `WAITING_FINALITY` (normal, clears ~00:15 UTC), `WAITING_SOURCE`
(no Ethereum server answering), `WAITING_HISTORY` (no certified day yet),
`CLOCK` (system clock off by >1 min), `NOT_GRANTED` (no grant for this key).

`EXCLUDED` / `KEY_EXCLUDED` is the one to avoid: it means a **double vote** —
the same key ran on two machines, or was stolen. The excluded grant's keys
*never count for that account again*. Hence the rule in the README: keep the
data folder on one computer, never copy it. On a new machine, install fresh.

## Deadlines are real

- **2026-11-08 00:00 UTC** — signed TDH counts only on the new chain; needs
  rc.9 or rc.10.
- **2026-12-01** — *"Release 0.1.0 must be upgraded before 2026-12-01."* It
  checks Ethereum blocks only up to that date, ahead of Ethereum's next upgrade
  changing block headers. A validator still on 0.1.0 after that **stops signing**.

Poll `min_supported` and `deadline` from `releases.json` and alert ahead of
them. Keep the previous version's folder until the new one has signed a day, so
you can roll back.

## For an agent operator

The honest shape of this: everything except the wallet grant is scriptable, and
the project deliberately keeps installation a human decision.

1. Dedicated always-on box. A Raspberry Pi 4/5 is explicitly supported; the
   ARM64 tarball is 45 MB.
2. Install and grant once, by hand. The grant needs a wallet signature.
3. Poll `releases.json` on a schedule. Alert on `sequence` change,
   `min_supported` above your version, or an approaching `deadline`.
4. Poll `validator status` and alert on exit `5` or `3`.
5. Upgrade deliberately: verify SHA-256 against the feed, move the symlink,
   restart, confirm it signs a day, then retire the old folder.
6. Never copy the data directory to a second machine.

Do not automate the download-and-install end to end just because you can. The
project chose no auto-updates; an agent that silently installs releases is
working against that, and a bad upgrade that double-signs costs the account
permanently.

## Managing it from this repo

`src/agent6529/validator.py` wraps the binary and the feed so an agent can
monitor and upgrade without a browser.

```bash
PYTHONPATH=src python3 -m agent6529.cli validator release   # feed vs installed
PYTHONPATH=src python3 -m agent6529.cli validator status    # local health
PYTHONPATH=src python3 -m agent6529.cli validator watch     # one verdict, for cron
PYTHONPATH=src python3 -m agent6529.cli account <handle>    # TDH, REP, cards
```

`validator watch` exits **0** when healthy and **5** when something needs you —
local alert, version below `min_supported`, or an approaching deadline — so it
drops straight into a scheduler.

Two deliberate limits in the code:

- `check_release()` tells you an upgrade is due. It does not install one. The
  project ships no auto-updates on purpose, and `plan_upgrade()` returns the
  steps for a supervised run rather than executing them.
- `download_release()` **refuses to return a path** whose SHA-256 does not
  match the signed feed, and deletes the bad file. An unverified build is never
  handed to a caller.

## The grant, headless

`grant sign-page` needs a browser. `grant draft` + `grant import` do not:

```bash
validator grant draft --account 0xWALLET --key <keycode> --json
# -> writes grants/<account>-<n>.typed-data.json  (EIP-712 ValidatorGrant)
```

Sign that typed data with any signer supporting `eth_signTypedData_v4`, then:

```bash
validator grant import --signature 0x...
```

The grant is EIP-712 typed data naming **no chain**, so it signs offline, costs
nothing, and moves no NFTs or funds. The validator must be running first — it
supplies the recent finalized Ethereum block the draft references.

**Verified caveat:** Bankr's API signs `personal_sign` freely but returns
`403 Contract calls need MFA` for `eth_signTypedData_v4` until MFA and contract
calls are enabled in its security settings. Check your signer can do typed data
*before* planning a headless grant.

## TDH is earned, not granted

A validator's weight is the TDH of the account that grants it, so a grant from
an account with `tdh: 0` runs correctly and counts for nothing.

TDH accrues **per day of holding** — receiving a card does not grant TDH
immediately. `6529 account <handle>` surfaces this directly: it reports
`memes_balance` alongside `tdh` and says so when an account holds cards but has
not accrued yet. Cards are at
[thememes.exchange](https://thememes.exchange/memes/max-tdh) and
[the collection on OpenSea](https://opensea.io/collection/thememes6529).

## Two things upgrading teaches you

**1. A release can be urgent while your version is still "supported".**

On 2026-11-08, rc.12 shipped flagged `severity: urgent` — it fixed validators
joining the new chain for the first time, which could not load the network's
history. But `min_supported` was still `rc.9`, so a checker that only compares
versions against `min_supported` reports everything fine while the validator
itself prints an urgent banner.

The feed carries `severity` and `reason` **per release**. Read both:

```bash
./bin/6529 validator release   # surfaces severity alongside min_supported
./bin/6529 validator watch     # exits 5 on either signal
```

**2. The release folder name does not change between releases.**

Both rc.10 and rc.12 unpack to `validator-0.1.0-<target>`, because the file
version is `0.1.0` for the whole rc line. Copying the new one into place
**overwrites the old one**, so the usual "keep the previous folder until the
new one has signed a day" advice silently does nothing. Rename first if you
want a real rollback:

```bash
sudo mv /usr/local/6529-validator/validator-0.1.0-<target> \
        /usr/local/6529-validator/validator-0.1.0-<target>.rc10
```

## Why a freshly authorized key may still not sign

A grant can be **in force** and the key still not count. `validator status
--verbose` is explicit about which input is missing:

```
key 2ac47d8c: not signed: no authorization listed the key that day
  authorized by 0xef2c…1c75, but not counted today:
  0xef2cc7d1… holds no TDH
```

That is not a broken grant. TDH is counted in **whole days held** against a
daily snapshot taken just after 00:00 UTC. A card received at 18:23 UTC has
been held 5.7 hours at the next snapshot, which is zero full days, so the
account has no TDH and the key has nothing to weight. One more daily cycle
fixes it.

Check both numbers together:

```bash
./bin/6529 account <handle>     # tdh alongside memes_balance
```

`tdh: 0` with `memes_balance: 1` is the expected state on day one, and the
command says so rather than leaving you to guess.
