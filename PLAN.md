# signal-bridge — plan

Bridge a Signal group to one member who only has email.
Signal → email as a batched digest. Email → Signal as near-immediate posts.
One bot can serve several groups, each with one email user, all configured via env vars.
In practice: the band's group, plus a test group that stays bridged in production.

## Decision: Signal + small bridge

Alternatives considered, briefly:

- **Delta Chat**: chat over email, so a plain-email user can in principle join a group natively.
  Everyone else would have to adopt a niche app. Recent versions push hard toward encrypted
  "chatmail" and treat classic-email contacts as second class. One email per message, with no
  batching.
- **Mailing list**: the smartphone users would hate it.
- **Matrix + bridges**: much more infrastructure than this needs.

Signal with a bot account on the spare landline is the least friction for everyone else.

## Architecture

```
 Signal group ⇄ [ bridge (python) ──subprocess──▶ signal-cli ]  ⇄  SMTP / IMAP  ⇄  email user
                 └──────── one container (quadlet) ────────┘       own domain
```

signal-cli runs as a subprocess, not via signal-cli-rest-api. The trade-off is that we own the
signal-cli updates, and Renovate handles them (see below).

### The bot's Signal identity

- Register the landline as a **primary** Signal account using voice verification. The voicemail
  records the code.
- The profile name is generic, e.g. "✉ Email bridge". Bridged messages are prefixed with the
  configured name (`[Marie] …`).
- Set a registration-lock PIN so nobody can re-register the number.

### Configuration (env vars)

Everything is prefixed with `SIGNAL_BRIDGE_` and parsed by `pydantic-settings`
(`env_prefix="SIGNAL_BRIDGE_"`, `env_nested_delimiter="__"`). Groups are a
`dict[str, Group]` keyed by an arbitrary slug. Slugs can contain single underscores, and they
come out lowercased.

| Var | Example | Notes |
|---|---|---|
| `SIGNAL_BRIDGE_ACCOUNT` | `+33…` | bot number |
| `SIGNAL_BRIDGE_ADDRESS` | `bridge@domain` | replies go to `bridge+<reply_token>@domain` |
| `SIGNAL_BRIDGE_IMAP_HOST`, `_IMAP_USER`, `_IMAP_PASSWORD` | | password: Podman secret |
| `SIGNAL_BRIDGE_SMTP_HOST`, `_SMTP_USER`, `_SMTP_PASSWORD` | | password: Podman secret |
| `SIGNAL_BRIDGE_ADMIN_EMAIL` | `me@domain` | failure alerts |
| `SIGNAL_BRIDGE_GROUPS__<slug>__GROUP_ID` | `abc…=` | from `listGroups` |
| `SIGNAL_BRIDGE_GROUPS__<slug>__EMAIL` | `marie@example.org` | the bridged user |
| `SIGNAL_BRIDGE_GROUPS__<slug>__NAME` | `Marie` | optional, default: local part of the email |
| `SIGNAL_BRIDGE_GROUPS__<slug>__FREQ` | `12h` | optional, default `12h`; `30m`/`6h`/`1d` via a small validator |
| `SIGNAL_BRIDGE_GROUPS__<slug>__REPLY_TOKEN` | random | Podman secret (`type=env`) |

Checked against pydantic-settings 2.13: a prefix + `__` + an arbitrary slug parse into the dict
as expected.

Changing anything means an Ansible run. A config error fails at startup with a readable pydantic
error, and the healthcheck rollback catches it.

**Welcome email:** at startup, for each group whose email differs from the one stored in its
state, send a short "how this works" email and store it. That covers both the first run and a
change of address, and it doubles as a delivery test.

### Container

One image, `signal-bridge` (this repo): Python + the signal-cli release.

- **signal-cli build:** the server (`pichenette`) is Debian 13 x86_64, so use the native Linux
  build (`signal-cli-<ver>-Linux-native.tar.gz`): no JVM, fast start per call.
- **Base image:** `python:3.14-slim`, digest-pinned. It already includes `ca-certificates`, which
  IMAPS/SMTPS need, so there's no apt step.
- **Version pin:** `ARG SIGNAL_CLI_VERSION` in the Dockerfile with a
  `# renovate: datasource=github-releases depName=AsamK/signal-cli` comment and a
  `customManagers` regex entry in `.github/renovate.json5`.
- **Update chain:** the same as `../conan`. signal-cli must stay current because Signal's servers
  reject old clients after a few months.
  - Renovate PRs get automerged.
  - Pushing to main mints a calver release, and `release.yml` builds and pushes
    `ghcr.io/ewjoachim/signal-bridge:latest`.
  - On the server, the quadlet's `AutoUpdate=registry` + `Pull=newer` lets
    `podman-auto-update.timer` pull the new image and restart.
  - The `HEALTHCHECK` gates the automatic rollback. Here it checks the mtime of a heartbeat file
    the loop touches each iteration (stdlib Python, no HTTP server). So a signal-cli bump that
    breaks `receive` gets rolled back.
- **Host bind mounts** (`/srv/signal-bridge/`):
  - signal-cli data dir. **This holds the account keys: back it up.**
  - Bridge state (the SQLite file).
- signal-cli locks its data dir, so there's one process and calls are sequential. That's no
  problem with a single loop.

One Python process with a simple `while True` loop, every ~2 min:

1. `signal-cli -a <bot> -o json receive --timeout 5`. It prints one JSON envelope per line.
   Store messages from configured groups in SQLite and ignore everything else. Attachments are
   already files in the data dir.
2. Check the IMAP inbox. Find the group from the `+<reply_token>`, and require `From` to be that
   group's email. Then:
   - Strip the quoted reply.
   - `signal-cli -a <bot> send -g <group> --message-from-stdin -a <files…>` with `[Name] ` prefixed.
   - Store it as a message too, so it appears in the next digest for context.
   - Move the mail to `Processed`.
3. For each group, send a digest when there are undigested messages from others and either:
   - the oldest of them is older than `freq` (so `freq` is the maximum delay, and a burst stays in one digest), or
   - one of them **@mentions the bot**. That's the "urgent" path: the whole pending digest goes
     out now.

subprocess calls always pass argv as a list, and the message text goes through stdin.
Receiving also keeps the Signal account active. Inactive accounts eventually get dropped.

### Signal → email (digest)

English, minimal wording. Translations can come later if ever.

- Subject: `[<group name>] 5 new messages`.
- Plain-text body, one block per message: `Tue 14:32 Paul: …`.
- The email user's own messages are included, so the thread reads naturally.
- Quotes appear as `> …`.
- Reactions are dropped in v1.
- Edits show the final text. Deleted messages are dropped.
- Footer: `Reply to this email to post in the group.`
- Attachments go on the email: sheet-music PDFs, photos, voice notes.
- `Reply-To: bridge+<reply_token>@domain`.

### Email → Signal

- IMAP poll on the bridge mailbox.
- **Accept** only if the `+<reply_token>` matches a group **and** `From` is that group's email.
  This is a cheap anti-spoofing measure, with no DKIM parsing.
- **Strip the quote** generically: a reply-parser lib (`mail-parser-reply`, multi-language). If it
  breaks for a real client, adjust then.
- **Post** the text and attachments to the group. Write the attachments to a temp dir, then
  `send -a`.
- Anything else: move it to `Rejected`. Never post it.

### State

SQLite (stdlib `sqlite3`), one file on the bind mount:

- `messages(group_id, ts, author, text, quote, attachments_json, mentions_bot, digested_at)`
- `names(key, name)`: display names of contacts (by uuid) and groups (by group id)
- `welcomed(group_id, email)`

Config stays in env vars. The DB only holds state.

No ORM.

## Code

- Python 3.14, `uv`, deps: `pydantic-settings`, maybe `mail-parser-reply`. Use the stdlib for
  `subprocess`/`imaplib`/`smtplib`/`email`/`sqlite3`.
- Config: env vars in the quadlet (see above). Secrets go in Podman secrets, with the values in
  Ansible Vault (like conan's `SECRET_KEY`).
- Deployment: rootful quadlet via `containers.podman.podman_container` (`state: quadlet`), like
  conan. The signal-cli data dir and the SQLite file live on host bind mounts under
  `/srv/signal-bridge/` so they can be backed up directly.
- Tooling: copy from conan (pre-commit, ruff, `autofix.yml`, `release.yml`, renovate config,
  Dockerfile structure: uv from its image, non-root uid, deps layer before source).
- Layout:
  ```
  signal_bridge/
    __main__.py   # loop
    signal_cli.py # subprocess wrapper: receive (parse JSON lines), send
    config.py     # pydantic-settings: Settings + Group
    inbound.py    # IMAP → Signal
    digest.py     # store → render → SMTP
    store.py      # sqlite
  tests/          # config parsing, receive payloads, digest rendering, reply stripping
  Dockerfile      # python + pinned signal-cli native release
  .github/
    renovate.json5         # conan's + regex manager for SIGNAL_CLI_VERSION
    workflows/release.yml  # conan's: calver release → ghcr.io push
  README.md       # incl. example ansible quadlet task, as in conan
  ```
- Failure handling: log and continue. If a loop iteration fails N times in a row, email *me*.

## One-time setup (manual, `podman exec` / `podman run` with the data bind mount)

1. Get a captcha token from `https://signalcaptchas.org/registration/generate.html`.
2. `signal-cli -a +33… register --captcha <token>`. Signal wants an SMS attempt first. Wait about
   60 s, then run `register --voice --captcha <token>`.
3. Listen to the voicemail, then `signal-cli -a +33… verify <code>`.
4. `setPin <pin>`, then `updateProfile --given-name … --avatar …`.
5. Create a **test group** (you + the bot), and add the bot to the band's group. Do both from
   your phone. If it stays invited/pending, accept it by hand with
   `updateGroup -g <group id>` (the id comes from `listGroups`). The alternative is
   `joinGroup --uri <group invite link>`.
6. `signal-cli -o json listGroups` gives the group ids. Put them in
   `SIGNAL_BRIDGE_GROUPS__TEST__…` / `SIGNAL_BRIDGE_GROUPS__BAND__…` and deploy.

Also save the JSON from a real `receive` as a test fixture, including a mention and a quote.

## Testing

You only have the landline and your own phone, and that's enough.

- **Emails:** your domain gives unlimited addresses. The test group's email is a test mailbox on
  your domain that you can send from, so the `From` check works for real.
- **Signal:** the **test group** (you + the bot) is bridged in production, next to the band's
  group. Posting, @mentioning the bot, email replies, and attachments can all be tried there
  without bothering the band.
- **Only one copy of the bot can run.** signal-cli keeps encryption state in its data dir, so two
  copies of that dir running at once get out of sync. Before go-live you can develop locally,
  then rsync the dir to the server once. After that, the server is the only place it runs.
- **The iteration loop:**
  1. Unit tests locally.
  2. Push to main.
  3. CI builds the image.
  4. On the server, run `systemctl start podman-auto-update` instead of waiting for the timer.
  5. Try it in the test group.
- **Unit tests** cover the logic as pure functions, with no account needed:
  - receive JSON → message
  - messages → digest
  - email → accepted? + stripped text
  - is a digest due?
  - config parsing

  Fixtures are real `receive` output from the test group. Multi-author cases are hand-edited
  copies, since there's only one human sender to test with.
- Signal and email I/O stay in thin wrappers that are tested by hand. There's no local mail
  server unless the email side turns out fiddly.
- **Registration:** register once and keep the data dir. Signal rate-limits registration
  attempts.

## Milestones

1. **Image + Renovate + register**: build the image with signal-cli, register the number, and
   send and receive in the group by hand.
2. **Signal → email digest** (+ welcome email), text only. Already useful on its own.
3. **Email → Signal**, text only.
4. **Attachments** both ways.
5. Polish: quotes, mention → urgent, failure alert email, backup of the signal-cli data dir.
