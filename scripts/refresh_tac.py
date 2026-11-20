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
import pools
import trades
import observatory

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
    stage("trades", lambda old: trades.collect(old, now - 366 * 86400, now, max_pages=45))
    stage("rates", lambda _: {"asOf": now, "rows": trades.rates()}, interval=6 * 3600)
    stage("pools", lambda _: pools.collect(now), interval=24 * 3600)
    # Gradually verify account types; 18 per run avoids exhausting free API quota.
    # Unchecked owners stay unidentified and are never classified from balances.
    stage("identity", lambda _: observatory.identity(snapshot, now, budget=18, pace=0.2))
    if updated_any:
        snapshot["updated"] = int(time.time())
    snapshot["errors"] = sorted(errors)
    save(snapshot)
    print("TAC snapshot update:", "partial" if errors else "complete", "errors:", sorted(errors), flush=True)
    return updated_any


if __name__ == "__main__":
    refresh()
