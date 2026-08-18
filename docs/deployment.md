# Deploying weather-viewdata

An operations note: how this service is hosted on one small VPS, how a release
tag becomes a running service, and where the secrets live. It records decisions
argued once, not per deploy.

It also carries the **shared viewdata.no host setup** — the VPS, its users,
hardening, Caddy and DNS — because weather-viewdata is the first and so far only
deployed service. When a second service (wiki, dictionary) arrives, those shared
sections should move to a dedicated infrastructure repository; what stays here is
this service's own units, its data, and its release and deploy.

## The host

```
netcup VPS pico             one IPv4 address, one IPv6, a handful of services
viewdata.no                 the domain; each service takes a subdomain
```

One cheap VPS runs every service. A Viewdata service is low-traffic and
low-load, so a single small box carries a handful or two of them at once.

Why one box: the cost of a second is not repaid by the load, and one host keeps
the DNS, the firewall and the deploy path in one place.

## Users on the host

| User | Kind | Login | `sudo` | Owns |
| --- | --- | --- | --- | --- |
| `<admin>` | a person | SSH key | full | administers the box |
| per service, e.g. `weather-viewdata` | system account | none (`nologin`) | none | its own process |
| `deploy` | CI account | SSH key | one `systemctl restart` per service | the code under `/srv` |

```sh
# one locked-down system account per service
sudo adduser --system --group --no-create-home --shell /usr/sbin/nologin weather-viewdata
```

Three classes, split by how much each can do. A service account cannot log in or
`sudo`, so a reached service is a dead end; `deploy` can update code and restart
one unit and no more; only `<admin>` holds real power, and only over a key. A
service's writable state is not a hand-chowned home directory but a `systemd`
`StateDirectory`, created and owned for the service on start.

Why split them: the internet-facing account and the CI account each hold the
least that lets them do their one job, so a compromise of either stops there.

## Hardening the host

The host is Debian 13. The admin account is created with a password for `sudo`
and a public key, and root's own SSH login is then closed:

```sh
sudo adduser <admin>
sudo usermod -aG sudo <admin>
sudo install -d -m 700 -o <admin> -g <admin> /home/<admin>/.ssh
# the admin's public key goes in /home/<admin>/.ssh/authorized_keys, mode 0600
```

```
# /etc/ssh/sshd_config.d/10-hardening.conf
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
```

The firewall denies inbound by default and opens each port only as the thing
behind it goes in; SSH is rate-limited rather than merely allowed:

```sh
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw limit 22/tcp
sudo ufw enable
```

`fail2ban` installs with its `sshd` jail enabled and bans persistent probers;
`unattended-upgrades` applies security updates daily:

```sh
sudo apt install -y fail2ban unattended-upgrades
# /etc/apt/apt.conf.d/20auto-upgrades
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
```

Why in this order: a proven key login and a `ufw` rule admitting SSH come before
the sshd restart and before `ufw enable`, so no step locks the box against the
person running it. Password auth being off makes `fail2ban` belt-and-braces, kept
for the log quiet and the blocked scanners.

## Two planes

| Plane    | Protocol | Port            | Reaches                     | Routed by  |
| -------- | -------- | --------------- | --------------------------- | ---------- |
| Viewdata | raw TCP  | one high port each | the Sextile service      | the port   |
| Web      | HTTP(S)  | 80 / 443        | a one-page connection notice | the subdomain |

A Viewdata client opens a raw TCP socket. Nothing on that wire names a subdomain,
so the **port is the selector** and the subdomain is a human convention pointing
at the shared IP. `weather.viewdata.no:16651` and `wiki.viewdata.no:16651` would
reach the same service. The web plane is ordinary HTTP, so there the **subdomain
is the selector** and a reverse proxy routes each to its own landing page.

Why keep them apart: they are routed by different things, so a proxy that earns
its place on the web plane has nothing to do on the Viewdata plane.

## A service, as a systemd unit

```ini
# /etc/systemd/system/weather-viewdata.service
[Unit]
Description=weather-viewdata Viewdata service
After=network-online.target
Wants=network-online.target

[Service]
User=weather-viewdata
StateDirectory=weather-viewdata
WorkingDirectory=/var/lib/weather-viewdata
ExecStart=/srv/weather-viewdata/.venv/bin/weather-viewdata serve --host 0.0.0.0 --port 16651 --index /var/lib/weather-viewdata/places.sqlite
EnvironmentFile=-/etc/sextile/weather-viewdata.env
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Each service is one unit: an unprivileged user, a fixed high port, `Restart` so a
crash recovers. `StateDirectory` gives it a `/var/lib/weather-viewdata` it owns
for its SQLite file, and `WorkingDirectory` runs it there while the code stays
under `/srv`. The `-` on `EnvironmentFile` makes the file optional, so a service
with no secrets needs no file and no edit to this unit.

Why systemd over containers: for a few tiny long-lived sockets on a 2 GB box,
one unit per service is lighter than Docker and asks nothing of the RAM the small
host is chosen to save.

## Seeding and refreshing data

```ini
# /etc/systemd/system/weather-viewdata-import.service  (Type=oneshot, User=weather-viewdata)
ExecStart=/srv/weather-viewdata/.venv/bin/weather-viewdata import-places --index /var/lib/weather-viewdata/places.sqlite
ExecStartPost=+/usr/bin/systemctl try-restart weather-viewdata
```

A companion `oneshot` unit populates the service's data, paired with a timer for
scheduled refreshes; a code deploy never runs it. The `+` prefix on
`ExecStartPost` restarts the service as root after the unprivileged import, so it
reopens the finished file.

Why separate from the deploy: data is seeded once and refreshed on a timer, in
`/var/lib` where no deploy reaches, so a push replaces code and restarts while the
database survives untouched.

## The web plane, with Caddy

```
# /etc/caddy/Caddyfile
weather.viewdata.no {
    root * /srv/www/weather
    file_server
}
wiki.viewdata.no {
    root * /srv/www/wiki
    file_server
}
```

`caddy` on 80/443 serves one static page per subdomain and obtains a Let's
Encrypt certificate for each automatically. Each page states the host and port to
dial; it is not the service, only the notice beside its door.

Why Caddy: automatic TLS for every subdomain with near-zero configuration, which
is the whole of what the web plane needs.

## Bringing up the web plane

DNS at the `viewdata.no` registrar points every subdomain at the host with one
wildcard record, and the apex alongside it:

| Type | Name | Value | TTL |
| --- | --- | --- | --- |
| `A` | `*` | `<VPS_IP>` | 300 |
| `A` | `@` | `<VPS_IP>` | 300 |

The firewall opens the web ports (80 for the ACME challenge, 443 for traffic and
HTTP/3):

```sh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
```

Caddy installs from its official apt repository, runs as an unprivileged `caddy`
user under `systemd`, and reads `/etc/caddy/Caddyfile`; each service's landing
page lives under `/srv/www/<service>`. On reload Caddy fetches, and thereafter
renews, the certificate for each name in the Caddyfile.

Why this order: Caddy proves control of a name by answering Let's Encrypt on
port 80, so the record must resolve and 80 must be open before Caddy starts, or
the challenge retries in a loop. The wildcard record means a new service needs
only a Caddyfile block, never another DNS change.

## Repository and build

```
sextile            the framework: one repository, a library, no committed lockfile
weather-viewdata   this service: its own repository, its own committed lockfile
```

This service lives in its own repository and depends on the published `sextile`
from PyPI, with a committed `uv.lock`. A deploy clones the repository and runs
`uv sync --frozen`, so the box installs exactly what was tested and resolves
nothing itself. The interpreter rides in with the repository too (`.python-version`),
which `uv` fetches.

Why a repository per deployed service: a uv workspace has one lockfile, and a
library must not commit one while a deployment must, so the framework and a
deployable service cannot both be right in one workspace. That is the reason
weather-viewdata was extracted from the Sextile workspace; the framework's design
log records the decision.

## Secrets

```python
# in the service's config factory
api_key = os.environ["OPENWEATHER_API_KEY"]   # raises at startup if unset
```

```
# /etc/sextile/weather-viewdata.env   root:weather-viewdata  0640
OPENWEATHER_API_KEY=...
```

A service reads each secret from the environment and fails at startup if it is
missing; `systemd` supplies the environment from a file owned by root and
readable only by the service user. weather-viewdata needs no secret today (met.no
and GeoNames are keyless); the shape is in place for the first service that does.

Secrets are provisioned **on the box, out of CI**. GitHub then holds one secret
only, the deploy key, and never an upstream API key; a compromised pipeline can
restart a service but cannot read a credential that was never given to it. When
the set of placed keys outgrows memory, the next step is `age`/SOPS: encrypted
secrets committed to the repository, decrypted only on the box.

Why fail closed: a mis-provisioned box that refuses to start is found at once; one
that starts and serves a broken page is found by a reader.

## Deployment

```
release tag vX.Y.Z  ->  gate: ruff, mypy, pytest on the tagged commit
                    ->  deploy: ssh deploy@host, checkout the tag,
                        uv sync --frozen, restart the unit
```

`bump-my-version` writes the tag (`uv run bump-my-version bump patch|minor|major`,
then `git push --follow-tags`); the tag runs one workflow with two jobs. The
`gate` job runs the same checks CI runs — `ruff`, `mypy`, `pytest` — on the tagged
commit, from a reusable `gate.yml` shared with CI; the `deploy` job `needs` it, so
a tag on broken code fails the gate and **never reaches the host**. `deploy`
connects as the `deploy` user, checks out the tag, runs `uv sync --frozen`, and
restarts the unit — its one elevated power a `sudo` restricted to
`systemctl restart weather-viewdata`. Its secrets live on a `production` GitHub
Environment, exposed only to the tag-triggered job; a required reviewer there
gates each deploy behind a click if wanted.

Why tag-gated, tested and scoped: the repository is public, so anyone may open a
pull request; the deploy runs only on a maintainer's release tag, never on
`pull_request`; the gate makes a green suite a precondition of shipping; and the
key's reach is one service restart rather than the box.

## Security posture

The repository is public, so nothing in it is secret and the controls do not rest
on hiding the host, the ports or the deploy mechanism, all of which the workflow
file shows.

- Untrusted CI input (`pull_request` titles, branch names) is passed through
  `env:` variables, never interpolated into a shell `run:` step; the release tag
  is validated as a plain `vX.Y.Z` before it is passed to a shell on the host.
- Third-party actions are pinned to a commit SHA, not a moving tag.
- The deploy key is a dedicated non-root user, scoped to one restart, never able
  to read a runtime secret.
- The host takes key-only SSH with root login disabled, `fail2ban`,
  `unattended-upgrades`, and a firewall open to exactly SSH, 80, 443 and the
  service ports.
- The Viewdata plane is unauthenticated by the protocol's nature, which suits a
  public read-only service; the guarded surface is the deploy path, not the call.

## When to provision the VPS

The order the box was brought up in, and the order to bring up another:

1. Provision the VPS; point `viewdata.no` and one subdomain at its IP.
2. Harden the host (SSH keys, firewall, `fail2ban`, `unattended-upgrades`).
3. Install Caddy; serve one static landing page over automatic TLS.
4. Install the service by hand as a `systemd` unit on its port; dial it with
   `nc weather.viewdata.no 16651`.
5. Only then add the `deploy` user, its scoped `sudo`, and the tag-triggered
   GitHub Actions workflow (gated on the test suite), so the automation targets a
   shape already known to work.
