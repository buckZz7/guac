"""guac portal + marketing HTML UI (server-rendered, no JS framework).

Dark design system: near-black canvas (#0f0f0f), emerald accent (#3ecf8e),
Inter typeface, border-defined depth (no shadows), pill CTAs. Modeled on
developer-platform aesthetics (Supabase/Linear). One shared shell across the
marketing landing (/), the advertiser page (/advertisers), the portal, and
the OAuth flow. Mobile-responsive.
"""
import html as _html

import config
import oauth
import portal

# Dark theme tokens
_BG = "#0f0f0f"          # page canvas
_SURFACE = "#171717"     # raised surfaces (cards, inputs, code)
_SURFACE2 = "#1c1c1c"    # slightly raised (table head, hovers)
_B1 = "#242424"          # subtle borders (section dividers)
_B2 = "#2e2e2e"          # standard borders (cards, inputs)
_B3 = "#363636"          # prominent borders (hover, buttons)
_INK = "#fafafa"         # primary text
_INK2 = "#b4b4b4"        # secondary text
_MUTED = "#898989"       # muted text
_GREEN = "#3ecf8e"       # brand
_GREEN_LINK = "#00c573"  # interactive green
_GREEN_BORDER = "rgba(62,207,142,.3)"

# The headline user-facing number: the discount on every request.
_DISCOUNT_PCT = int(config.DISCOUNT_RATE * 100)

_MONO = '"Source Code Pro",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace'


def _icon(name):
    """Inline SVG card icons — stroked, rendered in the brand green."""
    icons = {
        "tag": "<svg width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%s' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z'/><line x1='7' y1='7' x2='7.01' y2='7'/></svg>",
        "gift": "<svg width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%s' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><polyline points='20 12 20 22 4 22 4 12'/><rect x='2' y='7' width='20' height='5'/><line x1='12' y1='22' x2='12' y2='7'/><path d='M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z'/><path d='M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z'/></svg>",
        "eye": "<svg width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%s' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z'/><circle cx='12' cy='12' r='3'/></svg>",
        "target": "<svg width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%s' stroke-width='1.8'><circle cx='12' cy='12' r='10'/><circle cx='12' cy='12' r='6'/><circle cx='12' cy='12' r='2'/></svg>",
        "chart": "<svg width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%s' stroke-width='1.8' stroke-linecap='round'><line x1='18' y1='20' x2='18' y2='10'/><line x1='12' y1='20' x2='12' y2='4'/><line x1='6' y1='20' x2='6' y2='14'/></svg>",
        "check": "<svg width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%s' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M22 11.08V12a10 10 0 1 1-5.93-9.14'/><polyline points='22 4 12 14.01 9 11.01'/></svg>",
        "bolt": "<svg width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%s' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><polygon points='13 2 3 14 12 14 11 22 21 10 12 10 13 2'/></svg>",
    }
    return icons.get(name, "") % _GREEN

_CSS = f"""
*{{box-sizing:border-box;margin:0}}
html{{scroll-behavior:smooth}}
body{{font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  background:{_BG};color:{_INK};line-height:1.6;-webkit-font-smoothing:antialiased;
  font-weight:400}}
a{{color:{_GREEN_LINK};text-decoration:none}} a:hover{{text-decoration:underline}}
.container{{max-width:1080px;margin:0 auto;padding:0 24px}}
/* nav */
.nav{{background:rgba(15,15,15,.82);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
  border-bottom:1px solid {_B1};position:sticky;top:0;z-index:50}}
.nav .inner{{position:relative;display:flex;align-items:center;gap:28px;padding:16px 24px;max-width:1080px;margin:0 auto}}
.logo{{font-size:1.25rem;font-weight:700;letter-spacing:-.03em;color:{_INK}}}
.logo span{{color:{_GREEN}}}
.nav .links{{margin-left:auto;display:flex;gap:24px;align-items:center;font-size:.875rem;
  flex-wrap:nowrap}}
.nav .links a{{color:{_INK2};font-weight:500}}
.nav .links a:hover{{color:{_INK};text-decoration:none}}
/* buttons inside the nav keep their own colors — the link rule must not
   override them (this was the grey-text-on-green bug) */
.nav .links a.btn{{color:inherit}}
.nav .links a.btn-primary{{color:#0f0f0f}}
.nav .links a.btn-ghost{{color:{_INK}}}
.menu-toggle{{display:none;margin-left:auto;background:none;border:1px solid {_B2};
  border-radius:10px;padding:9px 11px;cursor:pointer;color:{_INK}}}
.menu-toggle svg{{display:block}}
/* mobile nav */
@media(max-width:640px){{
  .nav .inner{{padding:13px 20px}}
  .menu-toggle{{display:block}}
  .nav .links{{display:none;position:absolute;top:100%;left:0;right:0;
    flex-direction:column;align-items:stretch;gap:4px;padding:16px 20px 20px;
    background:rgba(15,15,15,.97);backdrop-filter:blur(12px);border-bottom:1px solid {_B1}}}
  .nav.open .links{{display:flex}}
  .nav .links a{{padding:11px 4px;font-size:1rem}}
  .nav .links a.btn{{text-align:center;margin-top:8px}}
  .hero{{padding:64px 0 48px}}
  section{{padding:64px 0}}
}}
/* buttons */
.btn{{display:inline-block;padding:10px 26px;border-radius:999px;font-weight:500;font-size:.875rem;
  border:1px solid transparent;cursor:pointer;transition:border-color .15s,background .15s,color .15s}}
.btn-primary{{background:{_GREEN};color:#0f0f0f;border-color:{_GREEN}}}
.btn-primary:hover{{background:#4fdb9d;text-decoration:none;color:#0f0f0f}}
.btn-ghost{{background:transparent;color:{_INK};border-color:{_B3}}}
.btn-ghost:hover{{border-color:{_MUTED};text-decoration:none;color:{_INK}}}
.btn-block{{display:block;width:100%;text-align:center}}
/* hero */
.hero{{padding:110px 0 72px;text-align:center}}
.eyebrow{{display:inline-block;font-family:{_MONO};font-size:.72rem;letter-spacing:.14em;
  text-transform:uppercase;color:{_GREEN};border:1px solid {_GREEN_BORDER};
  padding:7px 16px;border-radius:999px;margin-bottom:28px}}
h1{{font-size:clamp(2.6rem,6vw,4.4rem);font-weight:500;letter-spacing:-.04em;line-height:1.05;
  max-width:860px;margin:0 auto}}
h1 .accent{{color:{_GREEN}}}
.lede{{font-size:1.15rem;color:{_INK2};max-width:640px;margin:24px auto 36px;line-height:1.65}}
.cta{{display:flex;gap:14px;justify-content:center;flex-wrap:wrap}}
.trust{{margin-top:30px;font-size:.85rem;color:{_MUTED}}}
.trust b{{color:{_INK2}}}
/* live meter strip */
.meter{{background:{_SURFACE};border-block:1px solid {_B1};padding:20px 0;font-size:.9rem;color:{_MUTED}}}
.meter b{{color:{_INK};font-weight:600;font-size:1rem;margin-right:2px}}
.meter .note{{font-family:{_MONO};font-size:.7rem;text-transform:uppercase;letter-spacing:.12em;color:{_GREEN}}}
/* sections */
section{{padding:96px 0}}
section.tight{{padding:56px 0}}
.sec-head{{text-align:center;max-width:680px;margin:0 auto 56px}}
h2{{font-size:clamp(1.7rem,3.4vw,2.4rem);font-weight:500;letter-spacing:-.03em;line-height:1.15}}
.sec-head p{{color:{_MUTED};margin-top:14px;font-size:1.05rem}}
.kicker{{font-family:{_MONO};font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;
  color:{_GREEN};display:block;margin-bottom:14px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}
.card{{background:{_SURFACE};border:1px solid {_B2};border-radius:16px;padding:30px;
  transition:border-color .15s}}
.card:hover{{border-color:{_B3}}}
.card .ic{{margin-bottom:16px;display:block}}
.card h3{{font-size:1.05rem;font-weight:600;margin-bottom:8px;letter-spacing:-.01em}}
.card p{{color:{_MUTED};font-size:.94rem}}
/* steps */
.steps{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px}}
.step{{position:relative;padding:30px;background:{_SURFACE};border:1px solid {_B2};border-radius:16px}}
.step .num{{font-family:{_MONO};font-size:.75rem;color:{_GREEN};letter-spacing:.1em;display:block;margin-bottom:14px}}
.step h3{{font-size:1.05rem;font-weight:600;margin-bottom:8px}}
.step p{{color:{_MUTED};font-size:.94rem}}
/* code / mock */
.code{{background:#0a0a0a;border:1px solid {_B2};color:#e2e8f0;border-radius:12px;padding:24px;
  font-family:{_MONO};font-size:.86rem;overflow-x:auto;line-height:1.75}}
.code .c{{color:#6b7280}} .code .g{{color:{_GREEN}}} .code .k{{color:#a5b4fc}}
.mock{{background:{_SURFACE};border:1px solid {_B2};border-radius:16px;overflow:hidden;
  max-width:660px;margin:0 auto;text-align:left}}
.mock .bubble{{padding:22px 26px;border-bottom:1px solid {_B1}}}
.mock .q{{color:{_MUTED};font-size:.9rem}}.mock .a{{margin-top:10px;color:{_INK2}}}
.mock .sponsor{{padding:18px 26px;font-size:.9rem;background:#131313}}
.mock .sponsor .tag{{display:inline-block;border:1px solid {_GREEN_BORDER};color:{_GREEN};
  font-family:{_MONO};font-size:.68rem;letter-spacing:.12em;text-transform:uppercase;
  font-weight:500;padding:3px 10px;border-radius:999px;margin-bottom:10px}}
.mock .sponsor b{{color:{_INK}}}
.caption{{text-align:center;color:{_MUTED};margin-top:20px;font-size:.88rem}}
/* two-panel portal home */
.portal-home{{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:56px 0}}
@media(max-width:720px){{.portal-home{{grid-template-columns:1fr}}}}
.portal-col{{background:{_SURFACE};border:1px solid {_B2};border-radius:16px;padding:36px}}
.portal-col h2{{font-size:1.3rem;margin-bottom:10px}}
.portal-col p{{color:{_MUTED};margin-bottom:22px}}
.oauth-note{{font-size:.85rem;color:{_MUTED};margin-top:14px}}
/* forms */
form{{display:flex;flex-direction:column;gap:12px}}
.card form{{margin-top:8px}}
input[type=email],input[type=number],input[type=text],textarea,select{{
  width:100%;padding:12px 14px;border:1px solid {_B2};border-radius:10px;font-size:.95rem;
  background:{_BG};color:{_INK};font-family:inherit}}
input:focus,textarea:focus,select:focus{{outline:none;border-color:{_GREEN}}}
input::placeholder,textarea::placeholder{{color:#555}}
label{{font-weight:500;font-size:.9rem;color:{_INK2}}}
.flash{{background:#1f1a0a;border:1px solid #4d3f14;color:#f5d78e;padding:12px 16px;border-radius:10px;margin:12px 0;font-size:.9rem}}
.error{{background:#2a1215;border:1px solid #4d1f24;color:#fca5a5;padding:12px 16px;border-radius:10px;margin:12px 0;font-size:.9rem}}
/* dashboards */
.dash{{max-width:860px;margin:0 auto;padding:48px 24px}}
.dash h1{{font-size:1.8rem;font-weight:600;letter-spacing:-.02em;margin-bottom:4px}}
.dash .sub{{color:{_MUTED};margin-bottom:28px}}
.stat-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:24px}}
.stat{{background:{_SURFACE};border:1px solid {_B2};border-radius:14px;padding:22px}}
.stat .num{{font-size:1.7rem;font-weight:600;color:{_GREEN};letter-spacing:-.02em}}
.stat .lbl{{font-size:.78rem;color:{_MUTED};margin-top:2px}}
table{{width:100%;border-collapse:collapse;background:{_SURFACE};border:1px solid {_B2};border-radius:12px;overflow:hidden;font-size:.9rem}}
th,td{{text-align:left;padding:12px 16px;border-bottom:1px solid {_B1};color:{_INK2}}}
th{{background:{_SURFACE2};font-weight:600;color:{_MUTED};font-size:.74rem;text-transform:uppercase;letter-spacing:.06em}}
tr:last-child td{{border-bottom:0}}
.code-line{{background:#0a0a0a;border:1px solid {_B2};padding:10px 14px;border-radius:8px;
  font-family:{_MONO};font-size:.85rem;color:#e2e8f0;word-break:break-all;margin:6px 0}}
.badge{{display:inline-block;padding:3px 10px;border-radius:999px;font-size:.72rem;font-weight:600}}
.badge.active{{background:rgba(62,207,142,.12);color:{_GREEN}}}
.badge.paused{{background:rgba(248,113,113,.12);color:#f87171}}
.btn-oauth{{display:block;text-align:center;padding:12px;border:1px solid {_B2};border-radius:10px;
  font-weight:500;color:{_INK};margin:6px 0;background:{_SURFACE}}}
.btn-oauth:hover{{border-color:{_B3};text-decoration:none}}
/* footer */
footer{{background:{_BG};border-top:1px solid {_B1};padding:44px 24px}}
footer .inner{{max-width:1080px;margin:0 auto;display:flex;flex-wrap:wrap;gap:16px;align-items:center;
  font-size:.86rem;color:{_MUTED}}}
footer .links{{margin-left:auto;display:flex;gap:22px}}
footer .links a{{color:{_MUTED}}} footer .links a:hover{{color:{_INK2}}}
/* faq */
.faq{{max-width:720px;margin:0 auto}}
.faq details{{background:{_SURFACE};border:1px solid {_B2};border-radius:12px;padding:18px 22px;margin-bottom:10px}}
.faq summary{{font-weight:500;cursor:pointer;color:{_INK};font-size:.98rem}}
.faq p{{color:{_MUTED};margin-top:10px;font-size:.94rem}}
/* doc pages */
.doc-page{{max-width:760px}}
.doc-page .back{{display:inline-block;margin-bottom:16px;color:{_MUTED}}}
.doc-page h1{{font-size:1.9rem;font-weight:600;margin-bottom:8px}}
.doc-page h2{{font-size:1.35rem;font-weight:600;margin:28px 0 8px}}
.doc-page h3{{font-size:1.1rem;font-weight:600;margin:20px 0 6px}}
.doc-page p{{color:{_INK2};margin:10px 0}}
.doc-page ul,.doc-page ol{{margin:10px 0 10px 24px;color:{_INK2}}}
.doc-page li{{margin:4px 0}}
.doc-page code{{background:{_SURFACE};border:1px solid {_B1};padding:2px 6px;border-radius:5px;font-size:.88em;color:{_INK}}}
.doc-page hr{{border:0;border-top:1px solid {_B1};margin:24px 0}}
.doc-page .doc-code{{background:#0a0a0a;border:1px solid {_B2};color:#e2e8f0;border-radius:10px;padding:16px;
  overflow-x:auto;font-family:{_MONO};font-size:.84rem;margin:12px 0}}
.doc-page blockquote{{border-left:2px solid {_GREEN};padding:6px 16px;margin:12px 0;color:{_MUTED}}}
/* advertiser banner strip (user page) */
.adv-strip{{background:{_SURFACE};border:1px solid {_B2};border-radius:16px;padding:28px 32px;
  display:flex;align-items:center;gap:20px;flex-wrap:wrap}}
.adv-strip p{{color:{_MUTED};font-size:.95rem;flex:1;min-width:240px}}
.adv-strip b{{color:{_INK}}}
"""


def _page(title, body, nav_links=()):
    nav = "".join(f'<a href="{_html.escape(h)}">{_html.escape(t)}</a>' for t, h in nav_links)
    favicon = ("data:image/svg+xml," +
               "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E"
               "%3Ccircle cx='50' cy='50' r='46' fill='%233ecf8e'/%3E"
               "%3Ctext x='50' y='66' font-size='52' font-family='Inter,Arial' font-weight='bold' "
               "text-anchor='middle' fill='%230f0f0f'%3Eg%3C/text%3E%3C/svg%3E")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="guac — inference at a flat discount, funded by disclosed sponsors. Pay below market rate on every request; a sponsor appears below a few answers a day. Point any OpenAI-compatible agent at one URL.">
<meta property="og:title" content="guac — pay wholesale for AI, sponsored">
<meta property="og:description" content="The ad-funded inference gateway. A flat discount on every request, disclosed sponsors, no ads in the model.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://addguac.fly.dev/">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Code+Pro:wght@400;500&display=swap" rel="stylesheet">
<link rel="icon" href="{favicon}">
<title>{_html.escape(title)} · guac</title><style>{_CSS}</style></head>
<body>
<nav class="nav" id="nav"><div class="inner">
  <a class="logo" href="/">guac<span>.</span></a>
  <button class="menu-toggle" aria-label="Menu" onclick="document.getElementById('nav').classList.toggle('open')">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="4" y1="7" x2="20" y2="7"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="17" x2="20" y2="17"/></svg>
  </button>
  <div class="links">{nav}
    <a class="btn btn-primary" href="/portal">Get started</a>
  </div>
</div></nav>
{body}
<footer><div class="inner">
  <div>guac — inference below market rate, funded by disclosed sponsors.</div>
  <div class="links">
    <a href="/advertisers">Advertisers</a><a href="/pitch">Pitch</a><a href="/terms">Terms</a><a href="/privacy">Privacy</a><a href="https://github.com/buckZz7/guac">GitHub</a>
  </div>
</div></footer>
</body></html>"""


def marketing_home(stats=None):
    """The marketing landing page served at /. 100% user-focused: what YOU get.
    Advertisers get their own page at /advertisers. `stats` optionally carries
    live ledger numbers for the public meter."""
    meter = ""
    if stats and stats.get("requests", 0) > 0:
        meter = f"""
<div class="meter"><div class="container" style="display:flex;gap:32px;flex-wrap:wrap;justify-content:center;align-items:center">
  <span><b>{stats['requests']:,}</b> requests served</span>
  <span><b>{stats['impressions']:,}</b> sponsorships delivered</span>
  <span><b>${stats['subsidized_usd']:.2f}</b> billed at the discounted rate</span>
  <span class="note">live from the guac ledger</span>
</div></div>"""
    body = f"""
<div class="hero">
  <span class="eyebrow">Inference, sponsored</span>
  <h1>Top models, up to {_DISCOUNT_PCT}% off.<br><span class="accent">Sponsors fund the discount.</span></h1>
  <p class="lede">Point your agent at one URL. Each model on the menu is billed below market
  price — the discount is set per model, up to {_DISCOUNT_PCT}%, sponsored answer or not. A few
  answers a day carry a disclosed sponsor below them; that ad revenue is what keeps your rate
  low. The model output itself is never touched.</p>
  <div class="cta">
    <a class="btn btn-primary" href="/portal">Get my API key</a>
    <a class="btn btn-ghost" href="#how">How it works</a>
  </div>
  <p class="trust">Any OpenAI-compatible agent · Frontier models pass-through · <b>Ads never enter the model</b></p>
</div>
{meter}

<section id="how" style="padding-top:80px">
  <div class="container">
    <div class="sec-head"><span class="kicker">How it works</span>
      <h2>Three steps. Zero config drama.</h2></div>
    <div class="steps">
      <div class="step"><span class="num">01</span><h3>Top up &amp; connect</h3>
        <p>Get an API key and base URL. Point Hermes, Codex, OpenClaw — any OpenAI-compatible client — at it.</p></div>
      <div class="step"><span class="num">02</span><h3>Billed below market</h3>
        <p>Every request is charged at that model's discounted rate — set per model, always under market. No markup, no subscription, no surprises.</p></div>
      <div class="step"><span class="num">03</span><h3>Sponsors fund the discount</h3>
        <p>A few answers a day carry a disclosed <b>Sponsor:</b> footer. That ad revenue is what pays for your below-market rate.</p></div>
    </div>
  </div>
</section>

<section style="padding-top:0">
  <div class="container">
    <div class="sec-head"><span class="kicker">The exchange</span>
      <h2>Your answer, untouched. The sponsor below it keeps your rate low.</h2></div>
    <div class="mock">
      <div class="bubble"><div class="q">You: Which VPN should I get?</div>
        <div class="a">The best pick depends on your needs — streaming, privacy, or speed. Here are my top recommendations…</div></div>
      <div class="sponsor">
        <span class="tag">Sponsor</span><br>
        <b>Acme VPN</b> — 50% off your first year<br>
        <a href="/pitch">Learn more</a>
      </div>
    </div>
    <p class="caption">Everything above the line is byte-identical to the model's output. The footer is the ad — and it's what funds your discount.</p>
  </div>
</section>

<section id="pricing" style="padding-top:0">
  <div class="container">
    <div class="sec-head"><span class="kicker">Pricing</span>
      <h2>Below market price. Set per model.</h2></div>
    <div class="grid">
      <div class="card"><span class="ic">{_icon('tag')}</span><h3>A discount menu, not one rate</h3>
        <p>Each model has its own discount off the market rate — quality-gated pools carry the biggest cuts. Every request is metered at that model's price.</p></div>
      <div class="card"><span class="ic">{_icon('gift')}</span><h3>Discounted whether sponsored or not</h3>
        <p>You don't earn credits or wait for ads. The discount is in your rate — every request. Sponsors are simply what makes it sustainable.</p></div>
      <div class="card"><span class="ic">{_icon('eye')}</span><h3>Every cent visible</h3>
        <p>Your dashboard shows your balance, what you've spent, and what you've saved vs market price. The ledger is append-only and auditable.</p></div>
    </div>
  </div>
</section>

<section id="models" style="padding-top:0">
  <div class="container">
    <div class="sec-head"><span class="kicker">Models</span>
      <h2>Ask for a model. Get that model.</h2></div>
    <div class="grid">
      <div class="card"><h3>Frontier, pass-through</h3>
        <p>GPT, Claude, Gemini, Llama — request any slug and it's forwarded unchanged, billed at the real wholesale cost.</p></div>
      <div class="card"><h3>Quality-gated open pools</h3>
        <p>Cheap open-model suppliers sit behind a measured quality gate: success rate + latency. Degrading sources are dropped until they recover.</p></div>
      <div class="card"><h3>No silent substitution</h3>
        <p>Name a model and you get it. Generic routing only happens when you ask for "guac".</p></div>
    </div>
  </div>
</section>

<section style="padding-top:0">
  <div class="container">
    <div class="sec-head"><span class="kicker">Setup</span>
      <h2>Connected in one minute</h2></div>
    <div class="code"><span class="c"># Hermes</span>
<span class="g">$</span> hermes config set model.provider custom
<span class="g">$</span> hermes config set model.base_url https://addguac.fly.dev/v1
<span class="g">$</span> hermes config set model.api_key guac_&lt;your-key&gt;

<span class="c"># or any OpenAI-compatible client</span>
<span class="g">$</span> curl https://addguac.fly.dev/v1/chat/completions \
  -H "Authorization: Bearer guac_&lt;your-key&gt;" \
  -d '{{"model":"anthropic/claude-sonnet-4","messages":[{{"role":"user","content":"hello"}}]}}'</div>
  </div>
</section>

<section style="padding-top:0">
  <div class="container">
    <div class="sec-head"><span class="kicker">FAQ</span><h2>Questions</h2></div>
    <div class="faq">
      <details><summary>Do ads go inside my AI answers?</summary><p>No. The model's output is never altered. Sponsors appear only as a clearly-separated footer below the answer, marked "Sponsor".</p></details>
      <details><summary>How does the discount actually work?</summary><p>Each model on the menu has a set discount off its market price, billed on every request. Advertisers pay for disclosed sponsorships below a few answers a day; that revenue funds the gap between your price and market price. Models without a discount are billed at market rate — the dashboard shows each model's price.</p></details>
      <details><summary>What do I pay when there's no sponsor on my answer?</summary><p>The same rate as always. The discount isn't tied to seeing an ad — it's built into each model's price.</p></details>
      <details><summary>Which models can I use?</summary><p>Any model the connected providers serve, by slug — frontier models via pass-through at market rate, plus quality-gated open-model pools carrying discounts of up to {_DISCOUNT_PCT}%.</p></details>
      <details><summary>Which agents work with guac?</summary><p>Anything OpenAI-compatible: Hermes, Codex, OpenClaw, Aider, or a plain script. If it takes a base_url and an API key, it works.</p></details>
      <details><summary>Will I see ads all the time?</summary><p>No — a few a day at most, and only when an advertiser has funded inventory. No funded sponsor, no footer.</p></details>
    </div>
  </div>
</section>

<section class="tight" style="padding-top:0">
  <div class="container">
    <div class="adv-strip">
      <p><b>Running ads?</b> Put your offer below real agent answers — disclosed, budget-capped, metered from the ledger.</p>
      <a class="btn btn-ghost" href="/advertisers">For advertisers &rarr;</a>
    </div>
  </div>
</section>
"""
    return _page("Cheaper tokens, sponsored", body,
                 nav_links=(("How it works", "#how"), ("Pricing", "#pricing"),
                            ("Models", "#models")))


def advertiser_home():
    """Dedicated advertiser page — the marketing surface for the demand side."""
    body = f"""
<div class="hero" style="padding:88px 0 56px">
  <span class="eyebrow">For advertisers</span>
  <h1>Where AI agents<br><span class="accent">actually read.</span></h1>
  <p class="lede">Your offer appears as a disclosed sponsor below real agent answers —
  at the moment the human is reading a result they asked for. No banners, no feed,
  no bots. Budget-capped and metered from the ledger.</p>
  <div class="cta">
    <a class="btn btn-primary" href="/auth/login?role=advertiser">Open the ad manager</a>
    <a class="btn btn-ghost" href="/pitch">Read the pitch</a>
  </div>
</div>

<section style="padding-top:24px">
  <div class="container">
    <div class="grid">
      <div class="card"><span class="ic">{_icon('target')}</span><h3>Genuine attention</h3>
        <p>Placements sit under answers the user just requested — a moment of real focus, not a scroll-past.</p></div>
      <div class="card"><span class="ic">{_icon('chart')}</span><h3>Budget is the demand</h3>
        <p>${'{:.2f}'.format(config.IMPRESSION_COST)} per delivered impression. Your offer runs while it's funded and auto-pauses when spent. No auctions.</p></div>
      <div class="card"><span class="ic">{_icon('check')}</span><h3>Metered, not claimed</h3>
        <p>Impressions and clicks come straight from the ledger. You see the funnel: delivered, clicked, redeemed.</p></div>
      <div class="card"><span class="ic">{_icon('bolt')}</span><h3>One form, live in minutes</h3>
        <p>Headline, body, budget, link. Top up a balance, publish, and the gateway starts serving.</p></div>
    </div>
  </div>
</section>

<section style="padding-top:0">
  <div class="container">
    <div class="sec-head"><span class="kicker">What the user sees</span>
      <h2>A disclosed sponsor. Nothing more.</h2></div>
    <div class="mock">
      <div class="bubble"><div class="q">Agent: Here are three options for managed hosting, each with tradeoffs…</div></div>
      <div class="sponsor">
        <span class="tag">Sponsor</span><br>
        <b>Acme Cloud Hosting</b> — 50% off your first 3 months<br>
        Claim code AGENT50 · <a href="/pitch">Learn more</a>
      </div>
    </div>
    <p class="caption">The answer above the line is never touched. That separation is the product — and why users trust it.</p>
  </div>
</section>

<section style="padding-top:0">
  <div class="container">
    <div class="sec-head"><span class="kicker">How billing works</span><h2>Prepaid balance, per impression</h2></div>
    <div class="steps">
      <div class="step"><span class="num">01</span><h3>Top up</h3>
        <p>Prepaid balance in USD. You can't run ads you haven't funded — that's the whole system's honesty.</p></div>
      <div class="step"><span class="num">02</span><h3>Publish an offer</h3>
        <p>Set a budget (max spend). Each delivered impression debits ${'{:.2f}'.format(config.IMPRESSION_COST)}.</p></div>
      <div class="step"><span class="num">03</span><h3>Watch the funnel</h3>
        <p>Impressions, clicks, redemptions — per offer, from the ledger. Budget spent = auto-pause.</p></div>
    </div>
  </div>
</section>

<section class="tight" style="padding-top:0">
  <div class="container">
    <div class="adv-strip">
      <p><b>Ready to run?</b> Sign in, top up, and your first offer can be live today.</p>
      <a class="btn btn-primary" href="/auth/login?role=advertiser">Open the ad manager</a>
    </div>
  </div>
</section>
"""
    return _page("For advertisers", body,
                 nav_links=(("Ad manager", "/auth/login?role=advertiser"),
                            ("Pitch", "/pitch")))


def portal_home():
    """The portal home — two clear paths (user vs advertiser)."""
    body = """
<div class="container">
  <div class="portal-home">
    <div class="portal-col">
      <h2>I'm using an AI agent</h2>
      <p>Get an API key + base URL, point your agent at guac, and pay less for inference with disclosed sponsors.</p>
      <a class="btn btn-primary btn-block" href="/auth/login?role=user">Get my API key</a>
      <p class="oauth-note"><a href="/auth/login?role=user">Sign in</a> to view your key or settings.</p>
    </div>
    <div class="portal-col">
      <h2>I'm an advertiser</h2>
      <p>Put your offer in front of real AI users. Create offers, set a budget, and see honest impressions and clicks.</p>
      <a class="btn btn-ghost btn-block" href="/auth/login?role=advertiser">Open my ad manager</a>
      <p class="oauth-note"><a href="/pitch">Read the advertiser pitch</a> · <a href="/terms">Terms</a></p>
    </div>
  </div>
</div>
"""
    return _page("Get started", body)


def oauth_login(role, providers):
    """OAuth sign-in chooser."""
    body = f"""
<div class="container" style="max-width:440px;padding:48px 24px">
  <div class="card">
    <h2 style="margin-bottom:6px">Sign in to guac</h2>
    <p style="color:{_MUTED};margin-bottom:20px">Continue as an {'agent user' if role=='user' else 'advertiser'}.</p>
    {_oauth_buttons(role)}
    <p class="oauth-note"><a href="/portal/{'user' if role=='user' else 'advertiser'}/login">or sign in with email</a></p>
  </div>
</div>"""
    return _page("Sign in", body)


def _oauth_buttons(role):
    providers = oauth.providers_configured()
    if not providers:
        return '<p class="oauth-note">Email sign-in is available below.</p>'
    btns = []
    for p in providers:
        label = "GitHub" if p == "github" else "Google"
        btns.append(f'<a class="btn-oauth" href="/auth/start/{p}?role={role}">Continue with {label}</a>')
    return "<br>".join(btns)


def user_login_form(email=None, magic_link=None, error=None, emailed=False):
    flash = ""
    if magic_link:
        if config.DEV_MODE:
            flash = (f'<div class="flash"><strong>Dev mode magic link:</strong> '
                     f'<a href="{_html.escape(magic_link)}">{_html.escape(magic_link)}</a></div>')
        else:
            flash = '<div class="flash"><strong>Check your email</strong> — we sent you a sign-in link.</div>'
    elif emailed and not error:
        flash = '<div class="flash"><strong>Check your email</strong> — we sent you a sign-in link.</div>'
    if error:
        flash = f'<div class="error">{_html.escape(error)}</div>'
    body = f"""
<div class="container" style="max-width:440px;padding:48px 24px">
  <h1 style="margin-bottom:4px">User portal</h1>
  <p style="color:{_MUTED};margin-bottom:20px">Get your API key or sign back in.</p>
  {_oauth_buttons("user")}
  <div class="card" style="margin-top:16px">
    <h2 style="margin-bottom:4px">Or use your email</h2>
    <p style="color:{_MUTED};font-size:.9rem;margin-bottom:12px">We'll send you a magic link to sign in.</p>
    {flash}
    <form method="post" action="/portal/user/login">
      <input type="email" name="email" placeholder="you@example.com"
             value="{_html.escape(email or '')}" required>
      <button class="btn btn-primary" type="submit">Send magic link</button>
    </form>
  </div>
</div>"""
    return _page("User portal", body)


def advertiser_login_form(email=None, magic_link=None, error=None, emailed=False):
    flash = ""
    if magic_link:
        if config.DEV_MODE:
            flash = (f'<div class="flash"><strong>Dev mode magic link:</strong> '
                     f'<a href="{_html.escape(magic_link)}">{_html.escape(magic_link)}</a></div>')
        else:
            flash = '<div class="flash"><strong>Check your email</strong> — we sent you a sign-in link.</div>'
    elif emailed and not error:
        flash = '<div class="flash"><strong>Check your email</strong> — we sent you a sign-in link.</div>'
    if error:
        flash = f'<div class="error">{_html.escape(error)}</div>'
    body = f"""
<div class="container" style="max-width:440px;padding:48px 24px">
  <h1 style="margin-bottom:4px">Advertiser portal</h1>
  <p style="color:{_MUTED};margin-bottom:20px">Manage your offers and budget.</p>
  {_oauth_buttons("advertiser")}
  <div class="card" style="margin-top:16px">
    <h2 style="margin-bottom:4px">Or use your email</h2>
    <p style="color:{_MUTED};font-size:.9rem;margin-bottom:12px">We'll send you a magic link to sign in.</p>
    {flash}
    <form method="post" action="/portal/advertiser/login">
      <input type="email" name="email" placeholder="you@company.com"
             value="{_html.escape(email or '')}" required>
      <button class="btn btn-primary" type="submit">Send magic link</button>
    </form>
  </div>
</div>"""
    return _page("Advertiser portal", body)


def user_dashboard(user, balance, spent, saved):
    body = f"""
<div class="dash">
  <h1>Your agent setup</h1>
  <p class="sub">{_html.escape(user['email'])} · <a href="/portal/logout">log out</a></p>
  <div class="stat-row">
    <div class="stat"><div class="num">${balance:.2f}</div><div class="lbl">your balance</div></div>
    <div class="stat"><div class="num">${spent:.4f}</div><div class="lbl">spent (discounted rate)</div></div>
    <div class="stat"><div class="num">${saved:.4f}</div><div class="lbl">saved vs market price</div></div>
  </div>
  <div class="card" style="margin-bottom:20px">
    <h3>Top up your balance</h3>
    <p style="color:{_MUTED};font-size:.9rem;margin:6px 0 12px">Every request is billed at that
      model's discounted rate — set per model, up to {int(config.DISCOUNT_RATE*100)}% under market.
      Sponsors keep the discounts funded.</p>
    <form method="post" action="/user/topup">
      <input type="hidden" name="api_key" value="{_html.escape(user['api_key'])}">
      <input type="number" name="amount_cents" value="1000" min="100" step="100" style="max-width:160px">
      <button class="btn btn-primary" type="submit">Top up</button>
    </form>
  </div>
  <div class="card">
    <h3>Connect your agent</h3>
    <p style="color:{_MUTED};font-size:.9rem;margin:6px 0 12px">Point any OpenAI-compatible agent at this base URL with this key. Ask for a specific model slug and it's forwarded to the provider unchanged.</p>
    <div class="code-line">{_html.escape(portal.user_base_url())}</div>
    <div class="code-line">{_html.escape(user['api_key'])}</div>
    <p style="color:{_MUTED};font-size:.9rem;margin-top:14px">Example (Hermes):</p>
    <div class="code"><span class="g">$</span> hermes config set model.base_url {_html.escape(portal.user_base_url())}
<span class="g">$</span> hermes config set model.api_key {_html.escape(user['api_key'])}</div>
  </div>
</div>"""
    return _page("User portal", body)


def advertiser_dashboard(advertiser, offers, error=None, created=None, balance=0.0):
    err = f'<div class="error">{_html.escape(error)}</div>' if error else ""
    created_flash = f'<div class="flash">Offer created: <strong>{_html.escape(created)}</strong></div>' if created else ""
    rows = "".join(
        f"<tr><td>{_html.escape(o['headline'])}</td>"
        f"<td>{o['impressions']}</td>"
        f"<td>{o['funnel']['clicked']}</td>"
        f"<td>{o['funnel']['redeemed']}</td>"
        f"<td>${o['spent']:.2f}</td>"
        f"<td>${o['budget']:.2f}</td>"
        f"<td>{'<span class=badge active>active</span>' if o['active'] else '<span class=badge paused>paused</span>'}</td>"
        f"<td>{_toggle(o['id'], o['paused'], advertiser['token'])}</td></tr>"
        for o in offers)
    body = f"""
<div class="dash">
  <h1>Ad manager</h1>
  <p class="sub">{_html.escape(advertiser['email'])} · <a href="/portal/logout">log out</a></p>
  <div class="stat-row">
    <div class="stat"><div class="num">${balance:.2f}</div><div class="lbl">prepaid balance</div></div>
  </div>
  {created_flash}{err}
  <div class="card" style="margin-bottom:20px">
    <h3>Top up your balance</h3>
    <p style="color:{_MUTED};font-size:.9rem;margin:6px 0 12px">Your balance funds impressions. Top up to keep your offers running.</p>
    <form method="post" action="/advertiser/topup">
      <input type="hidden" name="token" value="{_html.escape(advertiser['token'])}">
      <input type="number" name="amount_cents" value="1000" min="100" step="100" style="max-width:160px">
      <button class="btn btn-primary" type="submit">Top up</button>
    </form>
  </div>
  <div class="card" style="margin-bottom:20px">
    <h3>Create an offer</h3>
    <form method="post" action="/portal/advertiser/offer">
      <input type="hidden" name="token" value="{_html.escape(advertiser['token'])}">
      <input type="text" name="headline" placeholder="Headline, e.g. 50% off first 3 months" required>
      <textarea name="body" placeholder="Body / details" rows="2"></textarea>
      <input type="text" name="claim" placeholder="Claim / code, e.g. AGENT50">
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <input type="number" name="budget" placeholder="Budget (USD)" min="0.01" step="0.01" required style="flex:1">
        <select name="offer_type" style="flex:1">
          <option value="discount">Discount</option>
          <option value="trial">Free trial</option>
          <option value="sponsorship">Sponsorship</option>
        </select>
      </div>
      <input type="text" name="image_url" placeholder="Image URL (optional)">
      <input type="text" name="link" placeholder="Link (optional, https://...)">
      <button class="btn btn-primary" type="submit">Create offer</button>
    </form>
    <p style="color:{_MUTED};font-size:.85rem;margin-top:12px">You're billed per impression (${config.IMPRESSION_COST:.2f} each). Offers run while funded. <a href="/pitch">How it works</a>.</p>
  </div>
  <div class="card">
    <h3>Your offers</h3>
    <table>
      <tr><th>Offer</th><th>Impr.</th><th>Clicks</th><th>Redeemed</th><th>Spent</th><th>Budget</th><th>Status</th><th></th></tr>
      {rows if rows else '<tr><td colspan=8 style="color:#64748b">No offers yet. Create one above.</td></tr>'}
    </table>
  </div>
  <div class="card" style="margin-top:20px">
    <h3>Your API token</h3>
    <p style="color:{_MUTED};font-size:.9rem;margin:6px 0 12px">Use this to create/manage offers programmatically.</p>
    <div class="code-line">{_html.escape(advertiser['token'])}</div>
  </div>
</div>"""
    return _page("Ad manager", body)


def _toggle(offer_id, paused, token):
    label = "Resume" if paused else "Pause"
    return (f'<form method="post" action="/portal/advertiser/offer/{offer_id}/toggle" '
            f'style="display:inline">'
            f'<input type="hidden" name="token" value="{_html.escape(token)}">'
            f'{button(label)}</form>')


def button(label):
    return f'<button class="btn btn-ghost" style="padding:6px 12px" type="submit">{_html.escape(label)}</button>'


# ---------------------------------------------------------------------------
# Markdown -> styled HTML (for /pitch, /terms, /privacy docs)
# ---------------------------------------------------------------------------

def _md_inline(text: str) -> str:
    """Minimal inline markdown: bold, italic, code, links. Escapes HTML."""
    import re as _re
    text = _html.escape(text)
    # code spans: `x`
    text = _re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = _re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = _re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    # links [text](url) -> only https, else strip
    def _link(m):
        label, url = m.group(1), m.group(2)
        if url.startswith(("http://", "https://", "/")):
            return f'<a href="{url}">{label}</a>'
        return label
    text = _re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, text)
    return text


def render_markdown(text: str) -> str:
    """Render a markdown string to styled HTML for the doc pages."""
    import re as _re
    lines = text.splitlines()
    html = []
    in_code = False
    code_buf = []
    list_buf = []

    def flush_list():
        if list_buf:
            html.append("<ul>" + "".join(f"<li>{_md_inline(x)}</li>" for x in list_buf) + "</ul>")
            list_buf.clear()

    for line in lines:
        if line.startswith("```"):
            if in_code:
                html.append(f'<pre class="doc-code">{"\n".join(code_buf)}</pre>')
                code_buf = []
                in_code = False
            else:
                flush_list()
                in_code = True
            continue
        if in_code:
            code_buf.append(line)
            continue
        if line.strip() == "":
            flush_list()
            continue
        if line.startswith("### "):
            flush_list(); html.append(f"<h3>{_md_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            flush_list(); html.append(f"<h2>{_md_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            flush_list(); html.append(f"<h1>{_md_inline(line[2:])}</h1>")
        elif line.startswith("- "):
            list_buf.append(line[2:])
        elif _re.match(r"^\d+\.\s", line):
            list_buf.append(_re.sub(r"^\d+\.\s", "", line))
        elif line.startswith("---"):
            flush_list(); html.append("<hr>")
        else:
            flush_list(); html.append(f"<p>{_md_inline(line)}</p>")
    flush_list()
    return "\n".join(html)


def doc_page(title, markdown_text, fallback=None):
    """A docs page in the design system."""
    if not markdown_text:
        markdown_text = fallback or f"# {title}\n\nContent not found."
    body = f"""
<div class="dash doc-page">
  <a href="/" class="back">&larr; guac home</a>
  {render_markdown(markdown_text)}
</div>"""
    return _page(title, body, nav_links=(("For advertisers", "/pitch"), ("Terms", "/terms"), ("Privacy", "/privacy")))
