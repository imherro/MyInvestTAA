# CURRENT_TAA Strategy Rebuild Decisions V1

## Purpose

This document records the decisions agreed before rebuilding the investment strategy. It does not define final trading parameters.

## Product Direction

- The repository will not be rolled back as a whole.
- The existing Tushare data path, atomic report publication, ETF mapping, Shadow tracking, FastAPI/Jinja Web stack, and port 8025 remain in place.
- The target strategy studies deep drawdown mispricing and recovery in long-lived assets.
- Cross-asset momentum Top-N selection is a legacy baseline, not the target investment model.
- The current runtime path remains unchanged until research produces a frozen candidate specification.

## Research Boundary

- Only the 32 A/B/C assets in `MyInvestTAA_全收益指数研究资产范围_V1.0.docx` are allowed.
- D-tier and unlisted assets must be rejected by code.
- Research uses total-return indexes only. ETF history does not participate in index parameter research.
- Research order is A7, then B12, then C13.
- Each asset is researched independently before portfolio construction.
- Risk-family exposures must be aggregated; correlated indexes are not independent diversification.
- Risk families are a closed contract vocabulary. The building-materials index belongs to `industrial_materials`, because its principal drivers are capacity, raw-material costs, real estate, and fixed investment rather than transport or logistics infrastructure.
- Parameters require walk-forward out-of-sample validation. Full-history optimum parameters cannot be adopted directly.

## Drawdown Semantics

- The primary drawdown reference is the expanding historical high-water mark available as of each date.
- Fixed three-year and five-year peaks are auxiliary diagnostics for structural change.
- A stale historical peak is a warning, not a stronger buy signal.
- Historical maximum drawdown is not a deterministic future bottom.
- A future implementation must never reset a stale peak silently or read information after the research date.

## Data Evidence

- Stable internal `asset_key`, official index code, and Tushare `provider_code` are separate fields.
- An unknown provider mapping remains `null`; suffixes and substitute indexes must not be guessed.
- Provider availability proves only that a code returns valid history. It does not independently prove total-return methodology.
- A total-return conclusion requires explicit project evidence and is represented separately from provider availability.
- Phase P0 adds no valuation, cycle, or fundamental fields. Missing filters are reported as not implemented or unassessed.

## Delivery Sequence

1. P0: machine-readable universe contract and A-tier data audit.
2. P1: A-tier drawdown events, recovery evidence, and research Web views.
3. P2: single-asset strategy families and walk-forward validation.
4. P3/P4: B-tier and C-tier expansion with asset-specific validity checks.
5. P5: risk-family-aware portfolio research.
6. P6: freeze the typed strategy specification and replace the formal CURRENT_TAA model.
7. P7: map selected assets to ETFs and restart meaningful Shadow tracking.

P0 does not modify the current model, current five reports, ETF mappings, Shadow, or Web pages.
