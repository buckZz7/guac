"""guac portal + marketing HTML UI (server-rendered, no JS framework).

One shared design system (light theme, avocado-green accent) across the
marketing landing (/), the portal (login, dashboards), and the OAuth flow.
Clean, mobile-responsive, conversion-focused copy.
"""
import html as _html

import config
import oauth
import portal

_ACCENT = "#2f9e6e"
_ACCENT_DARK = "#237a53"
_INK = "#0f172a"
_MUTED = "#64748b"
_BG = "#f8fafc"
_CARD = "#ffffff"
_BORDER = "#e2e8f0"

_CSS = f"""
*{{box-sizing:border-box;margin:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  background:{_BG};color:{_INK};line-height:1.6;-webkit-font-smoothing:antialiased}}
a{{color:{_ACCENT_DARK};text-decoration:none}} a:hover{{text-decoration:underline}}
.container{{max-width:1080px;margin:0 auto;padding:0 24px}}
/* nav */
.nav{{background:{_CARD};border-bottom:1px solid {_BORDER};position:sticky;top:0;z-index:10}}
.nav .inner{{display:flex;align-items:center;gap:24px;padding:14px 24px;max-width:1080px;margin:0 auto}}
.logo{{font-size:1.35rem;font-weight:800;letter-spacing:-.02em;color:{_INK}}}
.logo span{{color:{_ACCENT}}}
.nav .links{{margin-left:auto;display:flex;gap:20px;align-items:center;font-size:.92rem}}
.nav .links a{{color:{_MUTED}}} .nav .links a:hover{{color:{_INK}}}
.btn{{display:inline-block;padding:10px 20px;border-radius:8px;font-weight:600;font-size:.95rem;
  border:0;cursor:pointer;transition:all .12s}}
.btn-primary{{background:{_ACCENT};color:#fff}} .btn-primary:hover{{background:{_ACCENT_DARK};text-decoration:none}}
.btn-ghost{{background:transparent;color:{_INK};border:1px solid {_BORDER}}}
.btn-ghost:hover{{border-color:{_ACCENT};text-decoration:none}}
.btn-block{{display:block;width:100%;text-align:center}}
/* hero */
.hero{{padding:72px 0 56px;text-align:center}}
.eyebrow{{display:inline-block;background:#e8f5ef;color:{_ACCENT_DARK};font-size:.8rem;font-weight:600;
  padding:6px 14px;border-radius:999px;margin-bottom:20px;letter-spacing:.02em}}
h1{{font-size:clamp(2.2rem,5vw,3.4rem);font-weight:800;letter-spacing:-.03em;line-height:1.1;max-width:800px;margin:0 auto}}
h1 .accent{{color:{_ACCENT}}}
.lede{{font-size:1.2rem;color:{_MUTED};max-width:620px;margin:20px auto 32px}}
.cta{{display:flex;gap:14px;justify-content:center;flex-wrap:wrap}}
.trust{{margin-top:28px;font-size:.85rem;color:{_MUTED}}}
.trust b{{color:{_INK}}}
/* sections */
section{{padding:64px 0}}
section.alt{{background:{_CARD};border-block:1px solid {_BORDER}}}
.sec-head{{text-align:center;max-width:640px;margin:0 auto 40px}}
h2{{font-size:clamp(1.6rem,3vw,2.2rem);font-weight:800;letter-spacing:-.02em}}
.sec-head p{{color:{_MUTED};margin-top:12px;font-size:1.05rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px}}
.card{{background:{_CARD};border:1px solid {_BORDER};border-radius:14px;padding:28px}}
.card.plain{{box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.card .ic{{font-size:1.6rem;margin-bottom:12px}}
.card h3{{font-size:1.1rem;margin-bottom:8px}}
.card p{{color:{_MUTED};font-size:.95rem}}
/* steps */
.steps{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px;counter-reset:step}}
.step{{position:relative;padding:28px;background:{_CARD};border:1px solid {_BORDER};border-radius:14px}}
.step .num{{font-size:2.2rem;font-weight:800;color:{_ACCENT};opacity:.25;line-height:1}}
.step h3{{margin:8px 0 6px}}
.step p{{color:{_MUTED};font-size:.95rem}}
/* code / mock */
.code{{background:#0f172a;color:#e2e8f0;border-radius:12px;padding:24px;font-family:"SFMono-Regular",Consolas,"Liberation Mono",Menlo,monospace;
  font-size:.88rem;overflow-x:auto;line-height:1.7}}
.code .c{{color:#94a3b8}} .code .g{{color:{_ACCENT}}} .code .k{{color:#a5b4fc}}
.mock{{background:{_CARD};border:1px solid {_BORDER};border-radius:14px;overflow:hidden;max-width:640px;margin:0 auto;text-align:left}}
.mock .bubble{{padding:18px 22px;border-bottom:1px solid {_BORDER}}}
.mock .q{{color:{_MUTED}}}.mock .a{{margin-top:8px}}
.mock .sponsor{{border-top:2px dashed {_BORDER};padding:14px 22px;font-size:.9rem}}
.mock .sponsor .tag{{display:inline-block;background:#e8f5ef;color:{_ACCENT_DARK};font-weight:600;
  padding:2px 10px;border-radius:999px;font-size:.75rem;margin-bottom:6px}}
/* two-panel portal home */
.portal-home{{display:grid;grid-template-columns:1fr 1fr;gap:24px;padding:48px 0}}
@media(max-width:720px){{.portal-home{{grid-template-columns:1fr}}}}
.portal-col{{background:{_CARD};border:1px solid {_BORDER};border-radius:16px;padding:36px}}
.portal-col h2{{font-size:1.4rem;margin-bottom:10px}}
.portal-col p{{color:{_MUTED};margin-bottom:20px}}
.oauth-note{{font-size:.85rem;color:{_MUTED};margin-top:14px}}
/* forms */
.card form{{display:flex;flex-direction:column;gap:12px;margin-top:8px}}
input[type=email],input[type=number],input[type=text],textarea,select{{
  width:100%;padding:12px 14px;border:1px solid {_BORDER};border-radius:8px;font-size:.95rem;
  background:#fff;color:{_INK}}}
input:focus,textarea:focus,select:focus{{outline:none;border-color:{_ACCENT}}}
label{{font-weight:600;font-size:.9rem}}
.flash{{background:#fff8e6;border:1px solid #fde68a;padding:12px 16px;border-radius:8px;margin:12px 0;font-size:.9rem}}
.error{{background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;padding:12px 16px;border-radius:8px;margin:12px 0;font-size:.9rem}}
/* dashboards */
.dash{{max-width:860px;margin:0 auto;padding:40px 24px}}
.dash h1{{font-size:1.8rem;margin-bottom:4px}}
.dash .sub{{color:{_MUTED};margin-bottom:28px}}
.stat-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:24px}}
.stat{{background:{_CARD};border:1px solid {_BORDER};border-radius:12px;padding:20px}}
.stat .num{{font-size:1.8rem;font-weight:800;color:{_ACCENT_DARK}}}
.stat .lbl{{font-size:.8rem;color:{_MUTED}}}
table{{width:100%;border-collapse:collapse;background:{_CARD};border:1px solid {_BORDER};border-radius:12px;overflow:hidden;font-size:.9rem}}
th,td{{text-align:left;padding:12px 16px;border-bottom:1px solid {_BORDER}}}
th{{background:#f1f5f9;font-weight:700;color:{_MUTED};font-size:.8rem;text-transform:uppercase;letter-spacing:.04em}}
tr:last-child td{{border-bottom:0}}
.code-line{{background:#f1f5f9;padding:10px 14px;border-radius:8px;font-family:monospace;font-size:.9rem;word-break:break-all;margin:6px 0}}
.badge{{display:inline-block;padding:3px 10px;border-radius:999px;font-size:.75rem;font-weight:600}}
.badge.active{{background:#dcfce7;color:#166534}}
.badge.paused{{background:#fee2e2;color:#991b1b}}
.btn-oauth{{display:block;text-align:center;padding:12px;border:1px solid {_BORDER};border-radius:8px;
  font-weight:600;color:{_INK};margin:6px 0}}
.btn-oauth:hover{{border-color:{_ACCENT};text-decoration:none}}
/* footer */
footer{{background:{_CARD};border-top:1px solid {_BORDER};padding:40px 24px;margin-top:0}}
footer .inner{{max-width:1080px;margin:0 auto;display:flex;flex-wrap:wrap;gap:16px;align-items:center;font-size:.9rem;color:{_MUTED}}}
footer .links{{margin-left:auto;display:flex;gap:20px}}
/* faq */
.faq{{max-width:720px;margin:0 auto}}
.faq details{{background:{_CARD};border:1px solid {_BORDER};border-radius:10px;padding:16px 20px;margin-bottom:10px}}
.faq summary{{font-weight:600;cursor:pointer}}
.faq p{{color:{_MUTED};margin-top:8px;font-size:.95rem}}
/* doc pages */
.doc-page{{max-width:760px}}
.doc-page .back{{display:inline-block;margin-bottom:16px;color:{_MUTED}}}
.doc-page h1{{font-size:1.9rem;margin-bottom:8px}}
.doc-page h2{{font-size:1.35rem;margin:28px 0 8px}}
.doc-page h3{{font-size:1.1rem;margin:20px 0 6px}}
.doc-page p{{color:#334155;margin:10px 0}}
.doc-page ul,.doc-page ol{{margin:10px 0 10px 24px;color:#334155}}
.doc-page li{{margin:4px 0}}
.doc-page code{{background:#f1f5f9;padding:2px 6px;border-radius:5px;font-size:.9em;color:#0f172a}}
.doc-page hr{{border:0;border-top:1px solid {_BORDER};margin:24px 0}}
.doc-page .doc-code{{background:#0f172a;color:#e2e8f0;border-radius:10px;padding:16px;
  overflow-x:auto;font-family:monospace;font-size:.85rem;margin:12px 0}}
.doc-page blockquote{{border-left:3px solid {_ACCENT};padding:6px 16px;margin:12px 0;color:{_MUTED}}}
"""


def _page(title, body, nav_links=()):
    nav = "".join(f'<a href="{_html.escape(h)}">{_html.escape(t)}</a>' for t, h in nav_links)
    favicon = ("data:image/svg+xml," +
               "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E"
               "%3Ccircle cx='50' cy='50' r='46' fill='%232f9e6e'/%3E"
               "%3Ctext x='50' y='66' font-size='52' font-family='Arial' font-weight='bold' "
               "text-anchor='middle' fill='white'%3Eg%3C/text%3E%3C/svg%3E")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="guac — pay less for AI. A disclosed sponsor follows some of your agent's answers and advertiser money lowers your inference cost. Point any OpenAI-compatible agent at one URL.">
<meta property="og:title" content="guac — pay less for AI">
<meta property="og:description" content="The ad-funded AI gateway. Disclosed sponsors, honest pricing, no ads in the model.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://addguac.fly.dev/">
<link rel="icon" href="{favicon}">
<title>{_html.escape(title)} · guac</title><style>{_CSS}</style></head>
<body>
<nav class="nav"><div class="inner">
  <a class="logo" href="/">guac<span>.</span></a>
  <div class="links">{nav}
    <a class="btn btn-primary" href="/portal">Get started</a>
  </div>
</div></nav>
{body}
<footer><div class="inner">
  <div>guac — the ad-funded AI gateway. Disclosed sponsors, honest pricing, no ads in the model.</div>
  <div class="links">
    <a href="/terms">Terms</a><a href="/privacy">Privacy</a><a href="/pitch">For advertisers</a><a href="https://github.com/buckZz7/guac">GitHub</a>
  </div>
</div></footer>
</body></html>"""


def marketing_home():
    """The marketing landing page served at /."""
    body = """
<div class="hero">
  <span class="eyebrow">The ad-funded AI gateway</span>
  <h1>Pay less for AI.<br>Advertisers cover part of the cost.</h1>
  <p class="lede">guac sits between your agent and the model. A clearly-disclosed sponsor follows
  some of your answers — never inside them — and that advertiser money lowers what you pay for
  inference. Point any OpenAI-compatible agent at one URL and start saving.</p>
  <div class="cta">
    <a class="btn btn-primary" href="/portal">Get started free</a>
    <a class="btn btn-ghost" href="#how">See how it works</a>
  </div>
  <p class="trust">No ads in the model · No credits or wallets · <b>Transparent, always</b></p>
</div>

<section id="how">
  <div class="container">
    <div class="sec-head"><h2>How it works</h2>
      <p>Three simple steps. No client changes, no config drama.</p></div>
    <div class="steps">
      <div class="step"><div class="num">1</div><h3>Point your agent at guac</h3>
        <p>One base URL and an API key. Works with Hermes, Codex, OpenClaw, or any OpenAI-compatible client — no code changes.</p></div>
      <div class="step"><div class="num">2</div><h3>Your agent answers normally</h3>
        <p>The model output is never altered. No ads injected into your results, ever.</p></div>
      <div class="step"><div class="num">3</div><h3>You pay less</h3>
        <p>A disclosed <b>Sponsor:</b> footer follows a few answers each day. Advertiser money lowers your per-token cost.</p></div>
    </div>
  </div>
</section>

<section class="alt">
  <div class="container">
    <div class="sec-head"><h2>What it looks like</h2>
      <p>Your answer, untouched. A clearly-labeled sponsor below it.</p></div>
    <div class="mock">
      <div class="bubble"><div class="q">You: Which VPN should I get?</div>
        <div class="a">The best pick depends on your needs — streaming, privacy, or speed. Here are my top recommendations...</div></div>
      <div class="sponsor">
        <span class="tag">Sponsor</span><br>
        <b>NordVPN</b> — Get 66% off for 2 years + 4 months free<br>
        <a href="/go/sponsor-nordvpn">Learn more</a>
      </div>
    </div>
    <p style="text-align:center;color:#64748b;margin-top:20px;font-size:.9rem">The model's answer stays byte-identical. Only the disclosed footer is added.</p>
  </div>
</section>

<section>
  <div class="container">
    <div class="sec-head"><h2>Why people use guac</h2></div>
    <div class="grid">
      <div class="card"><div class="ic">💰</div><h3>Pay less for inference</h3>
        <p>Advertiser money + cheap, quality-gated supply mean a lower price per token than going direct.</p></div>
      <div class="card"><div class="ic">🔒</div><h3>No ads in your results</h3>
        <p>Sponsors are always a separate, disclosed footer — never injected into the model's answer.</p></div>
      <div class="card"><div class="ic">🛠️</div><h3>Works with your setup</h3>
        <p>Any OpenAI-compatible agent. Hermes, Codex, OpenClaw, a raw CLI — it just works.</p></div>
      <div class="card"><div class="ic">🕵️</div><h3>Honest by design</h3>
        <p>Ads only run when funded. No fabricated impressions. The split is always public.</p></div>
    </div>
  </div>
</section>

<section class="alt" id="code">
  <div class="container">
    <div class="sec-head"><h2>Get a key in seconds</h2>
      <p>Sign up, get an API key + base URL, and point your agent at it.</p></div>
    <div class="code"><span class="c"># Hermes</span>
<span class="g">$</span> hermes config set model.provider custom
<span class="g">$</span> hermes config set model.base_url https://addguac.fly.dev/v1
<span class="g">$</span> hermes config set model.api_key guac_&lt;your-key&gt;

<span class="c"># or any OpenAI-compatible client</span>
<span class="g">$</span> curl https://addguac.fly.dev/v1/chat/completions \
  -H "Authorization: Bearer guac_&lt;your-key&gt;" \
  -d '{{"model":"guac","messages":[{{"role":"user","content":"hello"}}]}}'</div>
  </div>
</section>

<section>
  <div class="container">
    <div class="sec-head"><h2>For advertisers</h2>
      <p>Put your offer in front of people actually using AI agents — with honest, metered results.</p></div>
    <div class="grid">
      <div class="card"><div class="ic">🎯</div><h3>Reach active AI users</h3>
        <p>Your offer appears as a disclosed sponsor below real agent answers — genuine attention, not a banner.</p></div>
      <div class="card"><div class="ic">📊</div><h3>Pay for what delivers</h3>
        <p>Per-impression billing. You set a budget; your offer runs only while it's funded and auto-pauses when spent.</p></div>
      <div class="card"><div class="ic">✅</div><h3>Real clicks, real proof</h3>
        <p>Impressions and clicks are metered honestly. See exactly what your budget bought.</p></div>
    </div>
    <div class="cta" style="margin-top:32px"><a class="btn btn-primary" href="/pitch">Read the advertiser pitch</a></div>
  </div>
</section>

<section class="alt">
  <div class="container">
    <div class="sec-head"><h2>FAQ</h2></div>
    <div class="faq">
      <details><summary>Does guac put ads inside my AI answers?</summary><p>No. The model's output is never altered. Sponsors appear only as a clearly-separated footer below the answer, marked with a "Sponsor" label.</p></details>
      <details><summary>Which agents work with guac?</summary><p>Any OpenAI-compatible client — Hermes, Codex, OpenClaw, Aider, or a plain script. If it accepts a base_url and API key, it works.</p></details>
      <details><summary>Is the discount a credit or wallet?</summary><p>No. It's simply a lower price per token. Nothing to manage, nothing to withdraw.</p></details>
      <details><summary>Will I see ads all the time?</summary><p>No — only a few a day, and only when an advertiser is actually funding them. If no one is paying, no ads appear at all.</p></details>
      <details><summary>How is guac different from a normal inference API?</summary><p>You get the same OpenAI-compatible interface, but advertiser funding lowers your cost. It's the honest way to make AI cheaper.</p></details>
    </div>
  </div>
</section>
"""
    return _page("Pay less for AI", body,
                 nav_links=(("How it works", "#how"), ("For advertisers", "/pitch"), ("GitHub", "https://github.com/buckZz7/guac")))


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


def user_dashboard(user, savings):
    body = f"""
<div class="dash">
  <h1>Your API key</h1>
  <p class="sub">{_html.escape(user['email'])} · <a href="/portal/logout">log out</a></p>
  <div class="stat-row">
    <div class="stat"><div class="num">${savings:.4f}</div><div class="lbl">estimated savings</div></div>
  </div>
  <div class="card">
    <h3>Connect your agent</h3>
    <p style="color:{_MUTED};font-size:.9rem;margin:6px 0 12px">Point any OpenAI-compatible agent at this base URL with this key.</p>
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
        f"<td>{_toggle(o['id'], o['paused'], advertiser['email'])}</td></tr>"
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
      <input type="hidden" name="email" value="{_html.escape(advertiser['email'])}">
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


def _toggle(offer_id, paused, email):
    label = "Resume" if paused else "Pause"
    return (f'<form method="post" action="/portal/advertiser/offer/{offer_id}/toggle" '
            f'style="display:inline">'
            f'<input type="hidden" name="email" value="{_html.escape(email)}">'
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
