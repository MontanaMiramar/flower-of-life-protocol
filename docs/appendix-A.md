# Appendix A — Reproducing the Results

Every normative claim in [PROTOCOL.md](../PROTOCOL.md) is backed by a test
in this repository. This appendix maps the claims to their evidence and
gives the exact commands to reproduce everything from a clean environment.

## A.1 Clean-room setup

```bash
git clone https://github.com/MontanaMiramar/flower-of-life-protocol.git
cd flower-of-life-protocol
python -m venv .venv && source .venv/bin/activate
pip install -e . pytest
```

Requires Python ≥ 3.10. Runtime dependencies are exactly three:
`cryptography` (Ed25519), `rfc8785` (JCS canonicalization), `base58`
(did:key multibase).

## A.2 The full suite

```bash
pytest -q        # 87 passed
```

| Test module | Spec sections | What it demonstrates |
|---|---|---|
| `tests/test_identity.py` | §2 | did:key self-certification, JCS-signed envelopes, replay/freshness defense |
| `tests/test_reputation.py` | §3, §4 | relational trust, bilateral outcome attestations, dangling penalty, distance/time decay |
| `tests/test_cost_model.py` | §5 | per-capability cooperate decision; the trust curve emerges from the equation |
| `tests/test_matching.py` | §6 | namespaced URIs, core-vocabulary synonyms, match confidence → effective risk |
| `tests/test_server.py` | §7, §8 | signed HTTP handshake over real sockets, SSRF endpoint validation |
| `tests/test_manifest.py` | Capability Manifest v0.2 | Merkle selective disclosure, domain separation, tier challenge conformance |
| `tests/test_inflated_claim.py` | §6.7 (+ Manifest spec §8.5) | the inflated-claim experiment (below) |

## A.3 The inflated-claim experiment

The claim (PROTOCOL.md §6.6–6.7): an agent that inflates its surplus to
attract encounters earns strictly less than an honest agent, because low
match confidence inflates effective risk and failed outcomes destroy the
trust that cooperation-at-magnitude requires.

Reproduce it directly (n=50, seed=42):

```bash
python stranger_harness.py --inflated-claim
```

or via the pinned test:

```bash
pytest -q tests/test_inflated_claim.py
```

The recorded run and its parameters are in
[docs/experiments/inflated_claim.md](experiments/inflated_claim.md):
over 50 identical trials, lying is strictly unprofitable at every
magnitude tested.

## A.4 The live round-trip

The full encounter → proposal → response → outcome → reputation cycle
over real HTTP:

```bash
python demo/demo_roundtrip.py
```

## A.5 Formal model

PROTOCOL.md §11 restates the v1.0 mechanism compactly: the cooperation
threshold `T*` (§11.1) and trust propagation with decay (§11.2) are
one-line algebra over the definitions of §4–§5, and hold by construction;
§11.3 (percolation) is stated as a conjecture and labeled as such. The
cost-model tests (`tests/test_cost_model.py`) exercise the same
inequalities numerically.
