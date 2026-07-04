# Flower of Life Protocol — Technical Specification v1.0 (DRAFT)

> **Status:** Working draft. Sections 1–5 stable; §6+ in progress.
> v1.0 supersedes v0.1 by replacing the "honest agents" assumption with
> a rational-stranger threat model, cryptographic identity, relational
> reputation, and a cost model that actually decides.

---

## 1. Threat Model

FLP v0.1 assumed honest agents. v1.0 does not. The counterparty is
modeled as a **rational stranger**: an agent that will defect whenever
defection has higher expected value than cooperation. FLP does not
appeal to good faith. It changes the payoffs so that honesty is the
rational strategy.

### 1.1 Adversaries

- **The lying stranger.** Inflates its surplus, accepts proposals,
  fails to deliver. Single-shot defector seeking value without return.
- **The Sybil.** Generates many identities cheaply to flood the
  network, self-deal reputation (identities vouching for each other),
  or escape consequences.
- **The whitewasher.** A single-identity Sybil: burns a reputation,
  regenerates a clean identity, returns.
- **The defamer.** Emits false negative outcomes about honest agents
  to poison their reputation. Attacks the reputation layer itself.
- **The surplus inflator.** Claims capabilities it cannot fulfill to
  bait cooperation. (Matching-layer variant of the lying stranger.)
- **The replayer.** Re-sends old signed messages out of context.
- **The confused-deputy abuser.** Uses an FLP agent's outbound fetches
  (card probe, bootstrap) to reach internal services (SSRF).

### 1.2 Adversary Capabilities (assumed)

The attacker can: read all public cards; generate unlimited keypairs
at zero cost; send any message to any endpoint; operate any number of
colluding agents. The attacker cannot: forge a signature without the
private key; find hash collisions; read private keys it does not hold.

### 1.3 Security Goals

- **Authenticity** — a message attributed to agent X was produced by
  the holder of X's key.
- **Integrity** — messages cannot be altered in transit undetected.
- **Non-repudiation** — an agent cannot deny a card, proposal, or
  outcome it signed.
- **Accountability** — defection leaves a signed, attributable trace.
- **Sybil-resistance via cost asymmetry** — identities are free, but
  trust is earned slowly; a cheap identity is worthless until it pays
  the time-cost of building reputation.

### 1.4 Non-Goals (v1.0, stated honestly)

FLP v1.0 does **not** provide: transport confidentiality (delegated to
TLS/the host framework); defense against a global passive traffic
analyst; legal/KYC identity (agent_id is pseudonymous by design);
robust security on a *cold* network. Reputation-based defenses require
density — a young network with few participants is inherently weak, and
implementors must not rely on FLP trust signals until the local graph
is dense. This is a property of the model, not a bug.

> **Design principle.** We do not prevent lying. We make lying
> unprofitable. A stranger cannot be stopped from defecting in one
> message; the protocol ensures that defection forfeits future
> cooperation worth more than the one-time gain.

### 1.5 Scope: Settlement Agnosticism

FLP is a protocol for **two things only: matching and trust.** It
decides *whether* two agents should cooperate and *whether* a
counterparty is reliable. It deliberately says nothing about *how the
cooperated-upon value is delivered or verified* — that is **settlement**,
a separate concern living in a layer above the core.

This boundary is load-bearing, not incidental. The surplus→need pattern
is **substrate-independent**: the geometry of "my surplus seeks your
deficit" is identical whether the surplus is data, a service, or a
physical good a human owns. It is *because* the pattern generalizes that
settlement must stay out of the core: baking any one settlement type
into the base would shrink a general matchmaker into a single-purpose
tool. The transport layer does not know about money — TCP carries
payments without being a payment system, and FLP matches asset exchange
without being an asset exchange.

The core therefore makes one promise it can always keep: for **digital**
cooperation, delivery happens *inside* the protocol, so both agents
witness it and the bilateral attestation of §4.3 carries genuine
ground truth. Settlement types where the agents *cannot* directly
witness fulfillment (physical goods, off-protocol services) are
explicitly out of scope for v1.0 and are addressed by the reserved
extension layer of §10. A `settlement_type` field (§8.3) marks the
boundary at the data level, defaulting to `digital`.

---

## 2. Identity

### 2.1 Keys

Every agent holds an **Ed25519** keypair. Ed25519 is chosen for small
keys (32 B) and signatures (64 B), deterministic signing (no nonce
footgun), and ubiquitous library support. The private key never leaves
the agent. The public key *is* the agent's identity.

### 2.2 Self-Certifying agent_id

`agent_id` is a **self-certifying identifier**: it encodes the public
key itself, not a name that must be looked up.

    agent_id = "did:key:" + multibase(multicodec(ed25519_pub))
    e.g. did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK

This is the `did:key` method (W3C DID). The consequence that matters:
**anyone holding the agent_id can verify that agent's signatures with
no registry, no lookup, no network call.** The identifier carries its
own verification key. This is what lets FLP have cryptographic identity
with no central authority — the thing v0.1 only claimed.

> **Design decision (on record).** agent_id = key, not hash(key).
> A hash is shorter but forces a separate "where do I fetch the
> pubkey" step, reintroducing a lookup and a trust dependency. The
> self-certifying ID removes an entire class of problem at the cost of
> a longer string. Decentralization beats brevity here.

### 2.3 What Is Signed, and How

Cards, proposals, responses, and outcome attestations are all signed.
A signed object is an envelope:

    {
      "body": { ...the object's fields... },
      "agent_id": "did:key:z6Mk...",
      "sig": "base64(ed25519_sign(canonical(body)))"
    }

`canonical()` is **JCS (RFC 8785)** — JSON Canonicalization Scheme:
sorted keys, no insignificant whitespace, normalized UTF-8 and number
forms. Plain JSON is non-deterministic (key order, spacing), so it
cannot be signed reliably; JCS makes the byte sequence reproducible on
both ends. Verification: recompute `canonical(body)`, check `sig`
against the key embedded in `agent_id`.

### 2.4 Freshness and Replay

Every signed object carries `issued_at` (unix seconds). Cards also
carry `expires_at`; messages also carry a `nonce` (≥128-bit random).
Receivers MUST reject objects that are expired, that arrive outside a
clock-skew window (default ±300 s), or whose `nonce` was seen within
the replay window. A signed card with no expiry is replayable forever;
expiry is mandatory, not optional.

### 2.5 Key Rotation (hook)

An agent may rotate keys via a signed rotation link: the old key signs
a statement endorsing the new agent_id. **Reputation — including any
negative history — transfers along the signed chain.** Rotation is a
public, attributable event, never a clean slate. Full semantics are
defined together with §4 Reputation, because rotation and whitewashing
are the same coin viewed from opposite sides.

---

## 3. Newcomers and Whitewashing

### 3.1 The Problem

Identity is free (§2.2). Therefore a defector can burn a reputation and
regenerate a clean identity at will. This cannot be prevented by
detection — a fresh key is indistinguishable from any honest newcomer's
fresh key, by construction.

### 3.2 The Resolution

FLP does not try to detect whitewashing. It makes a fresh identity
**worthless until it earns trust**, so that regenerating forfeits
everything the attacker built. The defense is the reputation *curve*,
not a filter.

Concrete rules:

1. **Identity creation is free and unrestricted.** Accepted, not fought.
2. **Reputation starts at 0 and is non-transferable across identities.**
   The only carry-over path is the signed rotation link of §2.5, which
   transfers negatives too. There is no reset.
3. **The cost model gates exchange magnitude by reputation.** A rep-0
   stranger is treated as maximum counterparty risk, so only
   **low-magnitude, low-stakes** exchanges clear the cost threshold
   (see §5, Cost Model). A newcomer can act — but only in small.
4. **Trust builds sub-linearly and decays super-linearly.** Reputation
   accrues slowly across many honest exchanges; a single defection
   costs more than many cooperations earned. This asymmetry is the
   deterrent: a rational stranger computes that one defection destroys
   more future value than it captures.
5. **Therefore whitewashing is permitted but unprofitable.** It returns
   the attacker to the probation tier, forfeiting all accrued trust,
   with no shortcut back. A whitewasher is, by design, in exactly the
   same position as any honest newcomer: re-grinding from zero.

### 3.3 Cold-Start (the cost of this design, stated)

If every agent distrusts rep-0 identities, no newcomer can ever begin.
Resolution: the **probation tier**. Low-magnitude exchanges are cheap
enough that `risk × magnitude` stays below `solo_cost` even at maximum
risk, so newcomers (and whitewashers) *can* transact small, build
history, and graduate. The network stays open to strangers; it just
makes them earn their way up. Honest newcomers experience this as a
brief warm-up. Whitewashers experience it as a permanent tax.

> **Sybil note.** Single-identity Sybil (whitewashing) is defeated here
> by rules 2–4. Multi-identity collusion (Sybils vouching for one
> another to manufacture reputation) is a *reputation-graph* attack and
> is addressed in §4 (gossip trust / witnessed outcomes), not here.

---

## 4. Reputation

### 4.1 Principle: There Is No Global Score

Reputation in FLP is **relational**, never global. Each agent computes
its *own* trust value for every other agent, from its own vantage point
in the cooperation graph. There is no canonical "reputation of X" — only
`trust(observer → X)`, which two different observers will legitimately
compute differently. This is not an inconsistency to be reconciled; it
is the point. A system with no center has no single number for an
attacker to capture, inflate, or poison.

### 4.2 Inputs

`trust(me → X)` is computed from two sources:

1. **Direct experience.** Outcomes of cooperations *I* completed with X.
   Highest weight. This is ground truth for me.
2. **Propagated testimony.** Outcomes reported by agents I already
   trust, about their cooperations with X — weighted by how much I
   trust *them*, and decayed by graph distance.

Direct experience always dominates testimony. I believe what I saw over
what I was told.

### 4.3 Outcome Attestations (bilateral)

When a cooperation concludes, **both** parties sign an outcome:

    {
      "body": {
        "type": "outcome_attestation",
        "proposal_id": "...",
        "counterparty": "did:key:...",
        "verdict": "fulfilled" | "failed",
        "issued_at": 1234567890,
        "nonce": "..."
      },
      "agent_id": "did:key:...(signer)...",
      "sig": "..."
    }

A cooperation has one of three terminal states, from the perspective of
each party's reputation math:

- **CONFIRMED-GOOD** — both parties signed `fulfilled`. Strong positive.
- **CONFIRMED-BAD** — both parties signed `failed`, OR the two verdicts
  disagree (a *disputed* outcome). Strong negative for the failing /
  disputing relationship. FLP does not adjudicate who was right; a
  disputed exchange simply damages the trust *edge* between those two
  agents, which is the only thing that needs to be true relationally.
- **DANGLING** — the cooperation was entered but never closed with a
  signed outcome from one side. **Soft negative.** (See 4.4.)

Because both signatures are required for CONFIRMED-GOOD, a **defamer
cannot unilaterally manufacture a negative** about an honest agent: it
would need the victim to co-sign its own failure. This is what choosing
bilateral attestation buys, and it is why FLP v1.0 does not need
witnesses to resist defamation. Witnessed/third-party attestation is a
v1.1 extension for higher-assurance contexts, not a v1.0 requirement.

### 4.4 The Dangling Penalty (closing the limbo loophole)

If "unsigned" were free, every rational defector would simply never
sign the outcomes of its own defections, hiding all bad behavior in
permanent limbo. FLP closes this: **entering a cooperation you do not
close is itself a soft negative against you.**

    fulfilled (confirmed)   → strong positive
    failed/disputed         → strong negative
    dangling (you left open)→ soft negative, applied after a timeout
                              to the party that did not sign

The asymmetry `confirmed-bad < dangling < confirmed-good` means:
honest agents are pushed to always close (closing is the only path to
positive rep), and defectors pay a cost whether they sign their failure
or hide from it. There is no profitable silence.

### 4.5 Propagation, Distance Decay, and Sybil Resistance

Testimony from a trusted agent enters my computation **attenuated by
trust and by distance**:

    weight(testimony from Y about X)
        = trust(me → Y) × decay^(path_length)

with `decay ∈ (0,1)` (default 0.5) and a hard horizon
`MAX_DEPTH` (default 2). Beyond the horizon, testimony contributes 0.

Consequences:

- **Direct experience > a friend's report > a stranger's report**,
  automatically, by construction.
- **Sybil collusion is defeated structurally, for free.** A cluster of
  fresh identities vouching for one another has *no short trusted path*
  to me. Their mutual praise arrives multiplied by `trust(me → them) ≈
  0`, so it contributes ≈ 0 to my view. I cannot be reached by a clique
  I have never transacted with and that no one I trust has transacted
  with. No separate anti-Sybil mechanism is required; the relational
  topology *is* the defense.
- A newcomer is **invisible, not distrusted** — it simply has no edges
  yet. It becomes visible to me the moment I transact with it directly,
  or someone within `MAX_DEPTH` of me does. This is the graph-level
  statement of the §3 probation tier.

#### 4.5.1 Propagation polarity: positives propagate, negatives are edge-local

A subtle interaction between §4.3 (anti-defamation), §4.4 (dangling), and
§4.5 (propagation) must be resolved explicitly, because it determines
whether the reputation layer is itself attackable. The resolution:

- **CONFIRMED_GOOD propagates.** It requires *both* parties' signatures,
  so it is forgery-proof, and it travels the trust graph as positive
  testimony (attenuated by trust and distance as above).
- **Negative outcomes do not propagate.** Mutual-bad, disputed, and
  dangling affect *only* the direct edge between the two involved
  parties. A third party never lowers its trust in X based on someone
  else's unverifiable claim that "X failed."

Why this asymmetry is mandatory: if negatives propagated, a defamer Y
could broadcast a negative about an honest X that no third party can
verify, reopening exactly the attack §4.3 closes. By making negatives
edge-local, an agent **cannot shout negatives** about others — it can
only *withhold* positive testimony (stop vouching) and stop referring
(§7.3). A known defector's reputation therefore falls because positive
testimony stops flowing *toward* it, never because accusations flow
*against* it. Withholding praise is unforgeable; broadcasting blame is
not — so FLP only allows the former to propagate.

This is consistent with §4.2's ordering (direct experience always
dominates): your own negative experience with X fully lowers your trust
in X; you simply cannot export that negative as testimony others must
believe.

### 4.6 Decay Over Time

Trust edges decay toward neutral with age (default half-life: 90 days).
Reputation is a claim about *current* behavior; stale cooperation is
weak evidence. Time decay also bounds the value of a long-dormant
identity reactivating, and prevents ancient grudges from being
permanent.

### 4.7 What Reputation Is For

`trust(me → X)` feeds exactly one thing: the **counterparty-risk term
of the cost model** (§5). Reputation is not a public badge or a
leaderboard — it is a private input to a private decision: *given what I
know of X, is cooperating still cheaper than going solo, and at what
magnitude?* Reputation never leaves the cost computation. This keeps
FLP's promise — math, not morality, not status.

> **Design decisions (on record).**
> 1. Reputation is relational; there is no global score (no center to
>    capture).
> 2. Outcomes are bilateral; defamation needs the victim's signature,
>    so it can't be forged.
> 3. Dangling = soft negative; silence is not a refuge.
> 4. Trust decays with graph distance (horizon 2) and with time
>    (half-life 90d); Sybil resistance falls out of the topology for
>    free.

---

## 5. Cost Model

### 5.1 Principle: The Equation Must Bite

FLP v0.1 advertised `cooperation_cost < solo_cost` but, with a fixed
cost ceiling below a fixed solo constant, the comparison was always
true when a match existed: the cost model decided nothing. v1.0 makes
the equation load-bearing. Cost is computed **per capability**, and
incorporates the counterparty risk derived from relational reputation
(§4). The decision is no longer "cooperate with X?" but "cooperate with
X *on item c*, and at what magnitude?"

### 5.2 Per-Capability Decision

For each capability `c` that I need and X offers (`c ∈ my.needs ∩
X.surplus`, under the namespaced matching of §6):

    coop_cost(c)  = transport_cost + ( risk(me→X) × magnitude(c) )
    cooperate(c)  ⟺  coop_cost(c) < solo_cost(c)

A single encounter can therefore yield cooperation on some capabilities
and a pass on others, with the same counterparty. The proposal carries
only the items that cleared their own threshold.

### 5.3 The Terms

- **`solo_cost(c)` — what it costs *me* to obtain `c` without
  cooperating.** A per-capability value I assign for myself (defaults
  provided; agents tune their own). High when `c` is outside my
  competence or expensive to produce alone; low when I can already do
  `c` cheaply. This is what makes cooperation *worth it* only where I
  am genuinely worse off solo. `solo_cost` is private; it is never
  published in my card.

- **`magnitude(c)` — the size/stakes of this specific exchange of
  `c`.** A one-off data point is small; an ongoing feed or a
  high-volume capability is large. Magnitude is what the probation tier
  (§3.3) caps for strangers: large-magnitude exchanges with a rep-0
  party cannot clear the threshold, small ones can.

- **`risk(me→X)` — counterparty risk, the bridge from reputation.**
  A monotonic decreasing function of relational trust:

        risk(me→X) = RISK_MAX − ( trust(me→X) × (RISK_MAX − RISK_MIN) )

  with `trust ∈ [0,1]`. A total stranger (`trust = 0`) is `RISK_MAX`;
  a long-proven partner approaches `RISK_MIN`. Risk multiplies
  magnitude: the more a defection would cost me (large magnitude), the
  more a risky counterparty inflates `coop_cost`. This single product
  is where identity, reputation, and the cooperation decision meet.

- **`transport_cost`** — fixed overhead of the exchange itself
  (handshake, bandwidth). Small, often negligible; kept explicit so the
  model degrades sanely as `magnitude → 0`.

### 5.4 Why This Produces the Trust Curve (not postulates it)

Hold `solo_cost(c)` and `magnitude(c)` fixed and vary the counterparty:

- **Stranger (trust≈0 → risk=RISK_MAX).** Only items where
  `solo_cost(c)` is high *and* `magnitude(c)` is small clear the
  threshold. → Newcomers transact, but only small and only where I
  truly need help. This *is* §3's probation tier, in arithmetic.
- **Proven partner (trust→1 → risk→RISK_MIN).** `coop_cost(c)`
  collapses toward `transport_cost`; nearly every matched item clears.
  → Trust, earned through §4 outcomes, mechanically unlocks
  larger-magnitude cooperation over time.

The "cooperation becomes the path of least resistance as trust grows"
thesis is therefore an **output** of the cost model, not an assumption
bolted onto it.

### 5.5 Worked Example

`solo_cost(market_data) = 8`, `transport = 1`, `RISK_MAX = 1.0`,
`RISK_MIN = 0.1`.

- Stranger, small ask: `trust=0 → risk=1.0`; `magnitude=2`.
  `coop_cost = 1 + 1.0×2 = 3 < 8` → **cooperate (small).**
- Stranger, large ask: same trust; `magnitude=10`.
  `coop_cost = 1 + 1.0×10 = 11 ≥ 8` → **pass.** (Probation cap.)
- Proven partner, large ask: `trust=0.9 → risk=0.19`; `magnitude=10`.
  `coop_cost = 1 + 0.19×10 = 2.9 < 8` → **cooperate (large).**

Same capability, same network. Behavior differs purely by earned trust
and requested magnitude. The equation bites.

### 5.6 Defaults and Tuning

Reference constants (implementors MAY override; values are not
protocol-normative, the *shape* is):

    RISK_MAX = 1.0      RISK_MIN = 0.1
    transport_cost = 1  default solo_cost(c) = 5   default magnitude = 1

Only the **structure** — per-capability comparison, `risk` decreasing
in trust, `risk × magnitude` as the risk term — is normative. The
numbers are an agent's private business.

> **Design decisions (on record).**
> 1. Cost is per-capability; one encounter can mix cooperate and pass.
> 2. `coop_cost = transport + risk × magnitude`; risk is the only term
>    fed by reputation, keeping the reputation→decision bridge to a
>    single, auditable product.
> 3. `solo_cost` and `magnitude` are private and per-item; the card
>    never reveals them — no strategic leak of what I find cheap or dear.
> 4. The trust curve is derived from the model, not postulated. v0.1's
>    decorative equation is now load-bearing.

---


## 6. Matching & Capability Namespacing

### 6.1 The v0.1 Failure

v0.1 matched capabilities by exact string set-intersection:
`set(a.capabilities) & set(b.surplus)`. Two agents that should
obviously cooperate would pass each other unless their humans had
pre-agreed on identical token spellings — which silently requires the
very coordination the protocol claims to eliminate. Worse, it gave the
*illusion* of decentralized discovery while depending on out-of-band
vocabulary alignment.

### 6.2 The Distinction That Resolves It

"No central authority" forbids a **registry** (a runtime service
everyone must query). It does **not** forbid a **shared reference** (a
forkable vocabulary that anyone extends and no one approves). FLP
provides shared reference without a center, in three degrading layers.

### 6.3 Layer 1 — Namespaced Capability URIs

Capabilities are URIs, not bare words:

    flp:cap/<domain>/<capability>
    e.g.  flp:cap/data/market-research
          flp:cap/lang/translation/es-quechua
          flp:cap/tourism/venue-availability

Namespacing removes the collision and ambiguity of bare tokens
(`research` meaning ten different things) and lets domains evolve
independently. Exact match on the full URI is the highest-confidence
signal and the cheapest to compute.

### 6.4 Layer 2 — The Core Vocabulary (forkable, not governed)

A **core vocabulary** of common capability URIs lives in the repo:
`/vocabulary/core.json`. It is a convention, not an authority:

- Anyone extends it by pull request or by **forking** — no approval
  gate, mirroring IMPLEMENTATIONS.md's philosophy.
- Agents declare which vocabulary version(s) they speak in their card
  (`vocab: ["flp-core/1", "rodstudio/1"]`).
- Unknown namespaces are not errors — they are simply unmatched at
  Layer 1 and fall through to Layer 3.

The core vocabulary is a *Schelling point* — a default everyone can
choose without being forced to. Its power is gravity, not law.

### 6.5 Layer 3 — Local Semantic Matching (optional, never central)

When URIs don't match exactly, an agent MAY apply its **own** local
matcher to decide whether `their.surplus` semantically satisfies
`my.needs` — e.g. local embeddings, a synonym table, or an LLM the
agent already runs. Strict requirements:

1. **Local only.** The matcher runs inside the agent. There is no
   shared semantic oracle to query — that would be a center. Two agents
   may legitimately reach different match conclusions; that is
   acceptable and expected (it mirrors §4's relational reputation).
2. **Advisory, not authoritative.** A semantic match is a *candidate*,
   never a confirmed capability. It feeds the cost model at **elevated
   risk** (see 6.7), because a fuzzy match is more likely to be wrong or
   gamed than an exact one.
3. **Opt-in.** Agents with no semantic layer simply operate at Layers
   1–2. The protocol is fully functional without Layer 3; it is an
   enhancement, not a dependency.

### 6.6 Matching Is Adversarial (the surplus inflator)

Under the §1 threat model, a declared surplus is a *claim*, not a fact:
the surplus inflator advertises capabilities it cannot fulfill to bait
cooperation. Therefore matching never grants trust. A match — exact or
semantic — only establishes that cooperation is *topically possible*.
Whether to act on it is decided entirely by §5 with §4's risk term:

- A first exchange on any match starts at **probation magnitude**
  (small), so an inflated claim, if false, costs the victim little.
- A failed delivery on a claimed capability produces a §4 negative
  outcome, raising `risk` for all future exchanges with that agent.
- Thus surplus inflation is self-limiting: it can win only small, once,
  and pays reputation for it.

Matching proposes. The cost model, weighted by reputation, disposes.

### 6.7 Match Confidence Feeds Risk

Match quality enters the cost model as a multiplier on counterparty
risk, unifying §6 with §5:

    match_confidence:  exact-URI = 1.0
                       core-vocab synonym = ~0.8
                       local-semantic = ~0.5 (agent-tuned)

    effective_risk(c) = risk(me→X) / match_confidence(c)

A fuzzy (low-confidence) match inflates effective risk, so it clears
the cost threshold only at smaller magnitude or higher trust — exactly
the caution a fuzzy match warrants. Exact matches pay no penalty. This
keeps Layer 3's flexibility from becoming an attack surface: the less
certain the match, the more trust or the smaller the stakes required.

> **Design decisions (on record).**
> 1. Capabilities are namespaced URIs, not bare tokens — kills v0.1's
>    exact-spelling fragility.
> 2. A shared *forkable vocabulary* gives reference without a registry;
>    "no center" ≠ "no common language."
> 3. Semantic matching is permitted but strictly **local, advisory, and
>    opt-in** — no shared oracle, so no center sneaks back in.
> 4. Matching never confers trust; it only opens the door. §5+§4 decide
>    whether to walk through, so the surplus inflator is defeated by
>    cost, not by detection.
> 5. Lower match confidence → higher effective risk → smaller/safer
>    exchanges. Flexibility and safety are the same dial.

---

## 7. Federated Discovery

### 7.1 Principle: Discovery Rides the Trust Graph

FLP has no registry. An agent is not found by querying a directory;
it is found by **traversal of the same trust graph that carries
reputation** (§4.5). This is deliberate: discovering an agent outside
your trust horizon is pointless, because the cost model (§5) would
treat it as maximum risk anyway. Discovery and reputation therefore
share one frontier — `MAX_DEPTH` — by design, not coincidence. You meet
the agents your trusted peers have met; that is exactly the set with
whom cooperation can clear the cost threshold.

### 7.2 Layer 1 — Well-Known Card Endpoint

Every FLP agent publishes its signed card at a conventional path:

    GET https://<host>/.well-known/flp-card

Returns the signed card envelope (§2.3). This is the `did:key` +
well-known pattern: if you know an agent's host, you can fetch and
**cryptographically verify** its card with no third party. Direct
knowledge of a host is the zeroth, always-available discovery path.

### 7.3 Layer 2 — Peer Referral (gossip, bounded)

An agent you already trust can refer others to you. Referral is a
signed statement:

    {
      "body": {
        "type": "referral",
        "subject": "did:key:...(the agent being referred)...",
        "subject_endpoint": "https://...",
        "context": "flp:cap/data/market-research",
        "issued_at": ..., "nonce": "..."
      },
      "agent_id": "did:key:...(the referrer)...",
      "sig": "..."
    }

Referrals propagate **only within `MAX_DEPTH`** and are weighted by
`trust(me → referrer)` exactly as testimony is (§4.5). A referral is
not an endorsement of capability — it is a pointer plus a verifiable
"I have transacted with this agent." The receiver still fetches the
card, still verifies, still starts at probation magnitude. Referral
shortens *finding*; it does not shortcut *trust*.

### 7.4 Layer 3 — Broadcast Channels (optional, untrusted by default)

Agents MAY publish cards to open pub/sub channels (a topic, a relay, a
shared list like IMPLEMENTATIONS.md). This is permitted but carries
**zero inherent trust**: a card found by broadcast is a card from a
stranger at `trust = 0`, discoverable but only transactable at
probation magnitude. Broadcast maximizes reach; the cost model ensures
reach never implies safety. This is how a cold network bootstraps
density without a registry — and why §1.4 warns that trust signals are
weak until that density exists.

### 7.5 Endpoint Validation Is Mandatory (SSRF defense)

Because an `endpoint` arrives inside an untrusted card, fetching it
naively is a confused-deputy / SSRF vector (§1.1): an attacker points
your agent at internal services. Before any FLP agent performs an
outbound request to a card- or referral-supplied URL, it MUST:

1. Require `https://` scheme (reject `http`, `file`, `gopher`, etc.).
2. Resolve the host and **reject private, loopback, link-local, and
   reserved ranges** — `127.0.0.0/8`, `10/8`, `172.16/12`,
   `192.168/16`, `169.254/16` (cloud metadata), `::1`, ULA, etc.
3. Re-check after DNS resolution and after any redirect (defeat
   DNS-rebinding and redirect-to-internal); do not follow cross-host
   redirects without re-validating.
4. Enforce a timeout and a response-size cap.

These are normative MUSTs, not suggestions. v0.1's `probe` and
`attempt_http_bootstrap` fetched arbitrary URLs with none of these
checks; v1.0 forbids that.

### 7.6 Bootstrap, Revisited (no endpoint spraying)

v0.1's bootstrap POSTed an invitation to five guessed paths
(`/webhook`, `/api/message`, …) on any host — unsolicited and abusable.
v1.0 replaces this with a single, consent-respecting mechanism:

- The invitation is delivered **only** to the agent's published
  `/.well-known/flp-card` host via a single well-known path
  `POST /.well-known/flp-bootstrap`, **or** out-of-band by the human
  operator (§ human relay). No path-guessing, no spraying.
- The bootstrap payload is signed by the inviter, so the recipient can
  verify who is inviting before acting.
- A non-FLP host simply 404s the well-known path; that is a clean,
  quiet negative, not five blind POSTs.

> **Design decisions (on record).**
> 1. Discovery rides the trust graph and shares reputation's horizon
>    (`MAX_DEPTH`) — you find exactly whom you could trust.
> 2. Three layers: well-known card (verifiable), bounded referral
>    (gossip), open broadcast (reach without trust).
> 3. Referral shortens finding, never shortcuts trust; broadcast =
>    trust 0; both still start at probation magnitude.
> 4. Endpoint validation against SSRF is a normative MUST — closes
>    v0.1's open confused-deputy hole.
> 5. Bootstrap is single, signed, and consent-respecting — no endpoint
>    spraying.

---

## 8. Wire Format & Endpoints

### 8.1 The Signed Envelope Is the Only Wire Object

Every object on the wire is a signed envelope (§2.3). There are no
unsigned FLP messages in v1.0.

    {
      "flp_version": "1.0",
      "body": { "type": "<object-type>", ... },
      "agent_id": "did:key:z6Mk...",
      "sig": "base64(ed25519_sign(JCS(body)))"
    }

`type` ∈ { `card`, `proposal`, `response`, `outcome_attestation`,
`referral`, `bootstrap` }. The receiver dispatches on `body.type` after
verifying `sig` against the key embedded in `agent_id`. **Verification
precedes parsing:** an envelope whose signature fails is dropped before
its body is interpreted.

### 8.2 Tolerant Deserialization (normative)

Parsing MUST ignore unknown fields, never reject on them.

    # Correct — forward-compatible
    known = {f.name for f in fields(FLPCard)}
    card = FLPCard(**{k: v for k, v in data.items() if k in known})

    # Forbidden — v0.1's bug
    card = FLPCard(**data)        # TypeError on any new field

A v1.0 agent receiving a v1.1 card MUST consume the fields it
understands and silently ignore the rest. Required-field *absence* is
an error; unexpected-field *presence* is not. This single rule is what
lets the network span versions without partitioning.

### 8.3 Object Bodies

**Card** (published, signed, expiring):

    {
      "type": "card",
      "agent_id": "did:key:...",
      "objective": "string",
      "needs":   ["flp:cap/...", ...],   // renamed from v0.1 "capabilities"
      "surplus": ["flp:cap/...", ...],
      "vocab":   ["flp-core/1", ...],
      "endpoint": "https://...",
      "language": "es",
      "tags": [...],
      "settlement_type": "digital",      // default; "physical"|"asset" reserved (§10)
      "issued_at": 1234567890,
      "expires_at": 1234654290
    }

> `capabilities` → `needs` is a deliberate rename: the field always
> meant "what I need," and v0.1's name caused exactly the surplus/needs
> confusion that broke the demo. `cost_to_share` is **removed** — cost
> is now private and per-capability (§5.3), never published.

**Proposal** (per-capability, only cleared items):

    {
      "type": "proposal",
      "proposal_id": "uuid4",            // full UUID, not 8 chars (§8.5)
      "to_agent": "did:key:...",
      "items": [
        { "capability": "flp:cap/data/market-research",
          "direction": "i_need" | "i_offer",
          "magnitude": 2,
          "match_confidence": 1.0 }
      ],
      "issued_at": ..., "nonce": "..."
    }

**Response:**

    {
      "type": "response",
      "proposal_id": "...",
      "decision": "accept" | "counter" | "decline",
      "counter_items": [ ... ] | null,   // counter is now implemented
      "reason": "string",
      "issued_at": ..., "nonce": "..."
    }

**Outcome attestation:** as defined in §4.3.

### 8.4 Endpoints

| Method | Path | Body in | Body out | Notes |
|--------|------|---------|----------|-------|
| GET  | `/.well-known/flp-card` | — | signed card | §7.2 |
| POST | `/flp/encounter` | signed card | signed proposal \| `{decision:"pass"}` | evaluate & maybe propose |
| POST | `/flp/respond`   | signed proposal | signed response | accept/counter/decline |
| POST | `/flp/outcome`   | signed attestation | signed attestation | bilateral close (§4.3) |
| POST | `/.well-known/flp-bootstrap` | signed bootstrap | 202 \| 404 | §7.6 |
| GET  | `/flp/status`    | — | agent's own encounter stats | introspection only |

Every endpoint MUST: verify the inbound signature before acting (8.1);
validate any supplied endpoint URL before fetching (§7.5); return its
own outputs as signed envelopes. `/flp/outcome` is new in v1.0 — v0.1
had no way to *close* a cooperation, which is why reputation was
impossible.

### 8.5 Identifiers

`proposal_id` is a full UUIDv4 (128-bit), not v0.1's 8-char truncation
(32-bit, birthday-collision-prone at network scale). `nonce` is ≥128-bit
random, unique per message, retained for the replay window (§2.4).

### 8.6 Errors

Errors are signed envelopes with `body.type = "error"` and a stable
`code`:

    invalid_signature · expired · replay_detected · version_unsupported
    unknown_capability · validation_failed · rate_limited · ssrf_blocked

An agent MUST NOT leak internal detail in error bodies (no stack
traces, no internal hostnames — itself an SSRF/recon hygiene point).

---

## 9. Versioning & Compatibility

### 9.1 What v0.1 Promised and Never Did

v0.1 §6 stated agents "should reject proposals from incompatible
versions and log the incompatibility." No code path ever read
`flp_version`. v1.0 makes version handling real and normative.

### 9.2 Semantic Versioning of the Protocol

FLP versions are `MAJOR.MINOR`:

- **MINOR** bump = backward-compatible additions (new optional fields,
  new capability namespaces, new object types a peer may ignore). A
  v1.0 agent and a v1.1 agent MUST interoperate, each using the subset
  it understands, via tolerant deserialization (§8.2).
- **MAJOR** bump = breaking change (altered signing scheme, changed
  required fields, changed evaluation semantics). Cross-major
  interaction is **not** assumed safe.

### 9.3 Negotiation (normative)

On every inbound envelope, the receiver reads `flp_version` and:

    same MAJOR        → proceed (ignore unknown fields per §8.2)
    higher MINOR, same MAJOR → proceed; treat unknown additions as absent
    lower MINOR, same MAJOR  → proceed; do not send fields the peer
                               predates as *required*
    different MAJOR    → respond error{code:"version_unsupported",
                               supported:["1.x"]} and log; do not act
                               on the body

Rejection is explicit, signed, and logged — never a silent drop, so the
peer learns *why* and can downgrade or upgrade.

### 9.4 Vocabulary Versioning Is Independent

Capability vocabulary (§6.4) versions **separately** from the protocol.
An agent declares `vocab` in its card; a vocabulary mismatch is not a
protocol-version error — unknown namespaces simply fall through to
Layer-3 semantic matching (§6.5) or go unmatched. Protocol version
governs *how agents talk*; vocabulary version governs *what they talk
about*. Decoupling them lets domains (tourism, translation, finance)
evolve their vocabularies without ever forcing a protocol bump.

### 9.5 Capability Discovery of Versions

`GET /flp/status` and the card both expose `flp_version` and `vocab`,
so a peer can determine compatibility **before** proposing — a cheap
pre-flight that avoids spending a full signed round-trip only to hit a
`version_unsupported`.

> **Design decisions (on record).**
> 1. Version handling is normative and real, not aspirational (v0.1's
>    gap closed).
> 2. MINOR = compatible (tolerant parsing carries it); MAJOR = explicit
>    signed rejection + log.
> 3. Protocol version and vocabulary version are independent axes — what
>    they talk about evolves without breaking how they talk.

---

## 10. Reserved: FLP-Settlement (Asset Exchange Layer) — v2+

This section reserves namespace and states intent for a future layer.
It defines **no normative behavior in v1.0.** It exists so the door is
designed open rather than retrofitted, and so the long-term direction is
on record.

### 10.1 Intent

The core (§§1–9) matches surplus to need and establishes trust,
substrate-independently (§1.5). **FLP-Settlement** is the planned layer
that lets the cooperated-upon value be a real-world asset a human
principal owns — a farm agent trading production surplus to cover the
farm's input deficits; a studio agent exchanging rendered output for
compute. This is the long-term goal: the same identity, reputation, and
discovery substrate serving data, services, *and* physical goods.

### 10.2 Why It Is a Layer, Not Core (recorded so it is not relitigated)

Three problems make physical/asset settlement categorically different
from digital cooperation, and all three are why it stays above the core:

- **The oracle problem.** Agents can witness an in-protocol digital
  delivery and sign §4.3 attestations from direct knowledge. They
  *cannot* witness whether 500 kg of tomatoes arrived, fresh, in the
  agreed amount. A `fulfilled` signature on a physical exchange relays
  the human's claim — it is hearsay, not the field-truth that §4
  reputation depends on. Settlement must supply its own verification
  (delivery receipts, escrow, third-party oracles); the core must not
  pretend its attestations cover it.
- **Pricing & clearing.** Data-for-data is topical matching. Goods
  imply quantity, divisibility, unit of account, and escrow — a
  clearing market, a different protocol from a matchmaker.
- **Fiduciary authority.** An agent committing a human's goods needs
  spend limits, representation bounds, and human-in-the-loop — an
  application-layer concern, not a wire concern.

### 10.3 The One Hard Rule for the Future Build

When FLP-Settlement is built, **non-witnessable settlement outcomes
MUST NOT feed the same `trust(me→X)` graph as witnessable digital
ones.** Otherwise an attacker farms infalsifiable reputation through
self-reported physical "successes" and then spends it on digital
exchanges. Physical/asset reputation is a **separate, clearly labeled
graph** carrying a lower-quality trust signal. This rule is recorded
now so the v2 build inherits it rather than discovering it through an
exploit.

### 10.4 Reserved Surface

- Card field `settlement_type ∈ {digital (default), physical, asset}`
  (§8.3). v1.0 agents treat non-`digital` as informational only.
- Capability namespace `flp:settle/*` is reserved for this layer.
- Object types `escrow`, `delivery_receipt`, `settlement_dispute` are
  reserved and unused in v1.0.

> **Design decision (on record).** Asset exchange is the long-term
> destination, but it enters as a settlement layer *above* a
> settlement-agnostic core — never baked in. This keeps v1.0 a general
> matchmaker (good for data, services, and goods alike) instead of
> collapsing it into one economy, and keeps the witnessable-reputation
> guarantee intact.

---

## Appendix A — Conceptual Completeness Map

How v1.0 closes each v0.1 weakness identified in audit:

| v0.1 weakness | v1.0 resolution |
|---------------|-----------------|
| No identity / spoofable agent_id | §2 Ed25519 self-certifying `did:key` |
| Cost model never bites (match ⇒ cooperate) | §5 per-capability `transport + risk×magnitude` |
| Exact-string matching needs shared vocab | §6 namespaced URIs + forkable vocab + local semantics |
| No way to close a cooperation (`outcome` unused) | §8.4 `/flp/outcome`, bilateral attestation §4.3 |
| No reputation | §4 relational trust, distance-decayed |
| Sybil / whitewashing undefended | §3 + §4.5 unprofitability via curve + topology |
| Defamation possible | §4.3 bilateral signatures required |
| SSRF in probe/bootstrap | §7.5 mandatory endpoint validation |
| Bootstrap sprays 5 endpoints | §7.6 single signed well-known path |
| `FLPCard(**data)` breaks on new fields | §8.2 tolerant deserialization |
| Version check promised, absent | §9 normative negotiation |
| `proposal_id` 8-char collision risk | §8.5 full UUIDv4 |

---

*FLP v1.0 (DRAFT). Conceptual specification complete. Reference
implementation (signed identity + relational reputation) to follow.*
*Flower of Life Protocol — Rod Studio, 2026. This specification is licensed under CC BY 4.0; the reference implementation under Apache-2.0.*
