# guac — advertiser pitch (demand-gated sponsorship)

**The one-line value:** guac places your offer after an agent's answers — up to
a few times a day per user, only while you have budget. You pay per delivered
offer; the money lowers that person's inference cost.

## What an advertiser gets

- **Simple, predictable placement.** Your offer appears as a disclosed
  `Sponsor:` footer below final agent answers, up to the daily cap. No auctions,
  no keyword bidding — you set a budget and your offer runs while it has funds.
- **Demand-gated by you.** Your budget is the demand. If you have budget, your
  offer is eligible; if you don't, no ad runs at all. The system only ever shows
  ads that are actually funded.
- **A few per day, never spam.** Each user sees at most a handful of sponsored
  footers a day (a hard cap), so your message is attention you earn, not noise.
- **Delivered impressions you can verify.** Every impression is metered from the
  ledger — the exact offer, the moment. No fabricated reach numbers.
- **Attribution that proves value.** A "click" here means the offer was actually
  *acted on* (referenced, redeemed), reported via guac's attribution callback /
  clickthrough. You see views → clicks → redemptions, not vanity metrics.

## What the user sees

```
"Here are three options for managed hosting, each with tradeoffs."

---
Sponsor: Acme Cloud Hosting — 50% off your first 3 months of managed hosting
Deploy your app to a vetted node with daily backups and 99.9% uptime.
Claim: 50% off first 3 months, code AGENT50
[Learn more]
```

- The model's answer is **untouched** — everything above the `---` line is
  byte-identical to what the model would have said without the sponsor.
- The sponsor is **disclosed** and clearly separated, so it never reads as the
  AI secretly selling something.
- The user's inference price is **lower** because of your money — that's the
  exchange, and it's transparent.

## Why this is a better slot than an ad

- It's a **sponsorship, not an interruption.** The offer follows a real agent
  answer the user just read, is disclosed, and is capped — attention you earn,
  not a banner that hijacks the page.
- The trust is the product. A disclosed, capped, clearly-separated sponsor
  doesn't erode the thing the whole system runs on.

## What we ask of you (one form)

`headline` · `body` · `claim` · `budget` · `image_url` (optional creative) · `link`

You set a budget; each delivered offer costs one impression; your offer
auto-pauses when the budget is spent. You're always on the hook only for what
actually delivered.

## The honest framing

Each user sees at most a few sponsored footers a day, so your impressions are
**capped by design** — you buy quality placement, not volume. Every impression
is metered from the ledger, every click is real (a clickthrough or attribution
callback), and the split is public. Your budget literally gates the whole system:
when you have funds, your offer runs; when you don't, no ads appear. That's a
story that survives a skeptic reading the numbers.

---

*That's the pitch. One sentence to lead with, if you're somewhere you can only
say one thing:*
> **guac places your disclosed offer after real agent answers — up to a few a
> day, only while your budget lasts — paid per delivered offer, metered
> honestly, and accountable end-to-end.**
