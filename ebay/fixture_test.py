"""Fixture test for ebay/finding.py — proves parsing + scoring against a canned
eBay Finding API JSON response (no network, no real key)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebay import finding

# --- canned eBay JSON: 4 sold items, totalEntries=1250 sold, 4200 active ---
SOLD_JSON = {
    "findCompletedItemsResponse": [{
        "ack": ["Success"],
        "searchResult": [{"@count": "4", "item": [
            {"itemId": ["1"], "title": ["handmade ceramic mug"],
             "sellingStatus": [{"currentPrice": [{"@currencyId": "USD", "__value__": "24.99"}]}]},
            {"itemId": ["2"], "title": ["stoneware mug rustic"],
             "sellingStatus": [{"currentPrice": [{"@currencyId": "USD", "__value__": "19.50"}]}]},
            {"itemId": ["3"], "title": ["pottery coffee mug"],
             "sellingStatus": [{"currentPrice": [{"@currencyId": "USD", "__value__": "32.00"}]}]},
            {"itemId": ["4"], "title": ["artisan mug gift"],
             "sellingStatus": [{"currentPrice": [{"@currencyId": "USD", "__value__": "27.75"}]}]},
        ]}],
        "paginationOutput": [{"totalEntries": ["1250"], "totalPages": ["13"]}],
    }]
}
ACTIVE_JSON = {
    "findItemsByKeywordsResponse": [{
        "ack": ["Success"],
        "searchResult": [{"@count": "0"}],
        "paginationOutput": [{"totalEntries": ["4200"], "totalPages": ["42"]}],
    }]
}


def fake_get(url: str, timeout: int = 30):
    if "findCompletedItems" in url:
        return SOLD_JSON
    return ACTIVE_JSON


finding._get = fake_get
finding.time.sleep = lambda s: None

res = finding.research_keyword("DUMMY-APP-ID", "ceramic mug")
print(res)

assert res["total_sold"] == 1250, res
assert res["active_count"] == 4200, res
assert res["sell_through"] == round(1250 / 4200, 3), res
assert res["sold_avg_price"] == round((24.99 + 19.50 + 32.00 + 27.75) / 4, 2), res
assert res["sold_min_price"] == 19.50, res
assert res["sold_max_price"] == 32.00, res
assert res["sold_sampled"] == 4, res
assert 0 < res["demand_score"] <= 100, res

# missing key -> graceful skip
no_key = finding.research_keyword(None, "ceramic mug")
assert "error" in no_key and "not configured" in no_key["error"], no_key

# failure ack -> error dict, not exception
bad = {"findCompletedItemsResponse": [{"ack": ["Failure"],
       "errorMessage": [{"error": [{"message": ["Invalid AppID"]}]}]}]}
finding._get = lambda url, timeout=30: bad
err = finding.research_keyword("BAD", "x")
assert "error" in err, err

print("ALL FIXTURE TESTS PASSED")
