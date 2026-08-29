# guac — DESIGN

*Advertiser pays. User saves. Middleman stays small.*

**Version 5 — v1 is demand-gated sponsorship.**

The v1 sponsorship is a **`Sponsor:` footer** for the human, delivered after
final agent answers. The gateway never touches the model's context — it forwards
the request unchanged and appends the disclosed footer **below** the answer,
delimited by `---`, so everything above the line is byte-identical to the model
output. This removes the injection risk and the "agent as hard buyer" machinery
from the critical path. The agent-native version is a later layer on top of the
same economics.

**The cadence is deliberately simple and demand-driven.** No auctions, no
topic-matching, no decision-point heuristics. An ad appears when **all three**
hold, deterministically:

1. **Final answer** — `finish_reason == "stop"`. Mid-loop `tool_calls` turns
   (the agent narrating tool work) never qualify — this is what removes the
   "bunch of intermediate messages" noise.
2. **Funded demand** — at least one active offer has budget remaining (static
   offers count as standing funded inventory). If no advertiser is paying, no
   ads appear at all — the system is honest about inventory.
3. **Under the daily cap** — the user hasn't hit `ADS_PER_DAY` (default 3) today.

Offers rotate deterministically so a user sees different sponsors across the
day. The footer carries the sponsor name, headline, body, claim, and optionally
an `image_url` (renders as native media) and `link` (tappable, routed through
the `/go/<id>` clickthrough).

## The model in one line
guac resells inference. Advertisers pay to reach your agent; that money lowers
your per-1M-token price. No credits, no balances, no wallet — **the price is just lower.**

```
Advertiser ──$──> guac ──$──> supply (wholesale inference)
                       └── user pays a discounted rate
```

- guac revenue = advertiser $ + user $ − wholesale cost
- The user's "discount" is a lower price, never a credit.

---

## Supply — where the inference comes from

The gateway is provider-agnostic. It routes each request to the cheapest source
that still clears a **quality gate**. Cheap wholesale = bigger discount + fatter margin.

```
retail price     R  (what a user would pay the big labs directly)
wholesale cost   W  (what guac pays its source)
ad money         A  (what the sponsor pays per delivered offer)
guac fee      F  (our cut)

user price       P = R − A + F
user saves       S = A − F
margin           = A + P − W
```

**Why Bittensor changes the game:** W is tiny on SN64 (Chutes), SN53 (engy), and
SN28 (gm — which resells Anthropic/OpenAI/Google through confidential VMs, literally
the same "markup spread" business). That makes the retail−wholesale spread huge, so
ad revenue sits on top of a wide gap:

- hold margin → pass a bigger discount than any retail reseller can match, or
- hold the discount → keep more of the spread.

Note: **SN74 (Gittensor) is not a supplier.** It's our compression/software subnet,
not an inference source. Keep it out of the routing pool.

### The quality gate (non-negotiable)

Bittensor inference is cheap *because* it's variable. If the cheap route is slow or
garbage, the discount is worthless, the user leaves, and the sponsor's ad was wasted.
So sourcing can never be "cheapest miner wins":

- **Deterministic quality scoring** of each source — spot evals, latency/uptime
  windows, provenance hashing. No LLM judge. (KEG/llama.cpp muscle.)
- **Failover** across sources: 64 → 53 → 28 → retail. One miner's bad day is never
  the user's bad day.
- Sources are **whitelisted + continuously scored**, not discovered live. Advertisers
  and users never see the supply; it's an internal routing decision gated on quality.

---

## User side (no choice — ads are placed for you)

The user makes **no frequency choice**. V1 appends a sponsor after final answers,
up to a hard daily cap, only when an advertiser has funded budget. There's no
"how many ads a day" knob; you never get ads on mid-loop narration, and you get
zero ads on days no advertiser is paying. The only user-facing trust is the
disclosure: the ad sits below a `---` line, clearly separated from the model's
answer, and it funds your discount.

The ad is a **`Sponsor:` footer** attached to the response — the human sees it,
the model never does. It rides on real attention (you just read the answer), so
it's trusted rather than noise.

## Advertiser side (one form)

> *Headline · body · claim · budget · image_url · link*

They buy **delivered impressions, capped per user per day**. Budget is the
demand that gates the whole system: with funds, your offer runs; without, no ads
appear. Deterministic rotation means different users see different sponsors, so
a given offer reaches a spread of users up to its budget. Later (agent-native):
they buy **offers delivered to agents that are actually deciding/buying**, with
the agent as a hard buyer.

Note the value proposition: each user sees at most a few sponsored footers a
day, so impressions are **capped by design**. The sell is quality placement and
accountability (metered impressions, real clicks, public split), not volume.

---

## Money flow (per request + monthly)

Per request, the gateway already meters tokens. The discount is a lower price, not a
credit — nothing enters the user's wallet.

Monthly settlement (Model B — wholesale savings flow to the user):
```
retail_cost     = tokens × retail $/M          (what the user would pay elsewhere)
wholesale_cost  = tokens × wholesale $/M       (what guac pays the source)
ad_revenue      = offers × $/offer             (what sponsors paid)
guac_fee        = offers × fee                 (guac's whole margin — thin, honest)
ad_pass_through = ad_revenue − guac_fee        (sponsor money, minus our fee)

user_paid   = max(0, wholesale_cost − ad_pass_through)
user_saving = retail_cost − user_paid          (cheap-supply savings + ad money)
guac_margin = guac_fee                          (guac keeps only its fee)
```

The split is always public: **sponsor → user, minus guac's fee.** Both the cheap-
supply savings and the ad money go to the user. If ad money exceeds the user's
full bill, the surplus is carried forward as credit — never pocketed by guac.

---

## Stats — impressions and clicks

Both come from the ledger, but they're not the same, and "click" needs a definition.

- **Impressions** — the gateway meters every request and every injected footer.
  A dashboard is just the ledger rendered. With decision-point placement, an
  impression is high-value by construction: it only happens at a genuine,
  relevant decision moment, so it's far more meaningful than a page view.
- **Clicks** — an agent doesn't click. A click = **the agent acted on an offer**
  (accepted, redeemed, referenced it). You can't see that from the proxy alone;
  the agent must report back. So guac ships a tiny **attribution callback**:
  the agent signals "I used the Acme offer" and guac records it.

That callback is the honest, non-fakeable version of a click — and it's the metric
advertisers actually value (proof the offer mattered, not that it was shown).

---

## The one honest tension

The pass-through margin is the whole business and it's thin by design — the user gets
most of the sponsor money. That's the *point* (trust = the product). So guac is a
**volume business**: many users × many sponsors. The moat is distribution (how many
agents route through us), not fee %.

Bittensor sourcing flips this: it doesn't make the *fee* bigger, it makes the *wholesale*
tiny, so the same thin fee is worth more per user — and you can also out-discount retail.
Supply is the lever that turns a thin-margin niche into a real business.

---

## Build order

1. **Gateway** (done, verified) — inject + meter + price.
2. **Settlement** — monthly bill, transparent split.
3. **Quality gate + failover** — the Bittensor supplier pool (done, + recovery).
4. **Attribution callback** — the "click" metric.
5. **Dashboard** — impressions + clicks for both sides.
6. **Portal** — magic-link auth for users + advertisers, ad manager, per-impression billing (done, live).

**Next: agent-native tier** — offers delivered to agents that actually decide/buy
(hard-buyer guardrails, act-based billing, typed offer tool). See
[`docs/AGENT_TIER.md`](docs/AGENT_TIER.md) for the design spec.
