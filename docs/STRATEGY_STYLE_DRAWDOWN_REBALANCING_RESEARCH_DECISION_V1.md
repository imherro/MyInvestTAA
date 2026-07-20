# Strategy-Style Drawdown Rebalancing Research Decision V1

## 1. Final Decision

```text
Mechanism decision: REJECTED
Selected profile: null
P2 research lifecycle status: CLOSED
Integration status: DO_NOT_INTEGRATE
```

The frozen P2 strategy-style drawdown rebalancing mechanism did not obtain
out-of-time support. P2 research is closed and must not proceed to allocation
design, portfolio backtesting, cost analysis, or `CURRENT_TAA` integration.

## 2. Formal Evidence

This decision references:

- `data/strategy_style_walk_forward_v1/manifest.json`
- `data/strategy_style_walk_forward_v1/walk_forward_summary.json`
- [STRATEGY_STYLE_FORWARD_OUTCOME_WALK_FORWARD_PREREGISTRATION_V1.md](STRATEGY_STYLE_FORWARD_OUTCOME_WALK_FORWARD_PREREGISTRATION_V1.md)
- [STRATEGY_STYLE_WALK_FORWARD_ARTIFACT_V1.md](STRATEGY_STYLE_WALK_FORWARD_ARTIFACT_V1.md)

The frozen evidence identity is:

```text
source as-of: 2026-07-15
formal OOS folds: WF_2018 through WF_2025
primary horizon: H60
minimum available fold count: 5
profile set: PROFILE_A PROFILE_B PROFILE_C
mechanism decision: REJECTED
selected profile: null
```

Formal result identities:

```text
event_outcomes SHA-256: 19e1687d8e45d058e99c06bc5f7ad6cb65ac0f0eea550bac762d11d98dce3ff0
walk_forward_summary SHA-256: 0ec8c12bdb22fdd9ba2d8abe31652df19d75ff10b1b9e99074474a76dca53f82
```

## 3. Profile Decision Facts

### PROFILE_A

```text
Condition A: false
H60 positive style count: 1
Condition B: false
H60 positive fold count: 2
Condition C: false
H60 available fold count: 8
H60 median of profile fold medians: -0.01979241044189991
Condition D: true
Profile support status: NOT_SUPPORTED
```

### PROFILE_B

```text
Condition A: false
H60 positive style count: 1
Condition B: false
H60 positive fold count: 2
Condition C: false
H60 available fold count: 8
H60 median of profile fold medians: -0.03534636978329121
Condition D: true
Profile support status: NOT_SUPPORTED
```

### PROFILE_C

```text
Condition A: false
H60 positive style count: 0
Condition B: false
H60 positive fold count: 1
Condition C: false
H60 available fold count: 8
H60 median of profile fold medians: -0.04215925113399898
Condition D: false
Profile support status: NOT_SUPPORTED
```

No profile satisfies all preregistered support conditions.

## 4. Interpretation

The H60 primary-horizon median peer-relative direction is negative for all
three profiles. H60 annual consistency is only two, two, and one positive fold,
below the required five. Style breadth is only one, one, and zero positive
style, below the required three.

PROFILE_A and PROFILE_B receive positive H120 secondary confirmation, but a
secondary horizon cannot override failure of the H60 primary-horizon breadth,
annual-consistency, and overall-direction conditions.

This decision rejects only the frozen P2 mechanism, profile set, horizons,
folds, and support logic. It does not establish that every style-rotation or
drawdown-rebalancing method is ineffective.

P2 must not be rescued after the result by adding profiles, changing horizons,
relaxing support thresholds, using development or 2026 prospective outcomes,
or running a portfolio backtest. Those actions would violate the preregistered
research process.

## 5. Downstream Boundary

```text
Allocation design authorization: DENIED
Portfolio backtest authorization: DENIED
CURRENT_TAA integration authorization: DENIED
P2 status: REJECTED / CLOSED
```

`DENIED` applies to this P2 research lifecycle. It records that no further P2
development is authorized and does not alter historical status fields in the
existing manifest.

Any future style research must use a new research version, state a materially
different economic hypothesis or mechanism, and preregister its evidence and
decision rules before viewing new results. It must not be presented as a P2
parameter adjustment.

## 6. Closure

P2 generated no approved profile, allocation, portfolio backtest, cost model,
or production integration. The evidence and rejection decision are retained
for auditability. P2 is formally complete and closed.
