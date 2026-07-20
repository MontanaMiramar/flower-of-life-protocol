# Security Policy

FLP is a trust protocol: its entire value rests on the soundness of its
identity, signature, and reputation mechanics. Security reports are taken
seriously and handled with priority.

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Email **roderickchicas@gmail.com** with subject line `FLP SECURITY:` followed
by a short description. Include a proof of concept if you have one. You will
receive an acknowledgment within 72 hours. Please allow up to 90 days for a
coordinated fix before public disclosure.

## Scope — what counts as a vulnerability here

The threat model is specified in PROTOCOL.md §1. Reports in these areas are
especially valuable:

- **Identity forgery** — any way to produce an envelope that verifies against
  an `agent_id` whose private key you do not hold (Ed25519 misuse, JCS/RFC 8785
  canonicalization ambiguity, did:key parsing confusion, §2).
- **Replay and freshness bypass** — reusing a signed envelope outside its
  intended window or context (§2.4).
- **Sybil economics** — any strategy where creating many fresh identities is
  *profitable* under the newcomer rules and cost model (§3, §5). The design
  goal is that Sybils are unprofitable, not impossible; a report showing
  profitable Sybil behavior is a protocol bug.
- **Reputation poisoning** — forging or laundering outcome attestations,
  defeating the bilateral requirement, or making the dangling penalty
  exploitable (§4).
- **Matching abuse** — surplus inflation or vocabulary tricks that defeat the
  match-confidence risk multiplier (§6.6–6.7).
- **SSRF / endpoint validation bypass** in the reference client (§7.5,
  `flp/net.py`).
- **Selective-disclosure leaks** in the Capability Manifest draft
  (docs/CAPABILITY_MANIFEST_spec_v0.2.md) — proving possession of a
  capability you do not have, or extracting undisclosed manifest entries.

## Out of scope

- Denial of service against a specific deployment (the reference server is
  explicitly not hardened production infrastructure — README "Maturity" note).
- Weak-trust behavior on sparse/cold networks: this is a documented
  limitation (PROTOCOL.md §1.4, docs/LIMITATIONS.md), not a vulnerability.
- Vulnerabilities in dependencies (`cryptography`, `rfc8785`, `base58`) —
  report those upstream, though a note here is appreciated if FLP's usage
  is affected.

## Supported versions

Only the latest tagged release receives security fixes.
