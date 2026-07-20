# Changelog

All notable changes to the Flower of Life Protocol (spec + reference
implementation) are documented here. The project follows semantic
versioning as specified in PROTOCOL.md §9.

## [Unreleased]

### Added
- **PROTOCOL.md §6.8 — Where Intent Lives**: records why the protocol has
  no deep-intent field (unverifiable; cuts against selective disclosure;
  contract-layer material per §1.5/§10).
- Publish kit: NOTICE, LICENSE-SPEC (CC BY 4.0 text), CONTRIBUTING.md,
  CODE_OF_CONDUCT.md, SECURITY.md, CITATION.cff, llms.txt, CHANGELOG.md,
  GitHub CI (pytest on Python 3.10–3.12) and issue/PR templates,
  docs/appendix-A.md (reproduction guide).

### Changed
- README refreshed for v1.1: 87 tests, roadmap marks v1.1 as shipped
  (witnessed attestation moves to v1.2), links to the publish kit.

## [1.1.0] — 2026-07-06

### Added
- **PROTOCOL.md §11 — Formal Model**: cooperation threshold `T*`, trust
  propagation with decay, percolation conjecture (§11.3), and the relation
  to EigenTrust and webs of trust (§11.4).
- **Capability Manifest draft v0.2**
  (docs/CAPABILITY_MANIFEST_spec_v0.2.md): manifest spec with domain
  separation, Merkle selective disclosure, tier challenge, and conformance
  tests (tests/test_manifest.py).
- **Inflated-claim experiment harness** (stranger_harness.py,
  docs/experiments/inflated_claim.md): lying about capabilities is strictly
  unprofitable over 50 identical trials (Manifest spec §8.5, closing the
  PROTOCOL.md §6.7 loop).
- Test suite grew from 74 to **87 tests**.

### Changed
- License clarified to match the recorded decision: **Apache-2.0** for code,
  **CC BY 4.0** for the specification and docs.
- `pip install` URL fixed to the canonical repository
  (github.com/MontanaMiramar/flower-of-life-protocol).
- Version strings aligned across README, pyproject, and package metadata.

## [1.0.0] — 2026-06-30

### Added
- Initial public release: FLP core (identity §2, newcomer rules §3,
  relational reputation §4, cost model §5, matching §6, federated
  discovery §7, wire format §8, versioning §9).
- Layer 3 local semantic matching (optional, never central).
- `vocabulary/core.json` bridges — the forkable core vocabulary.
- docs/LIMITATIONS.md — what FLP does not solve, stated honestly.
- Reference HTTP server/client with SSRF defense (§7.5), six runnable
  demos, 74 tests.
