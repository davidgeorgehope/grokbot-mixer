# grokbot-mixer

An automated liquid drum & bass mix builder made by DJ Grok Bot (an AI agent). It takes a list of tracks and produces a beat-matched, harmonically ordered mix of 60 minutes or more, with deterministic guardrails, an eval scorer, audio-reactive visuals and an optional private YouTube upload.

**Start with [AGENTS.md](AGENTS.md).** The full recipe is written so an agent can build a mix cold. Then read [SETUP.md](SETUP.md) and the [docs/](docs).

**No audio is included.** This repo holds code, plans and analysis data only. You must source your own tracks legally (for example official uploads you have the rights to use, or files you own) and respect the artists' and labels' copyright. Track IDs in the plans and tracklists are references only.

Credentials are never stored here. They're read at runtime from a password manager (see `config.example.env`).

License: MIT (see LICENSE).
