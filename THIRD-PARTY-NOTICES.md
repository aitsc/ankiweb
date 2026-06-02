# Third-Party Notices

**ankiweb** is a browser port of Anki and AnkiConnect. It is a derivative/combined work
and is licensed as a whole under **AGPL-3.0-or-later** (see [LICENSE](LICENSE)). This file
records the upstream copyrights and the licenses of the components it links, bundles, and
re-implements.

ankiweb Copyright (C) 2026 tsc &lt;xxj.tan@gmail.com&gt;.

---

## Anki — `anki` pylib (linked at runtime) + vendored compiled frontend

- Upstream: <https://github.com/ankitects/anki> (version **25.9.4**; `aqt` 25.9.4)
- Copyright (C) Ankitects Pty Ltd and the Anki contributors (see upstream `CONTRIBUTORS`)
- License: **AGPL-3.0-or-later**, with some user contributions under **BSD-3-Clause**.

ankiweb `import`s the `anki` Python library (collection, scheduler, Rust backend) at
runtime, and vendors Anki's **compiled frontend** — extracted from the `aqt` 25.9.4 wheel
(`_aqt/data/web/`: the SvelteKit SPA, `reviewer.js`, `editor.js`, the congrats page, CSS) by
`tools/fetch_web_assets.py` into `ankiweb/web_assets/` — and serves those bundles unmodified
(`/_anki/...`, `/_app/...`). Those compiled bundles are Anki object code under
AGPL-3.0-or-later. The **Corresponding Source** for them is the Anki/aqt 25.9.4 source at the
upstream repository above.

Anki's logo is Copyright Alex Fraser, licensed under AGPL-3.0. (Upstream's limited
alternative logo license permits using the logo only to *refer to* Anki in external content;
it does not relax the AGPL when the logo is shipped inside this derived app.)

### Components vendored *inside* the Anki frontend (permissive, AGPL-compatible)

| Component | License |
|-----------|---------|
| MathJax | Apache-2.0 |
| jQuery, jQuery-UI | MIT |
| plot.js | MIT |
| protobuf.js | BSD-3-Clause |
| Bootstrap (in `web_assets/css/...`) | MIT (Copyright 2011–2024 The Bootstrap Authors) |
| `statsbg.py` (pylib) | CC BY 4.0 |
| `mpv.py`, `winpaths.py` (qt) | MIT |
| Anki translations | mix of BSD and public domain |

These notices, where embedded in the vendored files, are preserved as served.

---

## AnkiConnect — re-implemented HTTP API (`ankiweb/ankiconnect/`)

- Upstream: <https://github.com/FooSoft/anki-connect>
- Copyright 2016–2021 Alex Yatskov (source headers); LICENSE file: 2016–2019 Alex Yatskov
- License: **GPL-3.0-or-later** (see [LICENSES/GPL-3.0-or-later.txt](LICENSES/GPL-3.0-or-later.txt))

ankiweb's `ankiconnect/` package re-implements ~120 AnkiConnect actions by closely following
the upstream source; it is a derivative work. GPLv3 §13 and AGPLv3 §13 grant the reciprocal
permission to combine GPL-3 and AGPL-3 code, so these portions are conveyed as part of the
AGPL-3.0-or-later combined work while remaining GPL-3.0-or-later in origin.

---

## Corresponding Source (AGPL §13)

Because ankiweb is a network service, every user interacting with it over a network is
entitled to the Corresponding Source of the running version. The app exposes a **Source**
link (top toolbar → `/about`); set `ANKIWEB_SOURCE_URL` to the location of your deployed
source. The pinned Anki/aqt 25.9.4 source is at <https://github.com/ankitects/anki> and the
AnkiConnect source at <https://github.com/FooSoft/anki-connect>.
