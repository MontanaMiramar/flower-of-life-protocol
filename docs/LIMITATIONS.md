# FLP v1 — Design Frontiers

> These are not weaknesses. They are the boundaries where v1 ends
> and the next layer begins — each with a path already marked.

---

## 1. The vocabulary boundary: not a wall, a Schelling horizon

Two agents with no semantic overlap cannot discover each other directly.
This sounds like a fatal flaw until you notice that the Flower of Life
pattern itself resolves it.

No node in the Flower of Life tessellation needs to touch every other node.
Each node touches its *neighbors*, and the full tessellation emerges from
local overlaps chained together. The same holds for FLP:

- Agent A (crypto analytics) and Agent C (hotel bookings) share no vocabulary.
- Agent B (personal assistant) shares some vocabulary with both.
- B doesn't need to *broker* anything. A and C become reachable through B
  simply because they're both reachable through B's vocabulary surface.

**General-purpose agents are the hubs of this network.** Max vocabulary
surface = max connectivity = bridge nodes. "More universal agents make larger
networks" is not a hope — it is hub formation in a network, and it is real.

**What v1 implements:** bilateral discovery with local vocabulary.
**What this seeds:** a connected component that grows as agents join.
**What makes it grow:** `cooperation_cost < solo_cost` must hold transitively,
and agents must be reachable — both properties that improve as more agents join.

---

## 2. The commitment gap: a deliberate boundary, not an oversight

FLP's handshake concludes with `ACCEPT`. What happens after — the actual work,
deliverables, SLAs — is out-of-band.

This is correct. HTTP does not dictate the payload. The day FLP specifies
deliverables and SLAs, it stops being universal.

The boundary is deliberate, and it has two exits already written:

**Exit A — Economic enforcement via reputation.**
The bilateral attestation of outcome (resolved/disputed) feeds back into the
reputation ledger. A bad actor doesn't face a contract breach; they face
every future encounter starting with lower trust. Defection is not free.
This is economic enforcement, not contractual, and it is sufficient to make
the first cooperation worth attempting.

**Exit B — §10 FLP-Settlement (reserved in PROTOCOL.md).**
The spec reserves §10 precisely for the contract/SLA layer — a higher-order
protocol that lives *on top of* the core, without contaminating it. When
you need binding deliverables, §10 is the door. It is not v1. It does not
need to be.

---

## 3. The bilateral nucleus: where the network begins

FLP v1 is bilateral: A encounters B. Multi-agent coalitions — where A, B,
and C together accomplish something none of them can do pairwise — require
a higher-order protocol that does not yet exist.

This is the honest statement. What it obscures is that the bilateral model
*is the nucleus*, not a truncated version of the goal.

The missing piece is transitive brokering: B introduces A to C. For that
to work, two things must be true:

1. `cooperation_cost < solo_cost` must hold *through* the bridge, not just
   at each bilateral hop.
2. A mechanism for introduction must exist (B says "A, meet C; I vouch").

Neither is automatic. Both are buildable on the reputation and identity
foundations v1 already provides.

---

## Summary: three frontiers, three directions

| Limit | What it really is | Path forward |
|---|---|---|
| Vocabulary gaps between distant domains | The Flower of Life pattern — local overlap forms global connectivity | Hub agents + transitive vocabulary + growing core.json |
| Out-of-band contracts | Deliberate — same reason HTTP doesn't dictate payload | Economic enforcement via reputation + §10 FLP-Settlement |
| Bilateral only | The nucleus, not the ceiling | Transitive brokering on top of v1's identity + reputation layer |

FLP v1 is the bilateral nucleus. Multilateral is a deliberate seed,
with the path already marked. A repo that says "this is bilateral by design,
and here is how it becomes a network" reads as architecture, not as a hole.

---

*PROTOCOL.md §10 is reserved for FLP-Settlement.*
*core.json is forkable and extensible by design.*
*The reputation ledger is the economic backbone for all three paths.*

---

*Flower of Life Protocol documentation — Rod Studio, 2026. Licensed under CC BY 4.0.*
