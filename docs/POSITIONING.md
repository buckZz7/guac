# guac — Market & Positioning Brief

_A research-grounded look at the ad-in-AI landscape, where guac fits, and how to
position it. Research date: Aug 2026._

## 1. The market is real and being validated by big money

The "ads in AI" opportunity is no longer hypothetical — it's funded and growing:

- **ChatGPT ads** launched Feb 2026 and crossed **$100M annualized ad revenue in
  ~2 months** (TNW, Aug 2026).
- **Google AI Mode** is placing ads at the bottom of AI answers (MediaPost).
- **Gravity** ("The Ad Network for AI") raised a **$30.5M Series A** (Lightspeed,
  Committed Capital; ~$38.5M total). It places text ads inside ChatGPT, Codebuff,
  Magneta, Runnable, and is **testing agent-to-agent ads** that humans never see,
  plus direct agent checkout (TNW / Business Insider).

**Takeaway:** ad-funded AI is a validated, venture-backed category. guac's
demand-gated, disclosed-sponsor model is squarely in this lane — and its
"human-facing footer, never in the model" approach is the **safer, trust-first**
version vs. Gravity's more aggressive in-conversation and agent-to-agent play.

## 2. Competitive map

| Player | What they do | How it differs from guac |
|---|---|---|
| **Gravity** | Full-stack ad network for AI chatbots; DSP + SSP + exchange; agent-to-agent ads | Ads **inside** the conversation; targets big platforms; VC-backed |
| **ChatGPT / OpenAI** | Ads in ChatGPT (free & low tiers) | Closed platform; guac is model-agnostic / bring-your-own-agent |
| **Google AI Mode** | Ads in AI search answers | Search-focused; closed |
| **Chutes (SN64)** | Bittensor cheap serverless inference (~85% under AWS) | **Supplier, not competitor** — guac can route through it |
| **Engy (SN53)** | Bittensor inference | Supplier |
| **Inference.net, cheap-gateway resellers** | Arbitrage/cheap inference | Compete on **inference price**, not the ad model |

**Key strategic insight:** guac is not primarily competing with other inference
resellers on *price per token*. It's a **distribution/monetization play**: the
ad-funded discount is the wedge to get users to route their agent through guac.
The moat is **distribution** (how many agents route through guac) and **trust**
(the disclosed, honest sponsorship), not a marginally lower token price.

## 3. guac's defensible position

- **Model-agnostic & harness-agnostic.** Works with Hermes, OpenClaw, Codex, any
  OpenAI-compatible client. Gravity/ChatGPT are platform-locked. This is guac's
  structural advantage: it monetizes *any* agent, not one vendor's.
- **Disclosed, human-facing, trust-first.** The sponsor is a clearly-separated
  `---` footer, never injected into the model. This aligns with FTC "clear and
  conspicuous" disclosure and avoids the trust damage of hidden/in-model ads.
- **Honest inventory.** Demand-gated: ads only run when funded. No fabricated
  reach. Advertisers buy metered, accountable impressions.
- **Cheap supply + ad money.** Routing through Bittensor subnets (Chutes/Engy)
  keeps wholesale low, widening the discount guac can pass through.

## 4. Where guac should NOT compete

- **Not a price war on raw inference.** Inference.net, big labs, and Bittensor
  miners will always undercut on raw $/token. guac wins on the *bundle*: cheap
  supply + ad discount + honest monetization, in one drop-in endpoint.
- **Not an enterprise DSP.** Don't chase Gravity's full ad-exchange/fraud-ridden
  adtech stack. guac's V1 is a focused, honest marketplace: one sponsor, one
  discount, transparent settlement.

## 5. Recommended positioning

**One-liner:** "guac is the OpenAI-compatible gateway where a disclosed sponsor
pays for part of your inference — point any agent at it and pay less."

**For users:** "Pay less for AI. A disclosed sponsor follows a few of your
answers — never in the model, never spam. Point your agent at one URL."

**For advertisers:** "Put your offer in front of people actually using agents —
at a genuine moment of attention, disclosed, metered, and accountable. You set a
budget; your offer runs only while it's funded."

## 6. Gaps still to close before marketing (from the readiness audit)

1. **Real money via Stripe** (built, needs your Stripe keys + backend flip).
2. **Email delivery** (built, needs your SMTP creds) — the portal is currently
   closed to public signup until then.
3. **Terms + Privacy** (drafted in `docs/TERMS.md`, `docs/PRIVACY.md`; lawyer
   review recommended before going live).
4. **Real affiliate/paid advertisers** (step 2; not needed to test, needed to
   market a live marketplace).
5. Consider a **waitlist** or closed beta while you wire credentials, rather than
   opening signups before the money/email paths work.

## 7. Suggested next strategic steps

- Land **1-2 real advertisers** (even via manual/affiliate deals) to validate
  demand and get reference proof metrics.
- Get **1-3 active users** routing real agents, to dogfood the discount story.
- Flip to **Stripe** once you have an advertiser willing to pay.
- Open a **private beta** before a public launch; use the waitlist to build
  anticipation and avoid being judged on an empty marketplace.
