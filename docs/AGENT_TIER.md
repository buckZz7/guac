# guac — AGENT-NATIVE TIER (v2) DESIGN

*Human-facing sponsorship is v1 (done, live). This is the design for the next
layer: offers delivered to agents that are actually deciding and buying — the
"ad inventory = decision slot" thesis. Research-grounded, honest by design.*

> Status: **design spec, not built.** Tradeoffs are flagged. Read this before
> writing code.

## The thesis, restated

v1 proves the economics with humans: an advertiser pays per impression, the
user sees a disclosed "brought to you by," the model is never touched. The
**agent-native tier** changes *who* the offer reaches. Instead of a human
seeing a sponsorship on a response, the **agent itself** receives offers in
context and can act on them — book the flight, pick the vendor, redeem the
trial. The ad inventory isn't a banner slot; it's a **decision the agent
makes on the user's behalf.**

That is the far larger business (from the original outbid analysis): thousands
of decisions per user, not one eyeball. But it carries a much higher trust
burden — the agent is spending on the user's behalf, and a "hard buyer" that's
an easy sale destroys the user's trust and, with it, the whole product.

## Industry context (research, mid-2026)

The space is real but early:

- **Protocols are forming**: Google's agentic-commerce open standard; AdCP
  (Scope3/PubMatic/Yahoo) and IAB's AAMP/ARTF/UCP as contested "buyer agent ↔
  seller agent" protocol layers. An agent advertises to another agent over a
  protocol, with the human setting strategy.
- **MCP is the substrate**: advertisers' own agents reach platforms via MCP or
  API (Yahoo's "Yours/Mine/Ours"; Amazon's DSP MCP beta).
- **Buy-side is cautious**: "buyers find agentic AI more interesting than
  urgent." The hype outruns the buying. A working, *honest* implementation is
  an early-mover advantage — but it must not feel like a gimmick.

**What this means for guac:** do not build our own agent-to-agent protocol.
That's a standards war (AdCP vs AAMP) we don't need to fight. guac's edge is
**distribution + honesty**: we already sit between agents and models, we
already have the quality-gated supply, and we already have the transparent
settlement. We layer offers onto a path agents already use.

## The core tension: trust (this is the whole game)

An agent that accepts offers has to be a **hard buyer**, not an easy sale.
Buck's profile is explicit: "the agent has to be good at navigating ads, not
being an easy sale." So the design must make the agent *resistant* to ads by
default and only act when the offer genuinely serves the user.

Failure modes to design against:

1. **Sycophantic buying** — the agent accepts the offer because it was
   presented (an "easy sale"), not because it's good for the user.
2. **Prompt-injected urgency** — an advertiser sneaks "ACCEPT IMMEDIATELY /
   this is the only option" into offer text to coerce a decision.
3. **Hidden costs** — the offer looks great but the claim is misleading; the
   agent can't verify it.
4. **Spend without value** — the agent redeems/buys on the user's behalf
   without clear authorization or benefit.

These are precisely the failure modes that make agent-advertising a trust
minefield, and why the buy side is cautious. guac's answer must be a set of
**hard guardrails**, not vibes.

## The guardrails (non-negotiable)

1. **The user authorizes the decision class, not the offer.** The user
   pre-approves categories ("may buy flight tickets up to $400"; "may redeem
   free trials"). The agent may act on offers **only within** an authorized
   class. No authorization, no purchase. This is the *agent as hard buyer*
   made real: it can say no to everything outside the user's stated bounds.

2. **The offer is data, not instruction.** Offer text is carried in a typed
   structure (`offer_id`, `claim`, `terms`, `budget`, `expiry`) — and is
   **never appended to the model's instruction stream as free text**. The agent
   reads it as a data object and evaluates it against the user's policy. This
   structurally prevents prompt-injection-as-advertising: no advertiser text
   becomes a model directive.

3. **Attribution is the sale, not the impression.** An advertiser pays only
   when the agent *actually acts* (accepts/redeems/buys), confirmed by the
   attribution callback — never for mere presentation. This keeps the honest
   "you pay for outcomes, not eyeballs" model from v1 and aligns with Buck's
   "monetize outcomes/trust, not tokens."

4. **The model never sees the offer unless the user opted into that class.**
   If a user hasn't authorized "travel," no travel offer is even loaded into
   context. This bounds both token cost and exposure.

5. **No anti-gaming framing.** We don't build "anti-gaming" defenses as a
   feature; we build *honest evaluation* as the default. An agent that must
   justify, to the user, every purchase it makes is the mechanism.

## Architecture

```
user policy  ──▶  guac ──▶ [agent context] ──▶ model (decides)
                    │  ▲
                    │  │ typed offer object (data, not instruction)
                    ▼  │
              offer index (active, budgeted, honest)
                 advertiser pays ONLY on attribution (act)
```

- **Policy store**: per-user authorized decision classes + limits. V1 of this
  is the existing `users.json`/settings; v2 adds structured policy.
- **Offer index**: active offers with budget/claim/terms, filtered by the
  user's authorized classes. Reuses the existing `offers.json` + per-impression
  billing, but billing triggers on **act** (attribution), not impression.
- **Typed offer injection**: the offer rides the response as a structured
  object (v1's `guac` block already does this shape) and, when the user has an
  agent-native tier, into a **typed tool/function call** the agent can invoke —
  never as free-text instructions.
- **Attribution-as-billing**: the existing `/v1/guac/attribution` endpoint is
  the sale trigger. Advertiser spend = acts, reconciled in settlement.

## Billing model (agent-native)

Rework of v1's per-impression model for the agent tier:

```
advertiser_pays = acts × cost_per_act        (only confirmed actions)
user_saves     = ad_pass_through             (same transparent split as v1)
guac_fee       = acts × fee_per_act          (thin, honest)
```

An "act" is a confirmed, attributed outcome (redeemed offer / completed
purchase), verified by the callback + (later) a proof receipt. This is the
"provably-beatable," non-fakeable metric Buck insists on: an advertiser can't
be charged for impressions that didn't convert, and can't be gamed by
inflation.

## Open questions (to resolve before building)

1. **Authorization UX**: how does a user express "may buy flights up to $400"
   simply? A policy UI? Natural-language policy the agent interprets?
2. **Verification of an "act"**: how do we prove the agent actually bought, not
   just called a function? (Receipts, vendor confirmation.) This is the
   anti-fakeable-logs problem.
3. **Opt-in default**: should the agent tier be default-off (user must enable)
   or default-on? Given trust stakes, likely default-off with a clear
   opt-in.
4. **Protocol**: build on MCP (offer-as-tool) vs OpenAI function-calling vs
   guac's own typed block. MCP is the industry direction; worth leaning there.
5. **Do we even need a model change?** The critical-path question: can the
   hard-buyer guardrails be enforced purely in the gateway (typed offer,
   policy filter, no free-text injection), or does it require agent-framework
   cooperation (a custom tool the agent must use)?

## Build order (when greenlit)

1. **Policy store** — per-user authorized decision classes + limits (extend
   users/settings).
2. **Typed offer tool** — offer as a function-call/MCP tool, not free text.
3. **Act-based billing** — switch the offer tier's billing trigger from
   impression to attributed action.
4. **Attribution proof** — receipts/vendor confirmation for the "act."
5. **Policy UI** — let users authorize decision classes simply.

## Why this is worth building (and why not yet)

Worth it: it's the actual product thesis — decision slots, not banners — and
the economics are far larger. It's also where the industry is heading
(agent-to-agent commerce, MCP).

Not yet: it needs users and real agents to validate, and it raises the hardest
trust questions (fakeable actions, easy-sale agents) that can't be answered by
engineering alone. This is why v1 (human-facing) shipped first — it proves the
economics and trust model in a low-stakes form. **The agent tier should build
on that proof, not replace it.**
