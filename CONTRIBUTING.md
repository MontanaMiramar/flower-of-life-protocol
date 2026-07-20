# Contributing to the Flower of Life Protocol

Thanks for your interest in FLP. This project is a protocol specification
plus a reference implementation, and contributions to either are welcome —
but they are reviewed differently.

## Ground rules

- **Every claim in the spec has a test.** If your change alters protocol
  behavior, it must come with a test that demonstrates the new behavior and
  a spec (PROTOCOL.md) edit that records it. Code-only changes to normative
  behavior will not be merged.
- **No center sneaks back in.** FLP's core commitment is that identity,
  reputation, matching, and discovery work without a registry, oracle, or
  shared operator. Contributions that introduce a required central
  component are out of scope, however convenient.
- **Design decisions are on record.** Sections of PROTOCOL.md carry
  `Design decisions (on record)` blocks. If you change a recorded decision,
  update the block and say why — contributors inherit the reasoning, not
  just the result.

## Getting started

```bash
git clone https://github.com/MontanaMiramar/flower-of-life-protocol.git
cd flower-of-life-protocol
python -m venv .venv && source .venv/bin/activate
pip install -e . pytest
pytest -q        # 87 tests should pass
```

The runtime dependencies are deliberately minimal: `cryptography`,
`rfc8785` (JCS), `base58`. Please do not add runtime dependencies without
opening an issue first. Optional features (e.g. Layer 3 semantic matching)
belong in `[project.optional-dependencies]`.

## Pull requests

1. Fork, create a topic branch, keep the diff focused.
2. Run `pytest -q` — the full suite must be green on Python 3.10–3.12.
3. If the change is normative (wire format, signatures, matching, cost
   model, reputation), update PROTOCOL.md in the same PR.
4. Write commit messages that state *what* and *why*, in English.

## Reporting issues

- Bugs and spec ambiguities: open a GitHub issue with a minimal
  reproduction or the exact spec text in question.
- Security issues (identity forgery, signature bypass, Sybil economics,
  SSRF): **do not open a public issue** — see [SECURITY.md](SECURITY.md).

## Licensing of contributions

By contributing you agree that your code contributions are licensed under
Apache-2.0 and your contributions to PROTOCOL.md and `docs/` are
additionally licensed under CC BY 4.0, matching the repository layout
(see LICENSE, LICENSE-SPEC, NOTICE).
