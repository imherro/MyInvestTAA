# Drawdown Event Contract V1

## Scope

This contract defines the point-in-time drawdown fact layer for the seven tier-A assets in `config/research_universe_v1.json`. It does not define drawdown percentiles, recovery probabilities, forward returns, strategy parameters, portfolio weights, ETF mappings, Shadow behavior, or Web pages.

The builder reads only the current universe contract, `reports/strategy_research/universe_audit.json`, and existing total-return caches under `data/research_prices/`. It performs no network access, substitution, cache repair, forward fill, or cross-index splice.

## Eligibility And Binding

Every tier-A asset receives a report. Price analysis requires all of:

- `contract_research_status=available`
- `contract_verification_status=verified`
- `research_ready=true`
- `return_basis_status=confirmed`
- `local_cache_status=available`

Blocked assets retain their contract identity and blockers but have no price source, current state, events, or drawdown series.

Before analysis, the audit `universe_id` and `universe_hash` must match the loaded contract. The audit must contain exactly the seven tier-A assets in research order, without duplicates, and each row's provider code and contract statuses must match. A mismatch fails closed before publication.

## Price Input

Each cache row contains `date`, `close`, and `return_basis=total_return`. History must be non-empty, strictly increasing, unique, valid ISO dates, and finite positive prices. Invalid or unordered data is rejected rather than normalized.

## Point-In-Time Definition

For trading date `t`:

```text
high_watermark(t) = max(price(s)), s <= t
drawdown(t) = price(t) / high_watermark(t) - 1
```

Only observations through `t` may be used. The first observation is a high-watermark state with zero drawdown and no event.

When no event is open, an equal historical high updates `high_watermark_date` to the most recent equal-high date without creating an event. A strictly higher value updates both the watermark value and date.

## Event Boundaries

An event starts on the first observation strictly below the current high watermark. Its `peak_date` is the most recent date at that watermark, `start_date` is the first underwater date, and its deterministic ID is `{asset_key}:{peak_date}`.

Within one continuous underwater period, every new strict low updates the trough. An equal later low does not change `trough_date`, so the first occurrence of the minimum is retained.

The event completes on the first observation whose price is at or above its peak value. Exact recovery and overshoot use the same rule. The recovery day has state `recovered`, carries the completed event ID, is not underwater, and cannot start another event. Its price and date become the current watermark. No tolerance or interpolated recovery is allowed.

An event still underwater on the final observation remains open with `completed=false`, `recovery_date=null`, and `recovery_sessions=null`.

## Event Fields

Each event contains identity, sequence, asset, completion state, peak/start/trough/recovery dates and values, maximum drawdown, last observation date, duration fields, and underwater count.

```text
event_id, event_sequence, asset_key, completed,
peak_date, peak_value, start_date, trough_date, trough_value,
max_drawdown, recovery_date, last_observation_date,
decline_sessions, recovery_sessions, event_span_sessions,
underwater_observations
```

- `decline_sessions`: trough index minus peak index.
- `recovery_sessions`: recovery index minus trough index; null for an open event.
- `event_span_sessions`: recovery index or last-observation index minus peak index.
- `underwater_observations`: count of actual observations with `drawdown < 0`; peak and recovery days are excluded.

Completed events contain final hindsight facts. They must not be used directly as historical decision inputs.

## Daily States

- `high_watermark`: first observation or a high/equal-high reached while no event is open; `event_id=null`.
- `underwater`: price strictly below the open event peak; carries the open event ID.
- `recovered`: first date at or above the open event peak; carries the completed event ID.

Calculations use unrounded inputs. JSON-derived floating values are rounded to at most ten decimal places, negative zero is normalized to zero, and NaN or Infinity is prohibited.

## As-Of Interface

`analyze_drawdown_history(rows, asset_key=..., as_of_date=...)` requires `as_of_date` to be an actual input trading date. It analyzes only rows through that date. It never rolls to another date.

When an as-of date is specified, the engine first locates the matching raw input row and immediately takes the inclusive prefix ending there. Full validation is applied only to that prefix. Rows after the target are not parsed, converted, or validated; even malformed future rows cannot change the historical result or its error state. Errors at or before the target still fail closed. With `as_of_date=None`, the complete input remains subject to strict validation.

For every valid date `t`, analyzing the full input as of `t` must equal analyzing the prefix ending at `t`. Appending future rows must not change the same as-of result. Future troughs, recoveries, and durations therefore cannot enter historical state.

## Reports And Provenance

`reports/strategy_research/drawdown_events/` contains exactly `index.json` and seven asset reports. The index records the raw-byte SHA-256 of the source audit. Each analyzed asset additionally records the raw-byte SHA-256 of its price cache. Blocked assets use null cache path and hash.

Only the index contains `generated_at`. With identical contract, audit, cache bytes, and methodology version, all other business content is deterministic. JSON uses UTF-8, sorted keys, fixed indentation, no non-finite values, and a trailing newline.

The builder stages and validates the complete eight-file set before replacing the output directory. A failed build leaves the prior complete directory intact and no partial report set is published.
