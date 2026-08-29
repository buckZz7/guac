# guac — Terms of Service

_Last updated: [Date]. This is a plain-English summary for transparency, not a
substitute for the full legal agreement. It is not legal advice._

guac ("we", "us") provides an OpenAI-compatible inference gateway that connects
an agent (the "Agent") to inference providers, and an advertising platform where
advertisers fund impressions that lower the user's per-token cost. By using guac
you agree to these Terms.

## 1. The two roles

- **User** — you point your Agent at guac's `base_url` with an API key. You get
  inference at a discounted rate funded in part by advertisers.
- **Advertiser** — you prepay a balance and fund offers that appear as disclosed
  `Sponsor:` footers after Agent answers.

## 2. Sponsorship disclosure

Sponsored content is **always disclosed**. A sponsor appears only as a clearly
separated `Sponsor:` footer below the model's answer, marked by a `---` divider.
The model's answer itself is never altered to contain advertising. This is a
core design principle, not a suggestion — it exists to keep the product honest
and to comply with advertising-disclosure rules (e.g. the FTC's requirement that
material connections be "clear and conspicuous").

## 3. User obligations

- You will not use guac to violate any law, to generate or distribute unlawful,
  harmful, or misleading content, or to abuse the service.
- You will protect your API key. You are responsible for all activity under it.
- You will not attempt to circumvent rate limits, spend caps, or quotas.

## 4. Advertiser obligations

- You represent that your offers (headline, body, link, images) are truthful,
  not deceptive, and comply with all applicable advertising law, including
  disclosing any material connection as required.
- Your `link` and `image_url` must be valid `https://` URLs. They are validated;
  `javascript:` and other non-web schemes are rejected.
- You fund offers by prepaying a balance. Offers run only while your balance and
  the offer's budget allow; impressions are metered and deducted from your
  balance.
- **Prohibited content:** we may reject or remove, without notice, offers that
  are unlawful, misleading, hateful, sexually explicit, or that promote fraud,
  prohibited products (e.g. controlled substances, weapons), or harm. This list
  is illustrative, not exhaustive.

## 5. Balances and refunds

- Advertiser balances are prepaid. Top-ups are handled by our payment provider
  (e.g. Stripe when enabled).
- Unused balance is refundable on request, minus any impressions already
  delivered and any processing fees, at our discretion and subject to the
  payment provider's terms.
- We may cap or suspend an account for abuse.

## 6. Pricing and the discount

- The discount is a **lower price**, not a credit or balance in your wallet.
- The settlement is transparent: user saving = sponsor money − guac's fee, and
  the split is always reconcilable from our ledgers.

## 7. Acceptable use / abuse

We employ rate limits, per-key spend caps, and content validation. We may
suspend access that, in our judgment, abuses the service (e.g. scraping,
signup spam, a leaked key burning tokens, fraud).

## 8. No warranty; limitation of liability

The service is provided "as is" without warranties of any kind. Inference
quality and availability depend on third-party providers. To the maximum extent
permitted by law, our aggregate liability is limited to the amounts you actually
paid us in the preceding 30 days. We are not liable for indirect, incidental,
special, or consequential damages.

## 9. Privacy

Our handling of your data is described in the [Privacy Policy](/privacy).

## 10. Termination

You may stop using guac at any time. We may suspend or terminate accounts for
violations of these Terms. On termination, balances are handled per section 5.

## 11. Changes to these Terms

We may update these Terms. Material changes will be reflected by an updated
"Last updated" date; continued use after a change constitutes acceptance.

## 12. Contact

Questions: [your contact email / address].

---

_These Terms are provided as a starting point. Have them reviewed by a lawyer
qualified in your jurisdiction before going live, and confirm they cover your
specific payment provider, jurisdiction, and offerings._
