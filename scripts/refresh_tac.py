"""Update independently verified TAC data in stages, preserving last good snapshots.

This collector intentionally does not fabricate burns, staking, special NFT badges,
DNS aliases or service ownership. New token/TON swap events are sourced from the
verified STON.fi pool; USD uses TON/USD rate data and is an estimate.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import assets
import service_registry
import pools
import trades
import observatory
import badges
import domains

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/snapshot.json"
REQUIRED_SOURCE_LABELS = ("burns", "zeroBurns", "identity", "domains", "badges")


def save(snapshot: dict) -> None:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    temporary = DATA.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False,
                                   separators=(",", ":"), allow_nan=False), encoding="utf-8")
    os.replace(temporary, DATA)


def refresh() -> bool:
    now = int(time.time())
    snapshot = json.loads(DATA.read_text(encoding="utf-8"))
    if snapshot.get("token") != assets.MASTER or snapshot.get("schema") != 1:
        raise ValueError("Snapshot token or schema mismatch")
    errors = set(snapshot.get("errors", []))
    errors.update(name for name in REQUIRED_SOURCE_LABELS if name not in snapshot)
    updated_any = False

    def stage(key, action, *, interval=0):
        nonlocal updated_any
        previous = snapshot.get(key) or {}
        if previous and now - previous.get("asOf", 0) < interval:
            print(key, "still current", flush=True)
            return
        try:
            result = action(previous)
            if not isinstance(result, dict) or result.get("asOf", 0) <= 0:
                raise ValueError("Missing or malformed section")
            snapshot[key] = result
            errors.discard(key)
            snapshot["updated"] = max(int(time.time()), result["asOf"])
            snapshot["errors"] = sorted(errors)
            save(snapshot)
            updated_any = True
            print(key, "SAVED", len(result.get("rows", result.get("holders", []))), flush=True)
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
            errors.add(key)
            snapshot["errors"] = sorted(errors)
            print(key, "UNAVAILABLE:", type(error).__name__, str(error)[:200], flush=True)

    stage("holders", lambda _: {**assets.holders(), "asOf": now})
    if service_registry.update(snapshot, now, observatory.KNOWN_SERVICES):
        errors.add("serviceRegistry")
    else:
        errors.discard("serviceRegistry")
    snapshot["errors"] = sorted(errors)
    save(snapshot)
    stage("trades", lambda old: trades.collect(old, now - 366 * 86400, now, max_pages=45))
    # Verify accepted burn notifications on the TAC master, never sender requests alone.
    # First scan covers seven days; subsequent scans overlap the last hour for reindexing.
    def collect_burns(old):
        since = max(1, int(old.get("asOf", now - 7 * 86400)) - 3600)
        rows, covered_since = assets.burns(old.get("rows", []), since)
        return {"asOf": now, "since": min(int(old.get("since", covered_since)), covered_since), "rows": rows}
    stage("burns", collect_burns, interval=1800)
    # Zero-address transfers are a distinct verified mechanism, queried less often.
    stage("zeroBurns", lambda old: observatory.zero_burns(old, now), interval=6 * 3600)
    stage("rates", lambda _: {"asOf": now, "rows": trades.rates()}, interval=6 * 3600)
    stage("pools", lambda _: pools.collect(now), interval=24 * 3600)
    # Gradually verify account types; 18 per run avoids exhausting free API quota.
    # Unchecked owners stay unidentified and are never classified from balances.
    stage("identity", lambda _: observatory.identity(snapshot, now, budget=4, pace=1.05), interval=3600)
    # Badge rules are intentionally empty for TAC until verified proofs are configured.
    # Publishing an empty, valid section is distinct from a failed badge source.
    stage("badges", lambda old: {**badges.refresh(old, now), "asOf": now}, interval=6 * 3600)
    # Four-digit DNS ownership is independently verified, not inferred from wallet labels.
    stage("domains", lambda old: domains.enrich(snapshot, now), interval=1800)
    if updated_any:
        snapshot["updated"] = int(time.time())
    snapshot["errors"] = sorted(errors)
    save(snapshot)
    print("TAC snapshot update:", "partial" if errors else "complete", "errors:", sorted(errors), flush=True)
    return updated_any


if __name__ == "__main__":
    refresh()
