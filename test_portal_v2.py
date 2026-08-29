import os, sys, tempfile
ROOT = "/opt/data/guac"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# hermetic: temp suppliers/offers so we hit the static ads.json fallback path
td = tempfile.mkdtemp()
os.environ["ADGATE_SUPPLIERS_FILE"] = os.path.join(td, "suppliers.json")
os.environ["ADGATE_OFFERS_FILE"] = os.path.join(td, "offers.json")

from fastapi.testclient import TestClient
import gateway

c = TestClient(gateway.app)

# 1) /pitch renders the advertiser doc (or graceful fallback if file absent)
r = c.get("/pitch")
assert r.status_code == 200, r.status_code
assert ("moment of need" in r.text) or ("decision-point sponsorship" in r.text)
print("PASS  /pitch renders the advertiser pitch (or fallback)")

# 2) landing page has the pitch link + new copy
r = c.get("/portal")
assert r.status_code == 200 and "Read the advertiser pitch" in r.text
assert "moment they're" in r.text
print("PASS  /portal landing has pitch link + decision-point copy")

# 3) advertiser offer form (dashboard) has intents/image_url/link fields
import portal, portal_html
adv = portal.get_advertiser("adv@x.com") or portal.create_advertiser("adv@x.com")
html = portal_html.advertiser_dashboard(adv, portal.offer_stats_for("adv@x.com"))
for token in ("name=\"intents\"", "name=\"image_url\"", "name=\"link\"",
              "How decision-point sponsorship works"):
    assert token in html, f"missing {token} in advertiser form"
print("PASS  advertiser offer form has intents/image_url/link + pitch link")

# 4) create an offer through the portal with the new fields, verify stored
r = c.post("/portal/advertiser/offer", data={
    "email": "adv@x.com", "headline": "50% off hosting", "body": "b",
    "claim": "CODE", "budget": "5", "offer_type": "discount",
    "intents": "hosting, deploy", "image_url": "https://x/y.png",
    "link": "https://x/agent"})
assert r.status_code == 200, r.status_code
offers = gateway.portal._offers()
assert offers, "offer not created"
o = offers[-1]
assert o["intents"] == ["hosting", "deploy"], o["intents"]
assert o["image_url"] == "https://x/y.png" and o["link"] == "https://x/agent"
print("PASS  offer stored with intents + image_url + link")

print("\nPORTAL/PITCH SMOKE TESTS PASSED")
