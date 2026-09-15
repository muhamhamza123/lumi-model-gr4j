# lumi-model-gr4j

GR4J (Perrin, Michel & Andreassian 2003) — a lumped daily rainfall-runoff
model, wrapped as an HTTP bridge for
[openmi-coupling](https://github.com/muhamhamza123/openmi-coupling).

- `gr4j_core.py` — the real, unmodified model (4 scalar parameters,
  no land-use zones).
- `bridge.py` — exposes it over HTTP (`/health`, `/initialize`,
  `/update`, `/finalize`) so a C# OpenMI component can drive it.

Run standalone: `pip install -r requirements.txt && python3 bridge.py`
(listens on port 5059).

This repo is what openmi-coupling's `lumi_batch_entrypoint.py` clones
fresh and installs, in isolation, for every job that uses this model —
see that project's `docs/HANDOFF.md` and `docs/LUMI_PRODUCTION_DESIGN.md`.
