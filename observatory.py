"""Zero-address burns and identified TON accounts. No staking assumptions."""
import base64
import service_registry
import time
from urllib.parse import urlencode
from assets import DOMAIN, MASTER, MASTER_RAW, fetch, raw_address, resolved_domain, token_amount
from domains import DIGITS
from badges import ZERO

TONCENTER = "https://toncenter.com/api/v3"
ROLES = {"dedust_vault":"DeDust Vault","stonfi_router_v2":"STON.fi Router V2",
         "stonfi_router_v1":"STON.fi Router V1","dedust_pool":"DeDust Pool",
         "stonfi_pool_v2":"STON.fi Pool V2","stonfi_pool_v1":"STON.fi Pool V1"}
RECOVERABLE = (OSError, ValueError, KeyError, RuntimeError)

# Address labels observed in user-provided gram.org screenshots on 2026-11-20.
# External attribution, not cryptographic proof of custodial ownership.
KNOWN_SERVICES = {'0:9ee8e6653451d75816a2e55dc2cd8b1d3baf32651d8631d31858ee8d275c188b': 'Bitget', '0:9650baefe1a7d54893516da54ee8b709a118ac76715aba39c1429b4a497047d1': 'Wallet in Telegram', '0:3b865f3176d329c18280bb36477a2ece4a726955ace73bb27014b5588d8e00b7': 'KuCoin', '0:f938abb44deb73fa56a39b895796017d5b350f9ea9d5db7d52643296dd660edb': 'Bybit', '0:7f8498bf9a0f00c72a44e9ddf17ccea359b45bdd1febd42a5549d309c96696cc': 'TAC Project Multisig', '0:f2a2e706bf1295fa6388e30a99c431ce294aef002727946d013a85dfc1554317': 'KuCoin', '0:c8b0596f090b2415fe55ef2e0785f1c576992bfde436aeac75efcec3ab1f0fac': 'Kraken'}
KNOWN_SERVICE_SOURCES = {'0:9ee8e6653451d75816a2e55dc2cd8b1d3baf32651d8631d31858ee8d275c188b': 'https://gram.org/address/UQCe6OZlNFHXWBai5V3CzYsdO68yZR2GMdMYWO6NJ1wYi5PA', '0:9650baefe1a7d54893516da54ee8b709a118ac76715aba39c1429b4a497047d1': 'https://gram.org/address/UQCWULrv4afVSJNRbaVO6LcJoRisdnFaujnBQptKSXBH0TMO', '0:3b865f3176d329c18280bb36477a2ece4a726955ace73bb27014b5588d8e00b7': 'https://gram.org/address/UQA7hl8xdtMpwYKAuzZHei7OSnJpVaznO7JwFLVYjY4At45g', '0:f938abb44deb73fa56a39b895796017d5b350f9ea9d5db7d52643296dd660edb': 'https://gram.org/address/UQD5OKu0Tetz-lajm4lXlgF9WzUPnqnV231SZDKW3WYO2-1d', '0:7f8498bf9a0f00c72a44e9ddf17ccea359b45bdd1febd42a5549d309c96696cc': 'https://gram.org/address/UQB_hJi_mg8AxypE6d3xfM6jWbRb3R_r1CpVSdMJyWaWzCP6', '0:f2a2e706bf1295fa6388e30a99c431ce294aef002727946d013a85dfc1554317': 'https://gram.org/address/UQDyoucGvxKV-mOI4wqZxDHOKUrvACcnlG0BOoXfwVVDF8MU', '0:c8b0596f090b2415fe55ef2e0785f1c576992bfde436aeac75efcec3ab1f0fac': 'https://gram.org/address/UQDIsFlvCQskFf5V7y4HhfHFdpkr_eQ2rqx1787Dqx8PrG9-'}
SERVICE_LABEL_CHECKED_AT = 1795202469
def role(wallet, account, registry=None):
    if wallet in KNOWN_SERVICES:
        return KNOWN_SERVICES[wallet]
    custody = service_registry.lookup(wallet, registry)
    if custody:
        return custody
    # The network's recognized interfaces are evidence, a large token balance is not.
    known = next((ROLES[i] for i in account.get("interfaces", []) if i in ROLES), None)
    if known:
        return known
    # Keep ordinary wallet contracts distinct from non-wallet smart contracts;
    # do not claim that an unknown contract belongs to any named service.
    if account.get("status") == "active" and account.get("is_wallet") is False:
        return "unclassified_contract"
    return None
def hash_hex(value):
    result = base64.b64decode(value, validate=True)
    if len(result) != 32:
        raise ValueError("Invalid transaction hash")
    return result.hex()


def to_zero(row):
    tx = hash_hex(row["transaction_hash"])
    wallet = raw_address(row["source"])
    amount = int(row["amount"])
    if row["transaction_aborted"] or amount <= 0 or wallet == ZERO:
        return None
    if raw_address(row["destination"]) != ZERO or raw_address(row["jetton_master"]) != MASTER_RAW:
        raise ValueError("Unexpected zero-address transfer")
    event = fetch("/events/" + hash_hex(row["trace_id"]))
    if event["in_progress"]:
        raise ValueError("Zero-address transfer has not finalized")
    for action in event["actions"]:
        if action["type"] != "JettonTransfer" or action["status"] != "ok" or tx not in action["base_transactions"]:
            continue
        transfer = action["JettonTransfer"]
        if ((transfer.get("sender") or {}).get("address") == wallet
                and (transfer.get("recipient") or {}).get("address") == ZERO
                and transfer["jetton"]["address"] == MASTER_RAW and int(transfer["amount"]) == amount):
            return {"kind": "burn", "method": "zero", "time": int(row["transaction_now"]),
                    "tx": tx, "wallet": wallet, "name": None, "tokenAmount": token_amount(amount)}
    return None


def zero_burns(previous, now):
    start = max(1, previous.get("asOf", now - 7 * 86400) - 3600)
    answers = {r["tx"]: r for r in previous.get("rows", []) if r["time"] < start}
    old = {r["tx"]: r for r in previous.get("rows", [])}
    for offset in range(0, 10000, 100):
        query = urlencode({"jetton_master": MASTER, "owner_address": ZERO, "direction": "in",
                           "start_utime": start, "end_utime": now, "offset": offset, "limit": 100})
        rows = fetch("/jetton/transfers?" + query, api=TONCENTER)["jetton_transfers"]
        for item in rows:
            key = hash_hex(item["transaction_hash"])
            if key in answers:
                continue
            row = old.get(key) or to_zero(item)
            if row:
                answers[key] = row
            if key not in old:
                time.sleep(1)
        if len(rows) < 100:
            return {"asOf": now, "rows": sorted(answers.values(), key=lambda r: (-r["time"], r["tx"]))}
    raise RuntimeError("Zero-address pagination limit")


def activation(wallet):
    cursor = 0
    for _ in range(5):
        page = fetch(f"/blockchain/accounts/{wallet}/transactions?sort_order=asc&limit=25&after_lt={cursor}", attempts=2)["transactions"]
        for tx in page:
            if tx["end_status"] == "active":
                if tx["account"]["address"] != wallet or tx["orig_status"] not in ("nonexist", "uninit"):
                    return None
                return int(tx["utime"])
        if len(page) < 25:
            return None
        next_cursor = int(page[-1]["lt"])
        if next_cursor <= cursor:
            raise ValueError("Activation cursor did not advance")
        cursor = next_cursor
    return None


def identity(snapshot, now, budget=32, pace=1.05):
    previous = snapshot.get("identity", {}).get("byWallet", {})
    holders = snapshot.get("holders", {}).get("holders", [])[:100]
    rows = snapshot.get("trades", {}).get("rows", [])[:50] + snapshot.get("burns", {}).get("rows", [])[:50] + snapshot.get("zeroBurns", {}).get("rows", [])[:50]
    visible = list(dict.fromkeys(r["wallet"] for r in holders[:5] + rows + holders[5:]))
    top = {r["wallet"] for r in holders[:30]}
    records = {w: dict(r) for w, r in previous.items()}
    for w in visible:
        records.setdefault(w, {})
        if w in KNOWN_SERVICES:
            records[w].update(role=KNOWN_SERVICES[w], roleSource=KNOWN_SERVICE_SOURCES[w],
                              roleChecked=SERVICE_LABEL_CHECKED_AT)
    queue = sorted(visible, key=lambda w: (w not in top, records[w].get("checked", 0)))
    checks = 0
    for wallet in queue:
        record = records[wallet]
        if checks >= budget:
            break
        if now - record.get("checked", 0) < (4 * 3600 if record.get("domain") else 12 * 3600):
            continue
        checks += 1
        try:
            account = fetch(f"/accounts/{wallet}", attempts=2)
            time.sleep(pace)
            label = role(wallet, account, snapshot.get("serviceRegistry"))
            names = fetch(f"/accounts/{wallet}/dns/backresolve", attempts=2)["domains"] if account["is_wallet"] else []
            domain = None
            linked_digits = []
            candidates = list(dict.fromkeys([*names, (account.get("name") or "").lower()]))
            for name in candidates:
                numeric = DIGITS.fullmatch(name)
                if not DOMAIN.fullmatch(name) or (domain and not numeric):
                    continue
                time.sleep(pace)
                validated = resolved_domain({"address": wallet, "name": name}, strict=True)
                if validated:
                    domain = domain or validated
                    if numeric:
                        linked_digits.append(validated)
            at = record.get("activated")
            if not at and account["is_wallet"] and account.get("status") == "active":
                time.sleep(pace)
                at = activation(wallet)
            record.update(checked=now, domain=domain, linkedDigits=linked_digits, role=label, activated=at)
        except RECOVERABLE as exc:
            print("Identity check:", wallet[:12], exc, flush=True)
        time.sleep(pace)
    return {"byWallet": records, "asOf": now}
