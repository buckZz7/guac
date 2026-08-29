import os, sys, tempfile
ROOT = "/opt/data/guac"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# hermetic: temp suppliers/offers so we hit the static ads.json fallback path
td = tempfile.mkdtemp()
os.environ["ADGATE_SUPPLIERS_FILE"] = os.path.join(td, "suppliers.json")
os.environ["ADGATE_OFFERS_FILE"] = os.path.join(td, "offers.json")
os.environ["ADGATE_ALLOW_DEMO_ADS"] = "1"  # this test exercises the demo fallback

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

# 1c) marketing landing at / renders (user-only page; advertisers have /advertisers)
r = c.get("/")
assert r.status_code == 200, r.status_code
assert "Cheaper tokens" in r.text
assert "Get my API key" in r.text
assert "/terms" in r.text and "/privacy" in r.text
print("PASS  marketing home at / renders (hero + CTAs + footer)")

# 1c-2) advertiser page renders separately
r = c.get("/advertisers")
assert r.status_code == 200 and "For advertisers" in r.text, r.status_code
print("PASS  /advertisers renders the advertiser marketing page")

# 1d) custom 404 renders (not a 500)
r = c.get("/does-not-exist-xyz")
assert r.status_code == 404, r.status_code
assert "Page not found" in r.text and "Back to guac home" in r.text
print("PASS  custom 404 renders with status 404")

# 2) portal home has two clear paths + legal footer
r = c.get("/portal")
assert r.status_code == 200, r.status_code
assert "I'm using an AI agent" in r.text
assert "I'm an advertiser" in r.text
assert "/terms" in r.text and "/privacy" in r.text
print("PASS  /portal has user + advertiser paths + legal footer")

# 3) advertiser offer form (dashboard) has image_url/link fields (no intents)
import portal, portal_html
adv = portal.get_advertiser("adv@x.com") or portal.create_advertiser("adv@x.com")
html = portal_html.advertiser_dashboard(adv, portal.offer_stats_for("adv@x.com"))
for token in ("name=\"image_url\"", "name=\"link\"",
              "Create an offer"):
    assert token in html, f"missing {token} in advertiser form"
assert "name=\"intents\"" not in html, "intents field should be removed"
print("PASS  advertiser offer form has image_url/link + pitch link (no intents)")

# 4) create an offer through the portal with the new fields, verify stored
# (form auth is the advertiser TOKEN — a bare email must NOT create offers)
r = c.post("/portal/advertiser/offer", data={
    "email": "adv@x.com", "headline": "spoofed", "body": "b",
    "claim": "CODE", "budget": "5", "offer_type": "discount"})
assert r.status_code == 200
assert not gateway.portal._offers(), "email-only form must NOT create an offer"
print("PASS  email-only offer form rejected (token required)")

adv_token = adv["token"]
r = c.post("/portal/advertiser/offer", data={
    "token": adv_token, "headline": "50% off hosting", "body": "b",
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
    "token": adv_token, "headline": "bad link", "body": "b",
    "claim": "C", "budget": "5", "link": "javascript:alert(1)"})
assert r.status_code == 200, r.status_code  # renders dashboard with error
offers = gateway.portal._offers()
assert offers[-1]["headline"] != "bad link", "javascript: link must be rejected"
print("PASS  invalid (javascript:) link rejected")

print("\nPORTAL/PITCH SMOKE TESTS PASSED")
