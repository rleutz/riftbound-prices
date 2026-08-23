#!/usr/bin/env python3
"""
Riftbound Price Fetcher
Fetches card prices from TCGCSV (which mirrors TCGPlayer data daily)
and writes riftbound_prices_updated.json in the format the tracker expects.

Runs daily via GitHub Actions. Safe to run manually too.
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── Constants ────────────────────────────────────────────────────────────────

TCGCSV_BASE   = "https://tcgcsv.com/tcgplayer"
CATEGORY_ID   = 89          # Riftbound: League of Legends Trading Card Game
USER_AGENT    = "RiftboundPriceFetcher/1.0 (github.com/rleutz/riftbound-prices)"
SLEEP_BETWEEN = 0.15        # seconds between requests (be a good neighbour)

# Known main sets — these get completion tracking in the tracker
MAIN_SETS = {"OGN", "OGS", "SFD", "UNL", "VEN"}

# Known supplemental/promo sets — prices fetched but flagged as non-main
PROMO_SETS = {"JDG", "OPP", "PR", "RWB", "SGN", "RAD", "LGC"}

# Sets to skip entirely (sealed products only, no singles worth tracking)
SKIP_SETS = set()

# Output path (relative to repo root, matching what the tracker fetches)
OUTPUT_PATH = "prices/riftbound_prices_updated.json"

# ── Helpers ──────────────────────────────────────────────────────────────────

def fetch_json(url: str) -> dict:
    """Fetch a URL and return parsed JSON. Raises on HTTP error."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_card_code(abbreviation: str, number_str: str, is_signature: bool) -> str | None:
    """
    Convert a TCGPlayer card number string into our internal card code.

    Examples:
      OGN  "001/298"      -> "OGN-001"
      OGN  "007a/298"     -> "OGN-007a"
      OGN  "299/298"      -> "OGN-299"        (overnumbered)
      OGN  "299*/298"     -> "OGN-299-SIG"    (signature)
      SFD  "224*/221"     -> "SFD-224-SIG"
    """
    if not number_str:
        return None

    # Strip the "/NNN" printed total suffix
    raw = number_str.split("/")[0].strip()   # e.g. "007a", "299*", "007"

    # Detect and strip the signature marker
    sig = raw.endswith("*")
    if sig:
        raw = raw[:-1]                        # "299*" → "299"

    # raw is now something like "001", "007a", "299"
    # We keep the alpha suffix (a, b …) as-is — it's part of our code scheme
    code = f"{abbreviation}-{raw}"

    if sig:
        code += "-SIG"

    return code


def is_real_card(product: dict) -> bool:
    """
    Return True if this product is a playable card (not a sealed product,
    token, or other non-card item).
    Products with no extendedData are sealed products — skip them.
    Tokens and Buffs are fine to skip too.
    """
    ext = product.get("extendedData", [])
    if not ext:
        return False

    # Build a quick lookup of extendedData fields
    fields = {e["name"]: e["value"] for e in ext}

    card_type = fields.get("Card Type", "")
    number    = fields.get("Number", "")

    # Skip if no number (shouldn't happen for real cards, but safety)
    if not number:
        return False

    # Skip pure tokens (Recruit, Buff, Sprite) — they don't have market prices
    # and aren't tracked in the collection
    skip_types = {"Token", "Unit;Token"}
    if card_type in skip_types:
        return False

    # "Buff" token appears as Card Type "Token" with no Number — already caught above
    return True


# ── Main logic ───────────────────────────────────────────────────────────────

def fetch_all_prices() -> dict:
    """
    1. Fetch group list for category 89
    2. For each group, fetch products + prices
    3. Join on productId, build card codes, collect market prices
    4. Return prices dict + metadata
    """

    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting price fetch …")

    # Step 1: get groups
    groups_url = f"{TCGCSV_BASE}/{CATEGORY_ID}/groups"
    print(f"  Fetching groups: {groups_url}")
    groups_data = fetch_json(groups_url)
    groups = groups_data.get("results", [])
    print(f"  Found {len(groups)} groups")

    prices_out   = {}   # card_code -> market_price (float)
    set_meta     = {}   # abbreviation -> {name, is_main, card_count, updated}
    new_sets     = []   # sets not in MAIN_SETS or PROMO_SETS

    for group in groups:
        group_id = group["groupId"]
        abbr     = group.get("abbreviation", "").strip()
        name     = group.get("name", "")

        if not abbr:
            print(f"  Skipping group {group_id} '{name}' — no abbreviation")
            continue

        if abbr in SKIP_SETS:
            print(f"  Skipping {abbr} (in SKIP_SETS)")
            continue

        is_main  = abbr in MAIN_SETS
        is_promo = abbr in PROMO_SETS

        # Detect unknown sets
        if not is_main and not is_promo:
            new_sets.append({"abbreviation": abbr, "name": name, "groupId": group_id})
            print(f"  ⚠️  NEW SET DETECTED: {abbr} ({name})")

        print(f"  Processing {abbr} ({name}, groupId={group_id}) …")

        # Step 2a: fetch products
        products_url = f"{TCGCSV_BASE}/{CATEGORY_ID}/{group_id}/products"
        time.sleep(SLEEP_BETWEEN)
        try:
            prod_data = fetch_json(products_url)
        except Exception as e:
            print(f"    ERROR fetching products: {e}")
            continue

        products = prod_data.get("results", [])

        # Build productId -> card_code map (only real cards)
        id_to_code = {}
        for p in products:
            if not is_real_card(p):
                continue
            fields  = {e["name"]: e["value"] for e in p.get("extendedData", [])}
            number  = fields.get("Number", "")
            is_sig  = "*" in number
            code    = build_card_code(abbr, number, is_sig)
            if code:
                id_to_code[p["productId"]] = code

        print(f"    {len(id_to_code)} playable cards found")

        # Step 2b: fetch prices
        prices_url = f"{TCGCSV_BASE}/{CATEGORY_ID}/{group_id}/prices"
        time.sleep(SLEEP_BETWEEN)
        try:
            price_data = fetch_json(prices_url)
        except Exception as e:
            print(f"    ERROR fetching prices: {e}")
            continue

        price_results = price_data.get("results", [])

        # For each price entry, find the matching card code
        # A product can have multiple subTypes (Normal, Foil etc.)
        # We want the Non-Foil market price first; fall back to Foil if that's all there is
        # Build: productId -> {subTypeName -> marketPrice}
        prod_prices: dict[int, dict[str, float]] = {}
        for pr in price_results:
            pid   = pr.get("productId")
            sub   = pr.get("subTypeName", "Normal")
            mkt   = pr.get("marketPrice")
            if pid is None or mkt is None:
                continue
            if pid not in prod_prices:
                prod_prices[pid] = {}
            prod_prices[pid][sub] = mkt

        # Now pick the best price per card
        SET_CARD_COUNT = 0
        for pid, code in id_to_code.items():
            if pid not in prod_prices:
                continue
            subs = prod_prices[pid]
            # Preference order: Normal > Foil > whatever
            price = (
                subs.get("Normal")
                or subs.get("Foil")
                or next(iter(subs.values()), None)
            )
            if price is not None:
                prices_out[code] = round(float(price), 2)
                SET_CARD_COUNT += 1

        print(f"    {SET_CARD_COUNT} prices recorded")

        set_meta[abbr] = {
            "name":       name,
            "groupId":    group_id,
            "is_main":    is_main,
            "is_promo":   is_promo or (not is_main),
            "card_count": len(id_to_code),
            "priced":     SET_CARD_COUNT,
        }

        time.sleep(SLEEP_BETWEEN)

    return {
        "prices":    prices_out,
        "updated":   datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "set_meta":  set_meta,
        "new_sets":  new_sets,
    }


def write_output(data: dict, path: str) -> None:
    """Write the prices JSON file."""
    import os
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Wrote {len(data['prices'])} prices to {path}")


def print_summary(data: dict) -> None:
    """Print a human-readable summary."""
    print("\n── Summary ─────────────────────────────────────────────")
    for abbr, meta in sorted(data["set_meta"].items()):
        tag = "MAIN" if meta["is_main"] else "PROMO"
        print(f"  [{tag}] {abbr:6s}  {meta['name']:40s}  "
              f"{meta['priced']:4d}/{meta['card_count']} cards priced")

    if data["new_sets"]:
        print("\n⚠️  NEW SETS DETECTED (not yet in tracker):")
        for s in data["new_sets"]:
            print(f"    {s['abbreviation']:6s}  {s['name']}  (groupId={s['groupId']})")

    print(f"\n  Total prices: {len(data['prices'])}")
    print(f"  Updated:      {data['updated']}")
    print("────────────────────────────────────────────────────────")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import os

    # Allow overriding output path via env var (used by GitHub Actions)
    out_path = os.environ.get("OUTPUT_PATH", OUTPUT_PATH)

    data = fetch_all_prices()
    write_output(data, out_path)
    print_summary(data)

    # Exit with code 1 if new sets were found, so the GH Action knows to open an issue
    if data["new_sets"]:
        print("\nExiting with code 1 to trigger new-set issue creation.")
        sys.exit(1)
