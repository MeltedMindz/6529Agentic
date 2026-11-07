# Running a 6529 validator

Notes from a live inspection on **2026-11-07**. Treat version numbers and dates
as a snapshot — re-check <https://6529.io/validator> before acting.

## What it is

> *"It runs on your computer, computes each day's TDH from Ethereum and signs
> it."* — 6529.io/validator

TDH (Total Days Held) is 6529's holder-weighting metric. The validator
independently recomputes it from Ethereum rather than trusting the API, then
signs the result. Consensus is reached when accounts holding more than **2/3 of
validating TDH** run a current release and have signed.

This is a *verification* role, not a blockchain node and not a mining role. It
does not require holding anything to run, but your signature only carries
weight proportional to the TDH of the accounts you control.

## Current release

As of 2026-11-07 the download page advertises **0.1.0-rc.10**, a desktop
application:

| platform | requirement | size |
|---|---|---|
| macOS | 11 or newer, Apple silicon or Intel | 89.4 MB |
| Windows | 10 or 11, 64-bit | 36.3 MB |
| Linux x86-64 | Ubuntu 22.04 / Debian 12 or newer | 29.4 MB |
| **Linux ARM64** | **Raspberry Pi 4/5, other ARM64** | **27.2 MB** |
| Linux AppImage | other desktops, *runs only while open* | 43.2 MB |

There was a scheduled consensus change on **Sunday 8 November 2026, 00:00 UTC**,
after which signed TDH counts only on the new chain. rc.9 and rc.10 both handle
it; rc.8 and older had to update first. That pattern — a dated switch requiring
a minimum release — is the thing to watch for operationally.

## Why this is awkward for an agent, honestly

The validator ships as a **desktop app**, not a daemon or container. The
download page is JavaScript-rendered and exposes no direct artifact URLs to
scrape, and there is no published package repository, Docker image, or
`validator --headless` flag that I could verify.

Two adjacent repositories exist under
[6529-Collections](https://github.com/6529-Collections) but **neither is the
validator**, and both are stale relative to rc.10:

| repo | language | last updated |
|---|---|---|
| `6529-Prenode` | TypeScript | 2025-07-02 |
| `6529node` | Go | 2025-03-07 |

So: there is no verified fully-unattended install path today. Anyone claiming
otherwise should be asked for the artifact URL.

## The practical path for an agent-operated validator

The Linux x86-64 and ARM64 builds are ordinary desktop binaries, which is what
makes this tractable. A Raspberry Pi 4/5 at 27.2 MB is the cheapest honest
option.

1. **Dedicated host.** A small always-on Linux box or Pi. The validator must be
   running to sign each day, and the AppImage variant explicitly *"runs only
   while open"* — prefer the `.deb`-style build over the AppImage for anything
   unattended.

2. **A real session.** Desktop builds generally expect a display. On a headless
   box, run it under a virtual one:

   ```bash
   sudo apt install -y xvfb
   xvfb-run -a /path/to/6529-validator
   ```

   Verify it actually signs under `xvfb` before trusting it — a GUI app can
   start cleanly and still not complete work without a compositor.

3. **Supervise it, don't babysit it.** A `systemd` user unit with
   `Restart=always` is the right shape:

   ```ini
   [Unit]
   Description=6529 Validator
   After=network-online.target

   [Service]
   ExecStart=/usr/bin/xvfb-run -a /opt/6529/validator
   Restart=always
   RestartSec=30

   [Install]
   WantedBy=default.target
   ```

   ```bash
   systemctl --user enable --now 6529-validator
   loginctl enable-linger "$USER"   # survive logout
   ```

   `enable-linger` matters: without it a user service dies with the login
   session — the same failure mode that silently takes down agent runtimes.

4. **Monitor the thing that actually degrades.** Not "is the process up" — a
   validator that is running but has not signed today is indistinguishable from
   a healthy one unless you check signing. Assert on **last successful signature
   date**, and alert when it falls behind by a day. A liveness check alone is
   not coverage.

5. **Watch for release deadlines.** Consensus switches have hard dates. Track
   the releases page and alert on a new minimum version, rather than discovering
   it after your signature stopped counting.

## Key handling

The validator signs with a key tied to the accounts whose TDH you are
attesting. Same rules as everywhere else in this repo:

- never put that key on a cloud host, in an environment variable on a
  third-party platform, or in a repository
- prefer a dedicated key that holds nothing beyond what it attests
- if a key has ever been exposed, rotate before using it for anything
  identity-bearing

## Open questions worth asking 6529 directly

Rather than guessing, these are the things that would make agent-run validators
genuinely easy, and none are answered publicly as of 2026-11-07:

- Is there a supported headless or CLI mode?
- Are there stable, scriptable artifact URLs (or a package repo) for the Linux
  builds?
- Is there a machine-readable endpoint for "current minimum release" so a
  monitor can alert before a consensus switch?
- Is there a documented way to query whether a given account signed on a given
  day?

If you get answers, this document should be updated with them rather than
inferred around.
