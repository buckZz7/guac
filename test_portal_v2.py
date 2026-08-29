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
assert ("moment of need" in r.text) or ("demand-gated sponsorship" in r.text)
print("PASS  /pitch renders the advertiser pitch (or fallback)")

# 1b) /terms and /privacy render
for path, frag in (("/terms", "Terms of Service"), ("/privacy", "Privacy Policy")):
    r = c.get(path)
    assert r.status_code == 200 and frag in r.text, (path, r.status_code)
print("PASS  /terms and /privacy render")

# 2) landing page has the pitch link + new copy + legal footer
r = c.get("/portal")
assert r.status_code == 200 and "Read the advertiser pitch" in r.text
assert "using agent answers" in r.text
assert "/terms" in r.text and "/privacy" in r.text
print("PASS  /portal landing has pitch link + legal footer + demand-gated copy")

# 3) advertiser offer form (dashboard) has image_url/link fields (no intents)
import portal, portal_html
adv = portal.get_advertiser("adv@x.com") or portal.create_advertiser("adv@x.com")
html = portal_html.advertiser_dashboard(adv, portal.offer_stats_for("adv@x.com"))
for token in ("name=\"image_url\"", "name=\"link\"",
              "guac sponsorship works"):
    assert token in html, f"missing {token} in advertiser form"
assert "name=\"intents\"" not in html, "intents field should be removed"
print("PASS  advertiser offer form has image_url/link + pitch link (no intents)")

# 4) create an offer through the portal with the new fields, verify stored
r = c.post("/portal/advertiser/offer", data={
    "email": "adv@x.com", "headline": "50% off hosting", "body": "b",
    "claim": "CODE", "budget": "5", "offer_type": "discount",
    "image_url": "https://x/y.png",
    "link": "https://x/agent"})
assert r.status_code == 200, r.status_code
offers = gateway.portal._offers()
assert offers, "offer not created"
o = offers[-1]
assert o["image_url"] == "https://x/y.png" and o["link"] == "https://x/agent"
print("PASS  offer stored with image_url + link")

# 5) invalid link rejected
r = c.post("/portal/advertiser/offer", data={
    "email": "adv@x.com", "headline": "bad link", "body": "b",
    "claim": "C", "budget": "5", "link": "javascript:alert(1)"})
assert r.status_code == 200, r.status_code  # renders dashboard with error
offers = gateway.portal._offers()
assert offers[-1]["headline"] != "bad link", "javascript: link must be rejected"
print("PASS  invalid (javascript:) link rejected")

print("\nPORTAL/PITCH SMOKE TESTS PASSED")
