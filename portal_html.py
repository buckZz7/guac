"""guac portal — HTML UI (server-rendered, no JS framework).

Landing page with two paths, a magic-link login, and per-role dashboards.
All auth is magic-link (no passwords). Dev-mode returns the magic link in
the response instead of emailing it.
"""
import html as _html

import config
import oauth
import portal

_CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  max-width:720px;margin:0 auto;padding:24px;color:#1a1a1a;background:#fafafa;line-height:1.5}
h1{font-size:1.6rem;margin-bottom:4px}
.card{background:#fff;border:1px solid #e3e3e3;border-radius:10px;padding:20px;margin:16px 0}
.card h2{margin-top:0}
input[type=email],input[type=number],textarea{width:100%;padding:10px;border:1px solid #ccc;
  border-radius:6px;font-size:1rem;box-sizing:border-box;margin:6px 0}
button{background:#0a7d5c;color:#fff;border:0;border-radius:6px;padding:10px 18px;font-size:1rem;cursor:pointer}
button:hover{background:#096b4e}
a{color:#0a7d5c;text-decoration:none}
.row{display:flex;gap:16px;flex-wrap:wrap}
.col{flex:1;min-width:260px;border:1px solid #e3e3e3;border-radius:10px;padding:18px;background:#fff}
.code{background:#f0f0f0;padding:10px;border-radius:6px;font-family:monospace;font-size:.9rem;word-break:break-all}
.meta{color:#666;font-size:.85rem}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.75rem}
.badge.active{background:#e6f4ea;color:#0a7d5c}
.badge.paused{background:#fdecea;color:#b3261e}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{text-align:left;padding:8px;border-bottom:1px solid #eee;font-size:.9rem}
.stats{display:flex;gap:24px;flex-wrap:wrap;margin:12px 0}
.stat .num{font-size:1.6rem;font-weight:700}
.stat .lbl{color:#666;font-size:.8rem}
.flash{background:#fff8e1;border:1px solid #ffe082;padding:10px 14px;border-radius:6px;margin:12px 0}
.error{background:#fdecea;border:1px solid #ef9a9a;padding:10px 14px;border-radius:6px;margin:12px 0}
.btn-secondary{background:#fff;color:#0a7d5c;border:1px solid #0a7d5c}
.btn-oauth{display:inline-block;background:#fff;color:#0a7d5c;border:1px solid #0a7d5c;
  border-radius:6px;padding:10px 16px;text-decoration:none;font-weight:600;margin:4px 0}
.oauth{margin:16px 0}
"""


def _page(title, body):
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(title)} · guac</title><style>{_CSS}</style></head>
<body>{body}</body></html>"""


def landing():
    body = """
    <h1>guac</h1>
    <p class="meta">Advertiser pays. User saves. Middleman stays small.</p>
    <div class="row">
      <div class="col">
        <h2>I'm an agent user</h2>
        <p>Point your agent at guac and pay less for inference. A disclosed
        sponsor follows some of your answers — up to a few a day, only when an
        advertiser is funding it. Sign up or log back in with your email.</p>
        <form method="post" action="/portal/user/login">
          <input type="email" name="email" placeholder="you@example.com" required>
          <button type="submit">Get my API key</button>
        </form>
        <p class="meta"><a href="/auth/login?role=user">or sign in with GitHub / Google</a></p>
      </div>
      <div class="col">
        <h2>I'm an advertiser</h2>
        <p>Put your offer in front of people using agent answers. Create offers,
        set a budget, and see impressions and clicks in real time. Per-impression
        billing; your offer runs while it has budget.</p>
        <form method="post" action="/portal/advertiser/login">
          <input type="email" name="email" placeholder="you@company.com" required>
          <button type="submit">Open my ad manager</button>
        </form>
        <p class="meta"><a href="/auth/login?role=advertiser">or sign in with GitHub / Google</a> · <a href="/pitch">Read the advertiser pitch</a></p>
      </div>
    </div>
    <p class="meta" style="margin-top:2.5rem;border-top:1px solid #e3e3e3;padding-top:1rem">
      <a href="/terms">Terms</a> · <a href="/privacy">Privacy</a> ·
      <a href="/pitch">For advertisers</a>
    </p>
    """
    return _page("guac", body)


def _oauth_buttons(role):
    """HTML for configured OAuth sign-in buttons."""
    providers = oauth.providers_configured()
    if not providers:
        return ""
    btns = []
    for p in providers:
        label = "GitHub" if p == "github" else "Google"
        btns.append(f'<a class="btn-oauth" href="/auth/start/{p}?role={role}">'
                    f'Continue with {label}</a>')
    return ('<div class="oauth"><p class="meta">or</p>' + "<br>".join(btns) + "</div>")


def user_login_form(email=None, magic_link=None, error=None, emailed=False):
    flash = ""
    if magic_link:
        if config.DEV_MODE:
            flash = (f'<div class="flash"><strong>Dev mode magic link:</strong>'
                     f'<br><a href="{_html.escape(magic_link)}">{_html.escape(magic_link)}</a></div>')
        else:
            flash = '<div class="flash"><strong>Check your email</strong> — we sent you a sign-in link.</div>'
    elif emailed and not error:
        flash = '<div class="flash"><strong>Check your email</strong> — we sent you a sign-in link.</div>'
    if error:
        flash = f'<div class="error">{_html.escape(error)}</div>'
    body = f"""
    <h1>User portal</h1>
    <a href="/portal" class="meta">← back</a>
    {_oauth_buttons("user")}
    <div class="card">
      <h2>Enter your email</h2>
      <p class="meta">We'll send you a magic link to view your API key.</p>
      {flash}
      <form method="post" action="/portal/user/login">
        <input type="email" name="email" placeholder="you@example.com"
               value="{_html.escape(email or '')}" required>
        <button type="submit">Send magic link</button>
      </form>
    </div>
    """
    return _page("User portal · guac", body)


def oauth_login(role, providers):
    """Standalone OAuth sign-in chooser page."""
    body = f"""
    <h1>Sign in</h1>
    <a href="/portal" class="meta">← back</a>
    <div class="card">
      <h2>Continue with</h2>
      {_oauth_buttons(role)}
      <p class="meta" style="margin-top:12px">
        <a href="/portal/{'user' if role=='user' else 'advertiser'}/login">or use email</a>
      </p>
    </div>
    """
    return _page("Sign in · guac", body)


def user_dashboard(user, savings):
    body = f"""
    <h1>User portal</h1>
    <p class="meta">{_html.escape(user['email'])} · <a href="/portal">log out</a></p>
    <div class="card">
      <h2>Your API key</h2>
      <p class="meta">Point your OpenAI-compatible agent at this base URL with
      this key.</p>
      <div class="code">{_html.escape(portal.user_base_url())}</div>
      <div class="code">{_html.escape(user['api_key'])}</div>
      <p class="meta">Example: <code>--base-url {_html.escape(portal.user_base_url())} --api-key {_html.escape(user['api_key'])}</code></p>
    </div>
    <div class="card">
      <h2>Sponsored messages per day</h2>
      <p class="meta">No frequency choice — a disclosed sponsor follows some of
      your answers, up to a daily cap, and it funds your discount.</p>
    </div>
    <div class="card">
      <h2>Your savings</h2>
      <div class="stats">
        <div class="stat"><div class="num">{savings:.4f}</div>
          <div class="lbl">est. saved (USD)</div></div>
      </div>
      <p class="meta">Cheap-supply savings + advertiser money, per the
      transparent split.</p>
    </div>
    """
    return _page("User portal · guac", body)


def advertiser_login_form(email=None, magic_link=None, error=None, emailed=False):
    flash = ""
    if magic_link:
        if config.DEV_MODE:
            flash = (f'<div class="flash"><strong>Dev mode magic link:</strong>'
                     f'<br><a href="{_html.escape(magic_link)}">{_html.escape(magic_link)}</a></div>')
        else:
            flash = '<div class="flash"><strong>Check your email</strong> — we sent you a sign-in link.</div>'
    elif emailed and not error:
        flash = '<div class="flash"><strong>Check your email</strong> — we sent you a sign-in link.</div>'
    if error:
        flash = f'<div class="error">{_html.escape(error)}</div>'
    body = f"""
    <h1>Advertiser portal</h1>
    <a href="/portal" class="meta">← back</a>
    {_oauth_buttons("advertiser")}
    <div class="card">
      <h2>Enter your email</h2>
      <p class="meta">We'll send you a magic link to open your ad manager.</p>
      {flash}
      <form method="post" action="/portal/advertiser/login">
        <input type="email" name="email" placeholder="you@company.com"
               value="{_html.escape(email or '')}" required>
        <button type="submit">Send magic link</button>
      </form>
    </div>
    """
    return _page("Advertiser portal · guac", body)


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
    <h1>Ad manager</h1>
    <p class="meta">{_html.escape(advertiser['email'])} · <a href="/portal">log out</a></p>
    <div class="card">
      <h2>Your API token</h2>
      <p class="meta">Use this to create/manage offers programmatically.</p>
      <div class="code">{_html.escape(advertiser['token'])}</div>
    </div>
    <div class="card">
      <h2>Balance</h2>
      <div class="stats"><div class="stat"><div class="num">${balance:.2f}</div>
        <div class="lbl">prepaid balance</div></div></div>
      <p class="meta">Your balance funds impressions. Top up to keep your offers running.</p>
      <form method="post" action="/advertiser/topup" class="inline-form" id="topup-form">
        <input type="hidden" name="token" value="{_html.escape(advertiser['token'])}">
        <input type="number" name="amount_cents" value="1000" min="100" step="100">
        <button type="submit">Top up</button>
      </form>
    </div>
    {created_flash}{err}
    <div class="card">
      <h2>Create an offer</h2>
      <form method="post" action="/portal/advertiser/offer">
        <input type="hidden" name="email" value="{_html.escape(advertiser['email'])}">
        <input type="text" name="headline" placeholder="Headline, e.g. 50% off first 3 months" required>
        <textarea name="body" placeholder="Body / details" rows="2"></textarea>
        <input type="text" name="claim" placeholder="Claim / code, e.g. AGENT50">
        <input type="number" name="budget" placeholder="Budget (USD)" min="0.01" step="0.01" required>
        <select name="offer_type">
          <option value="discount">Discount</option>
          <option value="trial">Free trial</option>
          <option value="sponsorship">Sponsorship</option>
        </select>
        <input type="text" name="image_url" placeholder="Image URL (optional creative)">
        <input type="text" name="link" placeholder="Link (optional, e.g. https://.../agent)">
        <button type="submit">Create offer</button>
      </form>
      <p class="meta">You're billed per impression (${config.IMPRESSION_COST:.2f}
      each); the offer auto-pauses when your budget is spent. Your offer runs
      while it has budget — no keyword targeting in V1. <a href="/pitch">How
      guac sponsorship works</a>.</p>
    </div>
    <div class="card">
      <h2>Your offers</h2>
      <table>
        <tr><th>Offer</th><th>Impr.</th><th>Clicks</th><th>Redeemed</th><th>Spent</th><th>Budget</th><th>Status</th><th></th></tr>
        {rows if rows else '<tr><td colspan=8 class=meta>No offers yet. Create one above.</td></tr>'}
      </table>
    </div>
    """
    return _page("Ad manager · guac", body)


def _toggle(offer_id, paused, email):
    label = "Resume" if paused else "Pause"
    return (f'<form method="post" action="/portal/advertiser/offer/{offer_id}/toggle" '
            f'style="display:inline">'
            f'<input type="hidden" name="email" value="{_html.escape(email)}">'
            f'{button(label)}</form>')


def button(label):
    return f'<button class="btn-secondary" type="submit">{_html.escape(label)}</button>'
