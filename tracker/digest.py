"""
digest.py - Turns the agent's findings into an email and sends it to subscribers.
"""

import csv
import datetime as dt
import html
import io
import os
import smtplib
from email.message import EmailMessage

import requests

ORDER = {"high": 0, "medium": 1, "low": 2}
BADGE = {"high": "#b42318", "medium": "#b54708", "low": "#475467"}


def _sorted(findings):
    return sorted(findings, key=lambda f: (ORDER.get(f.get("importance"), 3), f.get("date", "")))


def week_label(end: str) -> str:
    return dt.date.fromisoformat(end).strftime("%B %-d, %Y")


def to_markdown(result: dict) -> str:
    """Plain version, saved in the repo as a weekly archive."""
    lines = [f"# AI Policy Tracker: week ending {week_label(result['end'])}", "",
             result["overview"] or "", ""]
    for country in ["Canada", "United States", "European Union"]:
        items = [f for f in _sorted(result["findings"]) if f.get("jurisdiction") == country]
        lines += [f"## {country}", ""]
        if not items:
            lines += ["No major AI policy developments found this week.", ""]
        for f in items:
            fs = " · Financial services" if f.get("financial_services") else ""
            lines += [f"### [{f['title']}]({f['url']})",
                      f"*{f.get('importance', '').title()} importance · {f.get('date', '')}{fs}*", "",
                      f"**What happened:** {f['what_happened']}", "",
                      f"**Why it matters:** {f['why_it_matters']}", ""]
    lines += ["---", f"Sources checked: {', '.join(result['sources_checked'])}. "
              "Written by an AI agent. Always check the original source before relying on it."]
    return "\n".join(lines)


def to_html(result: dict, unsubscribe_url: str | None) -> str:
    e = html.escape
    parts = [f"""<div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;color:#101828">
<h1 style="font-size:22px;margin-bottom:4px">AI Policy Tracker</h1>
<p style="color:#475467;margin-top:0">Week ending {e(week_label(result['end']))} · Canada, United States and European Union</p>
<p style="font-size:15px;line-height:1.5">{e(result['overview'] or '')}</p>"""]
    for country in ["Canada", "United States", "European Union"]:
        items = [f for f in _sorted(result["findings"]) if f.get("jurisdiction") == country]
        parts.append(f'<h2 style="font-size:18px;border-bottom:1px solid #eaecf0;padding-bottom:6px">{country}</h2>')
        if not items:
            parts.append('<p style="color:#475467">No major AI policy developments found this week.</p>')
        for f in items:
            imp = f.get("importance", "low")
            fs = ' · <span style="color:#175cd3">Financial services</span>' if f.get("financial_services") else ""
            parts.append(f"""<div style="margin:14px 0 20px">
<a href="{e(f['url'])}" style="font-size:16px;font-weight:bold;color:#175cd3;text-decoration:none">{e(f['title'])}</a>
<div style="font-size:12px;margin:4px 0 8px"><span style="color:{BADGE.get(imp, '#475467')};font-weight:bold">{e(imp.upper())}</span>
 · {e(f.get('date', ''))}{fs}</div>
<p style="margin:4px 0;font-size:14px;line-height:1.5"><b>What happened:</b> {e(f['what_happened'])}</p>
<p style="margin:4px 0;font-size:14px;line-height:1.5"><b>Why it matters:</b> {e(f['why_it_matters'])}</p></div>""")
    footer = ("This digest is written by an AI agent that checks the Federal Register, Congress.gov, "
              "LEGISinfo, the Canada Gazette, official EU websites and other official announcements each week. "
              "It can make mistakes, so check the original source before relying on anything here.")
    parts.append(f'<hr style="border:none;border-top:1px solid #eaecf0"><p style="font-size:12px;color:#667085">{e(footer)}')
    if unsubscribe_url:
        parts.append(f'<br><a href="{e(unsubscribe_url)}" style="color:#667085">Unsubscribe</a>')
    parts.append("</p></div>")
    return "\n".join(parts)


def load_subscribers() -> list[str]:
    """Read the Google Form responses sheet (published as CSV).
    Each person's most recent answer wins, so choosing 'Unsubscribe' removes them."""
    emails = set()
    owner = os.environ.get("OWNER_EMAIL")
    if owner:
        emails.add(owner.strip().lower())

    url = os.environ.get("SUBSCRIBERS_CSV_URL")
    if not url:
        return sorted(emails)
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    if not rows:
        return sorted(emails)
    header = [h.lower() for h in rows[0]]
    email_col = next(i for i, h in enumerate(header) if "email" in h)
    action_col = next((i for i, h in enumerate(header) if "subscribe" in h), None)

    status = {}
    for row in rows[1:]:  # rows are in time order, so later answers overwrite earlier ones
        if len(row) <= email_col or "@" not in row[email_col]:
            continue
        addr = row[email_col].strip().lower()
        action = row[action_col].lower() if action_col is not None and len(row) > action_col else "subscribe"
        status[addr] = not action.startswith("unsubscribe")
    emails |= {a for a, on in status.items() if on}
    return sorted(emails)


def send(result: dict, recipients: list[str]) -> None:
    sender = os.environ["GMAIL_ADDRESS"]
    msg = EmailMessage()
    msg["Subject"] = f"AI Policy Tracker: week ending {week_label(result['end'])}"
    msg["From"] = f"AI Policy Tracker <{sender}>"
    msg["To"] = sender               # visible "To" is the bot itself
    msg["Bcc"] = ", ".join(recipients)  # subscribers are hidden from each other
    msg.set_content(to_markdown(result))
    msg.add_alternative(to_html(result, os.environ.get("UNSUBSCRIBE_URL")), subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, os.environ["GMAIL_APP_PASSWORD"])
        smtp.send_message(msg)
