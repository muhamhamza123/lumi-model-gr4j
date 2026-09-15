"""
GR4J, a standard 4-parameter lumped daily rainfall-runoff model
(Perrin, Michel & Andreassian, 2003). Deliberately not shaped like HBV --
one production store instead of three land uses, unit-hydrograph
convolution instead of a triangular delay buffer -- so wrapping it in BMI
and coupling it to the same router as HBV is a real test of whether the
orchestrator generalizes, not just a second copy of the same shape.

Accuracy/calibration is out of scope here by design (that's on whoever
plugs a model in, not the framework) -- this is a standard-form
implementation, not a tuned one.

Parameters:
    x1: production store capacity (mm)
    x2: groundwater exchange coefficient (mm/d)
    x3: routing store capacity (mm)
    x4: unit hydrograph time base (days)
"""

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class GR4JParams:
    x1: float
    x2: float
    x3: float
    x4: float


@dataclass
class GR4JState:
    production_store: float = 0.0   # S (mm)
    routing_store: float = 0.0      # R (mm)
    uh1: np.ndarray = field(default_factory=lambda: np.zeros(0))
    uh2: np.ndarray = field(default_factory=lambda: np.zeros(0))


def _uh1_ordinates(x4):
    n = int(math.ceil(x4))

    def sh1(t):
        if t <= 0:
            return 0.0
        if t < x4:
            return (t / x4) ** 2.5
        return 1.0

    return np.array([sh1(i) - sh1(i - 1) for i in range(1, n + 1)])


def _uh2_ordinates(x4):
    n = int(math.ceil(2 * x4))

    def sh2(t):
        if t <= 0:
            return 0.0
        if t < x4:
            return 0.5 * (t / x4) ** 2.5
        if t < 2 * x4:
            return 1.0 - 0.5 * (2 - t / x4) ** 2.5
        return 1.0

    return np.array([sh2(i) - sh2(i - 1) for i in range(1, n + 1)])


def make_state(params: GR4JParams) -> GR4JState:
    return GR4JState(
        production_store=0.3 * params.x1,
        routing_store=0.3 * params.x3,
        uh1=np.zeros(int(math.ceil(params.x4))),
        uh2=np.zeros(int(math.ceil(2 * params.x4))),
    )


_uh_cache = {}


def _get_uh_ordinates(x4):
    if x4 not in _uh_cache:
        _uh_cache[x4] = (_uh1_ordinates(x4), _uh2_ordinates(x4))
    return _uh_cache[x4]


def gr4j_daily_step(precip, pet, state: GR4JState, params: GR4JParams):
    """Advance GR4J by one day. Returns (state, q_mm_d)."""
    x1, x2, x3, x4 = params.x1, params.x2, params.x3, params.x4
    s = state.production_store

    pn = max(precip - pet, 0.0)
    en = max(pet - precip, 0.0)

    if pn > 0:
        ps = x1 * (1 - (s / x1) ** 2) * math.tanh(pn / x1) / (1 + (s / x1) * math.tanh(pn / x1))
        es = 0.0
    else:
        ps = 0.0
        es = s * (2 - s / x1) * math.tanh(en / x1) / (1 + (1 - s / x1) * math.tanh(en / x1))

    s = s - es + ps
    s = min(max(s, 0.0), x1)

    perc = s * (1 - (1 + (4.0 / 9.0 * s / x1) ** 4) ** -0.25)
    s = s - perc

    pr = perc + (pn - ps)

    uh1_ord, uh2_ord = _get_uh_ordinates(x4)
    n1, n2 = len(uh1_ord), len(uh2_ord)

    if len(state.uh1) != n1:
        state.uh1 = np.zeros(n1)
    if len(state.uh2) != n2:
        state.uh2 = np.zeros(n2)

    state.uh1 = state.uh1 + 0.9 * pr * uh1_ord
    state.uh2 = state.uh2 + 0.1 * pr * uh2_ord

    q9 = state.uh1[0]
    q1 = state.uh2[0]
    state.uh1 = np.append(state.uh1[1:], 0.0)
    state.uh2 = np.append(state.uh2[1:], 0.0)

    r = state.routing_store
    f = x2 * (r / x3) ** 3.5
    r = max(0.0, r + q9 + f)
    qr = r * (1 - (1 + (r / x3) ** 4) ** -0.25)
    r = r - qr

    qd = max(0.0, q1 + f)
    q = qr + qd

    state.production_store = s
    state.routing_store = r
    return state, max(q, 0.0)
