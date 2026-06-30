# Flower of Life Protocol (FLP) v1.0

**A protocol for matching and trust between autonomous agents that don't know each other.**

Two agents meet for the first time. Neither has a reason to trust the other.
FLP lets them discover whether they can help each other, decide whether
cooperating beats going it alone, and build a relationship where honesty is the
rational strategy — with no central authority, no registry, and no shared
operator.

The core idea: in a system with no center, cooperation is the path of least
resistance. v1.0 makes that a property you can run, not a slogan.

> **Maturity — read this first.** v1.0 is a complete, tested reference
> implementation of the protocol's hard parts (cryptographic identity,
> relational reputation, a cost model that decides, vocabulary-independent
> matching, a signed HTTP handshake with SSRF defense). It is **not** a
> hardened production network. Reputation-based defenses need a *dense* graph;
> trust signals are weak on a cold network (see PROTOCOL.md §1.4). Treat this
> as a serious foundation and a precise specification — not as turnkey
> infrastructure. The threat model is stated honestly in PROTOCOL.md §1.

## Why it's different

| Most agent protocols | FLP |
|---|---|
| Identity via registry/lookup | Identity **is** the key (`did:key`), verified with no network call (§2) |
| One global reputation score | **Relational** trust — there is no global number to capture or poison (§4) |
| Cooperate if capabilities match | Cooperate only when the **cost math** says so, weighted by earned trust (§5) |
| Exact-string capability matching | Namespaced URIs + forkable vocabulary + optional local semantics (§6) |
| "Assume honest agents" | A **rational-stranger threat model**; lying is made unprofitable, not impossible (§1) |

## Install

```bash
pip install -e .          # from a clone
# or
pip install git+https://github.com/MontanaMiramar/flower-of-life-protocol.git
```

Runtime dependencies are minimal: `cryptography`, `rfc8785` (JCS), `base58`.

## 60-second handshake

```python
from flp import Identity, FLPAgent, FLPServer, FLPClient, verify

cabo = FLPAgent(
    identity=Identity.generate(),
    needs=["flp:cap/data/market-research"],
    surplus=["flp:cap/tourism/venue-availability"],
    endpoint="https://cabo.example",
)
vex = FLPAgent(
    identity=Identity.generate(),
    needs=["flp:cap/tourism/venue-availability"],
    surplus=["flp:cap/data/market-intelligence"],   # a vocab-synonym of cabo's need
    endpoint="https://vex.example",
)

sv = FLPServer(vex).start()
client = FLPClient(allow_private=True)              # loopback dev only; never in prod

card = client.fetch_card(sv.base_url)              # discover + verify, no registry
proposal = client.encounter(sv.base_url, cabo.signed_card())
print(verify(proposal))                            # a signed, cost-evaluated proposal
sv.stop()
```

See `demo/demo_roundtrip.py` for the full encounter → proposal → response →
outcome → reputation cycle over real HTTP.

## How it fits together

```
identity (§2) ──signs──▶ everything on the wire
      │
reputation (§4) ──trust(me→X)──▶ cost model (§5) ──decides──▶ cooperate?
      ▲                                  ▲
   outcomes                        match confidence
   (§4.3, signed)                  matching (§6)
      ▲                                  ▲
   server (§8) ◀──discovery (§7)──▶ two cards meet
```

Every claim in the spec has a test. Run them:

```bash
pytest            # 74 tests across the five pillars
```

## Repository layout

```
flp/identity.py     §2   Ed25519 keys, did:key, JCS-signed envelopes, replay defense
flp/reputation.py   §4   relational trust, bilateral outcomes, distance/time decay
flp/cost_model.py   §5   per-capability cooperate decision; the equation that bites
flp/matching.py     §6   namespaced capability URIs + forkable vocabulary
flp/net.py          §7.5 SSRF guard for outbound fetches
flp/agent.py        §8   endpoint logic tying the pillars together
flp/server.py       §8   zero-dependency reference HTTP server + client
vocabulary/core.json §6.4 the forkable core vocabulary (a Schelling point)
PROTOCOL.md         the full specification
demo/               six runnable demos, one per pillar + the live round-trip
```

## Design decisions on record

The spec carries `Design decisions (on record)` blocks in each section
explaining *why* — e.g. why `agent_id` is the key and not its hash, why
reputation is relational, why positives propagate through the trust graph while
negatives stay edge-local (the anti-defamation choice). These are the field
notes of the design, kept so contributors inherit the reasoning, not just the
result.

## Roadmap

- **v1.1** — witnessed (third-party) outcome attestation for higher-assurance
  contexts; gossip robustness.
- **v2 — FLP-Settlement** (reserved, PROTOCOL.md §10): the same identity +
  reputation + discovery substrate extended to real-world assets a human owns
  (a farm agent trading produce for inputs). Settlement-agnostic by design: the
  core decides *whether* to cooperate; how value is delivered and verified is a
  layer above.

## License

MIT — see [LICENSE](LICENSE).

*Flower of Life Protocol — Rod Studio, 2026.*
