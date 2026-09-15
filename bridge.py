"""
HTTP bridge for GR4J -- exposes the real, unmodified gr4j_core.py (the
same file GR4J's BMI adapter uses; standard-form GR4J, Perrin, Michel &
Andreassian 2003) to a C# OpenMI component, same pattern as
hbv_bridge_service.py. Simpler than HBV's bridge: GR4J is a single-store
lumped model (no land-use zones), so its parameters are 4 flat scalar
values (x1..x4), not a CSV table.

Endpoints:
    POST /initialize   {"x1": ..., "x2": ..., "x3": ..., "x4": ..., "forcing_csv": "..."}
                        -> {"session_id": "...", "n_days": N}
    POST /update        {"session_id": "..."}
                        -> {"runoff": ..., "day": N, "log": "..."}
                        (no input needed -- GR4J is a pure producer, same
                        as HBV: it reads its own forcing file day by day)
    POST /finalize       {"session_id": "..."}

Run: ./.venv/bin/python bridge/gr4j_bridge_service.py
"""

import sys
import uuid
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request

# This model's own repo -- gr4j_core.py always sits right next to this
# file after a fresh clone (openmi-coupling's own lumi_batch_entrypoint.py
# clones the whole repo per component, then runs this as its entrypoint;
# see _clone_and_install), so no external ADAPTERS_DIR lookup is needed.
sys.path.insert(0, str(Path(__file__).parent))
from gr4j_core import GR4JParams, gr4j_daily_step, make_state

app = Flask(__name__)

_sessions = {}


@app.route("/health")
def health():
    return jsonify({"status": "ok", "sessions": len(_sessions)})


@app.route("/initialize", methods=["POST"])
def initialize():
    body = request.get_json(force=True)
    required = ("x1", "x2", "x3", "x4", "forcing_csv")
    missing = [k for k in required if k not in body]
    if missing:
        return jsonify({"error": f"missing required field(s): {missing}"}), 400

    params = GR4JParams(x1=float(body["x1"]), x2=float(body["x2"]), x3=float(body["x3"]), x4=float(body["x4"]))
    state = make_state(params)

    forcing = pd.read_csv(body["forcing_csv"], index_col=0, parse_dates=True)

    session_id = uuid.uuid4().hex
    _sessions[session_id] = {
        "params": params, "state": state,
        "precip": forcing["Prec_mm/d"].values, "pet": forcing["Epot_mm/d"].values,
        "dates": forcing.index, "day": 0, "n_days": len(forcing),
    }
    return jsonify({"session_id": session_id, "n_days": len(forcing)})


@app.route("/update", methods=["POST"])
def update():
    body = request.get_json(force=True)
    session_id = body.get("session_id")
    if session_id not in _sessions:
        return jsonify({"error": f"no session {session_id!r} -- call /initialize first"}), 400

    s = _sessions[session_id]
    if s["day"] >= s["n_days"]:
        return jsonify({"error": "update() called past end of forcing record"}), 400

    day = s["day"]
    precip = float(s["precip"][day])
    pet = float(s["pet"][day])
    date_label = s["dates"][day]

    s["state"], q = gr4j_daily_step(precip, pet, s["state"], s["params"])

    log_message = (
        f"day {day + 1}/{s['n_days']} ({date_label}): precip={precip:.2f}mm/d, pet={pet:.3f}mm/d "
        f"-> runoff={q:.4f}mm/d (production store={s['state'].production_store:.2f}mm, "
        f"routing store={s['state'].routing_store:.2f}mm)"
    )

    s["day"] += 1
    return jsonify({"runoff": q, "day": s["day"], "log": log_message})


@app.route("/finalize", methods=["POST"])
def finalize():
    body = request.get_json(force=True)
    _sessions.pop(body.get("session_id"), None)
    return jsonify({"finalized": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5059)
