# signal-bridge

Bridges Signal groups to members who only have email.

- **Signal → email:** group messages are batched into a digest email, sent at most every `freq`
  (12h by default), or right away when someone @mentions the bot. Attachments are included.
- **Email → Signal:** replying to a digest posts the reply into the group as `[Name] …`, with the
  quoted text stripped. Attachments work too.

The bot is a dedicated Signal account driven by [signal-cli](https://github.com/AsamK/signal-cli),
which is bundled in the image. One bot can bridge several groups, with one email address per group.

## Configuration

Everything is set through environment variables prefixed with `SIGNAL_BRIDGE_`.

| Variable | Example | Notes |
|---|---|---|
| `SIGNAL_BRIDGE_ACCOUNT` | `+33100000000` | The bot's phone number |
| `SIGNAL_BRIDGE_ADDRESS` | `bridge@example.org` | Sends digests. Replies come back to `bridge+<reply_token>@example.org`, so the mailbox must accept plus-addressing |
| `SIGNAL_BRIDGE_ADMIN_EMAIL` | `me@example.org` | Receives an alert after 5 failed iterations in a row |
| `SIGNAL_BRIDGE_IMAP_HOST`, `_IMAP_USER`, `_IMAP_PASSWORD` | | The mailbox of `ADDRESS`, IMAPS (port 993) |
| `SIGNAL_BRIDGE_SMTP_HOST`, `_SMTP_USER`, `_SMTP_PASSWORD` | | SMTPS (implicit TLS) |
| `SIGNAL_BRIDGE_SMTP_PORT` | `465` | Optional |
| `SIGNAL_BRIDGE_TIMEZONE` | `Europe/Paris` | Optional, `UTC` by default. Used for the times shown in digests |
| `SIGNAL_BRIDGE_POLL_INTERVAL` | `2m` | Optional |
| `SIGNAL_BRIDGE_DATA_DIR` | `/data` | Optional. Holds `signal-cli/` (account keys) and `bridge.db` |

Then, for each bridged group, pick a slug (e.g. `band`, `test`):

| Variable | Example | Notes |
|---|---|---|
| `SIGNAL_BRIDGE_GROUPS__<slug>__GROUP_ID` | `abc…=` | From `listGroups` (see below) |
| `SIGNAL_BRIDGE_GROUPS__<slug>__EMAIL` | `marie@example.org` | The email-only member |
| `SIGNAL_BRIDGE_GROUPS__<slug>__NAME` | `Marie` | Optional, defaults to the local part of the email. Used as the `[Name]` prefix |
| `SIGNAL_BRIDGE_GROUPS__<slug>__FREQ` | `12h` | Optional. Maximum delay before a digest: `30m`, `6h`, `1d`… |
| `SIGNAL_BRIDGE_GROUPS__<slug>__REPLY_TOKEN` | random | Secret. Only emails sent to `+<reply_token>` **and** from `EMAIL` are posted |

Generate a reply token with `python -c "import secrets; print(secrets.token_urlsafe(12))"`.

When a group's email is set for the first time, or changes, the bot sends that address a short
welcome email explaining how it works.

Processed emails are moved to a `Processed` IMAP folder. Emails that don't match a group go to
`Rejected` and are never posted.

## Registering the bot's number (once)

signal-cli keeps the account keys and encryption state in `/data/signal-cli`. **Back that
directory up, and never run two copies of it at once.** Two copies of the same state get out of
sync. Stop the service before running the commands below.

```bash
sc() {
  podman run --rm -it --user 10001:10001 -v /srv/signal-bridge:/data \
    ghcr.io/ewjoachim/signal-bridge:latest \
    signal-cli --config /data/signal-cli -a "+33100000000" "$@"
}
```

1. Solve the captcha at <https://signalcaptchas.org/registration/generate.html>. Copy the
   `signalcaptcha://…` link from "Open Signal".
2. `sc register --captcha 'signalcaptcha://…'`. Signal wants an SMS attempt first, even for a
   landline.
3. Wait about a minute, then `sc register --voice --captcha 'signalcaptcha://…'` (you may need a
   fresh captcha). You'll get a call that reads out the code.
4. `sc verify 123456`
5. `sc setPin 'some-long-pin'`. Sets the registration lock, so nobody else can re-register the
   number.
6. `sc updateProfile --given-name 'Email bridge'` (optionally add `--avatar /data/avatar.png`).
7. From your phone, add the bot to each group. If it shows up as invited, accept with
   `sc updateGroup -g <group id>`.
8. `sc -o json listGroups` lists the group ids for the configuration.

Signal rate-limits registrations, so do this once and keep `/data/signal-cli`.

## Example deployment using Podman Quadlet, rootful, via Ansible

As with any rootful Podman container, the container UID is the host UID: own the data directory
with the UID the container runs as. Secrets are Podman secrets. Their values come from an
encrypted store (e.g. Ansible Vault), never from the playbook.

```yaml
- name: Create signal-bridge data dir
  ansible.builtin.file:
    path: /srv/signal-bridge
    state: directory
    owner: "10001"
    group: "10001"
    mode: "0700"

- name: Store signal-bridge secrets
  containers.podman.podman_secret:
    name: "{{ item.name }}"
    state: present
    data: "{{ item.value }}"
  loop:
    - { name: signal_bridge_mail_password, value: "{{ signal_bridge_mail_password }}" }
    - { name: signal_bridge_band_token, value: "{{ signal_bridge_band_token }}" }
    - { name: signal_bridge_test_token, value: "{{ signal_bridge_test_token }}" }
  loop_control:
    label: "{{ item.name }}"

- name: Deploy signal-bridge quadlet
  containers.podman.podman_container:
    name: signal-bridge
    state: quadlet
    image: ghcr.io/ewjoachim/signal-bridge:latest
    user: "10001:10001"
    env:
      SIGNAL_BRIDGE_ACCOUNT: "+33100000000"
      SIGNAL_BRIDGE_ADDRESS: bridge@example.org
      SIGNAL_BRIDGE_ADMIN_EMAIL: me@example.org
      SIGNAL_BRIDGE_IMAP_HOST: mail.example.org
      SIGNAL_BRIDGE_IMAP_USER: bridge@example.org
      SIGNAL_BRIDGE_SMTP_HOST: mail.example.org
      SIGNAL_BRIDGE_SMTP_USER: bridge@example.org
      SIGNAL_BRIDGE_TIMEZONE: Europe/Paris
      SIGNAL_BRIDGE_GROUPS__BAND__GROUP_ID: "abc…="
      SIGNAL_BRIDGE_GROUPS__BAND__EMAIL: marie@example.org
      SIGNAL_BRIDGE_GROUPS__BAND__NAME: Marie
      SIGNAL_BRIDGE_GROUPS__TEST__GROUP_ID: "def…="
      SIGNAL_BRIDGE_GROUPS__TEST__EMAIL: test@example.org
      SIGNAL_BRIDGE_GROUPS__TEST__FREQ: 10m
    secrets:
      - "signal_bridge_mail_password,type=env,target=SIGNAL_BRIDGE_IMAP_PASSWORD"
      - "signal_bridge_mail_password,type=env,target=SIGNAL_BRIDGE_SMTP_PASSWORD"
      - "signal_bridge_band_token,type=env,target=SIGNAL_BRIDGE_GROUPS__BAND__REPLY_TOKEN"
      - "signal_bridge_test_token,type=env,target=SIGNAL_BRIDGE_GROUPS__TEST__REPLY_TOKEN"
    volume:
      - "/srv/signal-bridge:/data"   # bind mount → back this path up
    quadlet_options:
      - "AutoUpdate=registry"
      - "Pull=newer"
      - |
        [Service]
        Restart=always
        RestartSec=5s
```

**Continuous delivery.** Every push to main cuts a calver release and pushes
`ghcr.io/ewjoachim/signal-bridge:latest`. `podman-auto-update.timer` pulls the new image and
restarts the container. The image's healthcheck fails when `signal-cli receive` hasn't succeeded
for 15 minutes, so an update that breaks it gets rolled back. Renovate keeps signal-cli current,
which matters because Signal's servers stop accepting outdated clients after a few months.

To deploy right away instead of waiting for the timer: `systemctl start podman-auto-update`.

## Testing

Keep a test group (you and the bot) bridged to a test mailbox, next to the real groups. That lets
you try changes in production without bothering anyone.

## Development

```bash
uv sync
uv run prek install
uv run pytest
uv run prek run --all-files
```

To build the image locally (the bundled signal-cli is x86_64 only):

```bash
podman build --platform linux/amd64 -t signal-bridge .
```
