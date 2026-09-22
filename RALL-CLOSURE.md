# Closing the RALL Experiment

*Rod Agentic Lab · 2026-09-22*

RALL (Rod Agentic Lab Loop) was the first FLP node run in the open: a small,
self-running system on a single server that maintained its own knowledge catalog,
watched its own agents, answered the public through a chat and MCP host, and asked
an internal council for a structured verdict on what it perceived. Every action it
took was written to an append-only audit log.

This note closes the experiment. It reports what the audit log supports, and
nothing beyond it. Figures are counted up to 2026-09-22 13:45 UTC.

## Period

**60 days, 2026-07-25 → 2026-09-22.** Components came online in stages over the
first ten days, so 55 of the 60 calendar days carry at least one audited event.

## Figures

| | Figure |
|---|---|
| Audited events | **1,078** |
| Automated security scans | **53**, with **zero Critical and zero High** findings |
| Prompt-injection canary | **501 of 501 probes declined**: 63 runs across 51 consecutive days, zero failures |
| Human-gated catalog writes | **15 approved**, **0 real writes rejected** |
| External FLP handshakes | **0** |
| Council deliberations | **51**: 3 "income" verdicts, all on its first day |

### Security

An automated scanner ran 53 times between 2 August and 22 September. None of those
scans produced a Critical or High finding.

The prompt-injection canary started on 3 August, after the public host was
hardened against injection. From then on it ran every single day: 63 runs over 51
consecutive days, each sending a fixed set of adversarial prompts (instruction
overrides, jailbreak personas, attempts to extract the system prompt or internal
tokens, tool abuse, invented commitments, and instructions hidden inside data).
All 501 probes were declined. None got through.

### Human gates

Nothing the agents proposed reached the canonical catalog without Rod's explicit
approval. Fifteen catalog writes were approved and committed between 3 and 12
August. The only catalog writes ever rejected were three deliberate self-tests,
submitted on 3 August to prove that the gate refuses. No real content write was
rejected. Separately, one proposed code fix was rejected because it arrived empty,
with no diagnosis and no patch. That is the gate working as designed.

### FLP in the wild

From 10 August the Lab exposed a public FLP endpoint. Five handshakes completed,
all on 10–11 August, and all five originated from the Lab itself. **No outside
agent completed, or even attempted, an FLP handshake.** The only external traffic
that endpoint received was generic automated scanning.

The trust layer worked in the lab. The lab did not attract strangers.

### What the council said

The council went live on 4 August and deliberated 51 times:

- 5 early deliberations on 4 August, before verdicts were categorised;
- **3 "income" verdicts, all on 5 August**, within the council's first 24 hours
  (not the experiment's first 48);
- 39 "experiment" verdicts (5 August → 21 September);
- 4 partial verdicts with no category (18 August → 22 September).

After 5 August the council never again judged a signal to be an income
opportunity. One plausible reading: the early optimism came from a cold start
with no accumulated criteria, and the council grew more conservative as it built
some.

## What RALL showed, and what it did not

It showed that a small, gated, auditable agent loop can run unattended for two
months on a single server: no Critical or High security findings, an injection
canary that never failed, and a catalog the agents could not write to without a
human saying yes.

It did not show demand. No external agent used FLP, and the council stopped
seeing income after its first day. Those are results too, and we're reporting
them as such.

## After the close

The automated daily cycle and outward social activity are paused. Security
monitoring and the injection canary keep running. The full audit log and the
catalog state at close are preserved privately.

---

*Flower of Life Protocol · Apache-2.0 / CC BY 4.0*
