# Working on weather-viewdata

A deployed Sextile application: the weather, served as Viewdata frames, from the
Norwegian Meteorological Institute (met.no) and a local GeoNames place index. It
is the first live Sextile service, answering calls at **weather.viewdata.no,
port 16651**. It was extracted from the Sextile workspace and now depends on the
published framework; the framework itself lives at
[github.com/rob-smallshire/sextile](https://github.com/rob-smallshire/sextile).

Start with [README](README.md) and the design note in
[docs/design.md](docs/design.md).

## The framework boundary

This is an **application**, not the framework. It depends on the published
`sextile` (from PyPI), pinned in `pyproject.toml` and the committed `uv.lock`, and
it must use only `sextile`'s public surface -- never reach into framework
internals. If the framework is *awkward* to build on, that is a framework defect:
raise it against the `sextile` repo (or its architect), do not work around it by
reaching past the surface. The framework's own design, its public surface, and
the general deployment note (`docs/deployment.md`) all live in that repo.

## How this is built

- **Test-first, in small increments.** Name the next behaviour, write the failing
  test, make it pass, tidy. Commit at each working increment. **Never push** --
  that is the user's call.
- **The gate, all four green over the repo:** `uv run pytest`,
  `uv run ruff check .`, `uv run mypy`. CI runs the same checks (see
  `.github/workflows/`), and a release will not deploy unless they pass.
- **Python is repo-driven.** `.python-version` (3.12) names the interpreter; `uv`
  fetches it. Do not vendor `sextile` or pin Python elsewhere.
- **Measure the far ends.** The forecast (met.no) and place (GeoNames) data have
  shapes worth respecting; tests drive captured fixtures under `tests/data/`
  rather than the live services.

## Conventions

- Docstrings Google-style, contract first, plain prose (the `sextile` repo's
  CLAUDE.md states the sentence-level rules; this app follows them).
- Path variables use the `_filepath`/`_dirpath` suffixes, not `_dir`/`_file`.
- Comments explain *why*, beside the line that makes the choice.
- Commit at each increment. No emoji in commit messages, and do not name the
  model or the assistant. Do not push.

## Trying it

```sh
uv run weather-viewdata import-places              # build the place index (seconds)
uv run weather-viewdata serve                      # answer calls (default port 16650)
uv run weather-viewdata render --page 0            # the title frame, drawn to the terminal
uv run weather-viewdata render --page 3213133880   # Trondheim's forecast
nc localhost 16650                                 # and call it
```

The place index defaults to `places.sqlite` in the working directory; run
`import-places` and `serve` from the same place.

## The gazetteer, and other data

- `import-places` builds `places.sqlite` from GeoNames. It is **derived data**,
  rebuildable at any time -- not something to preserve. The index carries a
  schema version (`RULES`); the service **refuses to serve a stale index** rather
  than answer by rules that have since changed (`StaleIndexError`). Re-import
  after changing the rules that derive it.
- met.no **requires an identifying `User-Agent`** with somewhere to complain to
  (`forecast/met.py`); keep it identifying, or met.no will block the service.
- The running version is read from the installed package metadata
  (`__version__`, via `importlib.metadata`) and **shown on the title frame**, so
  a caller -- or you, dialling in -- can see which build answered. It refreshes
  with each `uv sync`.

## Releasing and deploying

Releasing is `bump-my-version`, and the tag does the rest:

```sh
uv run bump-my-version bump patch     # or minor|major: edits pyproject, commits, tags vX.Y.Z
git push --follow-tags                # the tag triggers .github/workflows/deploy.yml
```

- **The deploy is gated on the tests.** `deploy.yml` runs a `gate` job (the same
  `ruff`/`mypy`/`pytest` CI runs, via the reusable `gate.yml`) on the tagged
  commit, and the `deploy` job `needs` it -- so a tag on broken code fails the
  gate and **never reaches the server**.
- `deploy` connects to the VPS as the unprivileged `deploy` user, checks out the
  tag, runs `uv sync --frozen`, and restarts the `weather-viewdata` service. Its
  only elevated power is `sudo systemctl restart weather-viewdata`.
- Secrets live on the `production` GitHub Environment (the SSH key, host, user,
  known-hosts); a required reviewer there gates each deploy behind a click if
  wanted. The workflow uses no third-party actions beyond SHA-pinned
  `actions/checkout` and `astral-sh/setup-uv`.
- The committed `uv.lock`'s own `version` field may lag a bump by one; this is
  harmless -- `uv sync --frozen` installs this package from source at its real
  version and freezes only the dependencies.

## The server

- Live at **weather.viewdata.no, port 16651** (raw TCP, viewdata). A landing page
  at <https://weather.viewdata.no> (served by Caddy) gives the connection detail.
- Code at `/srv/weather-viewdata` (owned by `deploy`); data at
  `/var/lib/weather-viewdata` (a `systemd` `StateDirectory` that **survives
  redeploys** -- a code deploy never touches it).
- `systemd` units: `weather-viewdata.service` (the service, bound to
  `0.0.0.0:16651`), and `weather-viewdata-import.service` + `.timer`, which seed
  and weekly-refresh the gazetteer **outside** the code deploy.
- The full deployment design -- the two planes (raw-TCP viewdata vs the HTTP
  landing pages), host hardening, Caddy, the secret pattern -- is written up in
  [docs/deployment.md](docs/deployment.md).
