# FLP Capability Manifest — Draft Specification (v0.2, corrected)

Status: **Draft — proposed for v1.1** (alongside witnessed attestation).
License: CC BY 4.0 (spec), Apache-2.0 (reference implementation).

A capability manifest is what an agent **announces** to strangers so that matching (Layers 1–3) can decide, without leaking exploitable detail and without trusting unverified claims. It is not a skills format: it is the discovery-layer unit that federated gossip propagates.

---

## 1. Design principles

1. **Disclosure is a function of trust.** What a requester sees depends on the announcer's trust in that requester. Notation matters: the gate is **T(announcer → requester)** — the announcer's local, relational trust in the party asking. There is no global score anywhere in this spec.
2. **Tiers are announcer policy, not protocol constants.** The example tiers below (`public` / `known` / `trusted`) and any thresholds attached to them are chosen by each announcer. The protocol defines the *mechanism* (tiered, verifiable disclosure), never the *numbers*. Announcers MAY keep their thresholds private and simply answer with whatever tier their local trust permits.
3. **One signature, one mechanism.** Every field of the manifest — including `agent`, `capabilities[].id`, and `capabilities[].namespace` — is a leaf in a single Merkle tree. The announcer signs **only the root**. Fields that are always revealed simply ship with their inclusion proofs by default. There is no separate `signed_over` list; the tree is the signature's scope.
4. **Lying is unprofitable, and here, provable.** Because exact values are committed at signing time, any inconsistency between what was announced coarsely and what is revealed later is cryptographically attributable to the announcer (see §4).

## 2. Structure

```jsonc
{
  "manifest_version": "0.2",
  "agent": {
    "did": "did:key:z6Mk...",             // Ed25519 identity (Pillar 1)
    "issued_at": "2026-07-03T07:22:00Z",
    "expires_at": "2026-07-10T00:00:00Z"  // claim freshness only — see §6
  },

  "capabilities": [
    {
      "id": "cabo.marine.port-status",    // Layer 1: exact match
      "namespace": "cabo.marine",         // Layer 2: namespace match

      "disclosure": {
        "public": {                       // served to any authenticated stranger
          "provides": "Port status and sea conditions for the Los Cabos corridor.",
          "use_when": [
            "requester needs to know whether the port is open",
            "safety check for water activity / fishing"
          ],
          "do_not_use_when": [
            "dining questions -> cabo.dining",
            "land activities -> cabo.activities"
          ],
          "cost_band": "low"              // coarse band, never the exact price (§5)
        },

        "known": {                        // served when announcer's trust in requester is moderate
          "input_schema": { "date": "ISO-8601", "zone": "enum" },
          "cost": { "unit": "per_call", "value": 0.002, "currency": "USD" },
          "constraints": ["rate: 60/min", "cache: 1h"]
        },

        "trusted": {                      // served to high-trust counterparties
          "examples": [ /* real I/O pairs */ ],
          "endpoint_hint": "...",
          "sla": "p95 < 300ms"
        }
      }
    }
  ],

  "commitment": {
    "alg": "merkle-sha256",
    "root": "b3f1..."
  },
  "signature": {
    "alg": "Ed25519",
    "value": "base64..."                  // announcer's did signs commitment.root — nothing else
  }
}
```

`disclosure.public.{provides, use_when, do_not_use_when}` feeds Layer 3 (semantic matching). `do_not_use_when` is not documentation: it is a **negative signal** — an exclusion vector that reduces false positives between strangers whose capabilities look similar by positive similarity alone. Layer 3 remains optional local semantics; a manifest MUST be usable by implementations that never compute embeddings.

## 3. Requester authentication (normative)

Tiered disclosure is meaningless if the announcer cannot verify who is asking. Before serving any tier above `public`, the announcer MUST issue a challenge (random nonce) and the requester MUST return it signed with the private key of its claimed `did:key`. Only then does the announcer look up its local T(announcer → requester) and select the tier. Requests without a valid proof-of-key receive at most the `public` tier.

(This reuses the handshake primitives already defined in PROTOCOL.md; the manifest spec makes the requirement explicit rather than assumed.)

## 4. Selective disclosure with a single signature (Merkle commitment)

Signing the full plaintext manifest breaks verification for anyone who only receives the `public` tier — they cannot recompute the hash over fields they cannot see. The manifest therefore commits per field:

1. Every field of every tier is a leaf: `leaf = H(path || value || salt)`. The per-leaf `salt` prevents brute-forcing hidden low-entropy values.
2. The announcer builds the tree and signs **only the root** with its did.
3. Revealing a tier means shipping its fields **plus their inclusion proofs**.
4. The receiver verifies each revealed field against the signed root without learning anything about unrevealed leaves.

One signed manifest serves every trust level. `public`, `known`, and `trusted` unseal independently and all verify against the same root. No one inflates a claim without the signature exposing it; no one sees more than the announcer's trust in them permits.

**Selective-disclosure scheme:** Merkle-SHA256 is normative for v1.1 — it requires zero new dependencies and is implementable today. BBS+ signatures (more compact proofs, unlinkability) are noted as a possible future profile, not a requirement. Runnable now beats elegant later.

## 5. The cost bootstrap problem (resolved, not ignored)

The cooperation rule `c_ij + (1 − T_ij)·L < c_solo` needs a cost to decide. Hiding the exact cost behind a trust gate creates a deadlock with strangers: low trust → no cost visible → no cooperation → trust never grows.

Resolution: **coarse band public, exact price gated.**

- `public.cost_band ∈ {low, mid, high}` — an order of magnitude, enough for a first cooperation decision under uncertainty. The `(1 − T_ij)·L` term already prices that uncertainty; a first cooperation with a coarse band and a heavy trust penalty is exactly what the rule models.
- `known.cost` — the exact figure, once some history exists.

**Band/cost consistency is verifiable (the provable-lie property).** The exact `cost` was committed in the same Merkle root at signing time. An announcer that publishes `cost_band: "low"` and later reveals a committed `cost` outside that band is caught by anyone holding both proofs — the inconsistency is attributable, non-repudiable, and feeds directly into the counterparty's reputation update. This is "lying made unprofitable" in its strongest local form: here, the lie is not just costly — it is provable. Implementations MUST treat a band/committed-cost mismatch as a failed outcome for reputation purposes.

## 6. Manifest expiry vs. reputation freshness (decoupled)

`expires_at` governs **claim freshness only** — capabilities, schemas, prices change, so manifests are short-lived and re-signed on change. Reputation never travels inside a manifest and is never re-signed with it: trust lives in each agent's local relational store and moves at its own cadence. A new manifest version does not reset, refresh, or assert anything about T. Conflating the two would let announcers launder reputation through re-issuance.

## 7. Integration map

| Existing FLP component            | What the manifest supplies                          |
|-----------------------------------|-----------------------------------------------------|
| Layer 1 (exact)                   | `capabilities[].id`                                 |
| Layer 2 (namespace)               | `capabilities[].namespace`                          |
| Layer 3 (semantic, optional)      | `disclosure.public.{provides, use_when, do_not_use_when}` |
| Ed25519 / did:key (Pillar 1)      | `agent.did` + root signature + requester challenge  |
| Relational reputation (Pillar 2)  | selects which tier the announcer serves             |
| Per-capability cost model (P. 3)  | `cost_band` (public) / `cost` (committed, gated)    |
| Federated discovery (Pillar 5)    | the manifest is the unit that gossip propagates     |

## 8. Conformance tests (required before merge)

- [ ] Round-trip: build tree → sign root → reveal `public` only → verify.
- [ ] Tamper: modify one revealed field → verification fails.
- [ ] Hidden-leaf privacy: `public`-only receiver learns nothing about `known`/`trusted` values (salted leaves resist dictionary attack).
- [ ] Challenge: request for `known` tier without valid proof-of-key is served `public` only.
- [ ] **Inflated claim (stranger harness):** an agent whose `provides` overstates real capability accepts a cooperation, fails it, and loses reputation with the counterparty — closing the loop with §6.7 of the whitepaper. The lie must be strictly unprofitable across repeated trials.
- [ ] **Provable lie:** announcer commits `cost=high-value` but publishes `cost_band: "low"`; on reveal, the mismatch is detected from the two proofs alone and produces a negative outcome record.

## Open questions (tracked, not blocking)

- BBS+ profile: revisit when a maintained, lightweight implementation exists.
- Manifest revocation before `expires_at` (announcer key compromise): likely rides on the same mechanism as identity revocation — defer to the v1.1 witnessed-attestation design.
