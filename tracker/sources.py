"""
sources.py - The agent's TOOLS.

Each function here fetches information from one place (a government database,
a news search, a web page) and returns plain text the AI can read.

The agent decides which of these to call, in what order, and with what
search terms. That decision-making is what makes it an "agent" rather than
a simple script.
"""

import datetime as dt
import io
import os
import re
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "AI-Policy-Tracker/1.0 (student project, Harvard Kennedy School)"}
TIMEOUT = 30

# Words that suggest a document is about AI. Used to filter long lists of bills.
AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "algorithm", "automated decision",
    "generative", "deepfake", "deep fake", "large language model", "frontier model",
    "neural network", "facial recognition", "biometric", "chatbot", "synthetic media",
    "autonomous system", "intelligence artificielle",
]
AI_WORD = re.compile(r"\bA\.?I\.?\b")  # "AI" or "A.I." as a whole word, capital letters only


def looks_like_ai(text: str) -> bool:
    """True if the text mentions AI or a related term."""
    if not text:
        return False
    lower = text.lower()
    return any(k in lower for k in AI_KEYWORDS) or bool(AI_WORD.search(text))


def _since(days: int, end_date: dt.date | None = None) -> tuple[dt.date, dt.date]:
    end = end_date or dt.date.today()
    return end - dt.timedelta(days=days), end


# ---------------------------------------------------------------------------
# United States
# ---------------------------------------------------------------------------

def search_federal_register(query: str, days: int = 7, end_date: dt.date | None = None) -> list[dict]:
    """US Federal Register: rules, proposed rules, notices and presidential documents.
    No API key needed."""
    start, end = _since(days, end_date)
    params = {
        "conditions[term]": query,
        "conditions[publication_date][gte]": start.isoformat(),
        "conditions[publication_date][lte]": end.isoformat(),
        "per_page": 20,
        "order": "relevance",
        "fields[]": ["title", "abstract", "html_url", "publication_date", "agencies", "type"],
    }
    r = requests.get("https://www.federalregister.gov/api/v1/documents.json",
                     params=params, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    results = []
    for d in r.json().get("results", []):
        agencies = ", ".join(a.get("name", "") for a in d.get("agencies") or [] if a.get("name"))
        results.append({
            "title": d.get("title"),
            "url": d.get("html_url"),
            "date": d.get("publication_date"),
            "type": d.get("type"),
            "agency": agencies,
            "summary": (d.get("abstract") or "")[:600],
        })
    return results


_CONGRESS_TYPES = {
    "HR": "house-bill", "S": "senate-bill",
    "HRES": "house-resolution", "SRES": "senate-resolution",
    "HJRES": "house-joint-resolution", "SJRES": "senate-joint-resolution",
    "HCONRES": "house-concurrent-resolution", "SCONRES": "senate-concurrent-resolution",
}


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def search_congress_bills(days: int = 7, end_date: dt.date | None = None) -> list[dict]:
    """US Congress: bills with any activity in the window, filtered to AI-related titles.
    Needs a free CONGRESS_API_KEY from api.congress.gov."""
    key = os.environ.get("CONGRESS_API_KEY")
    if not key:
        return [{"note": "Congress.gov is not set up (no CONGRESS_API_KEY). Skip this source."}]
    start, end = _since(days, end_date)
    found, offset = [], 0
    while offset < 2500:  # safety cap on how many bills we scan
        params = {
            "api_key": key, "format": "json", "limit": 250, "offset": offset,
            "fromDateTime": f"{start.isoformat()}T00:00:00Z",
            "toDateTime": f"{end.isoformat()}T23:59:59Z",
            "sort": "updateDate+desc",
        }
        r = requests.get("https://api.congress.gov/v3/bill", params=params,
                         headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        bills = r.json().get("bills", [])
        for b in bills:
            if not looks_like_ai(b.get("title", "")):
                continue
            btype = (b.get("type") or "").upper()
            url = (f"https://www.congress.gov/bill/{_ordinal(int(b['congress']))}-congress/"
                   f"{_CONGRESS_TYPES.get(btype, 'house-bill')}/{b.get('number')}")
            action = b.get("latestAction") or {}
            found.append({
                "title": f"{btype} {b.get('number')}: {b.get('title')}",
                "url": url,
                "date": action.get("actionDate"),
                "latest_action": action.get("text"),
            })
        if len(bills) < 250:
            break
        offset += 250
    return found


# ---------------------------------------------------------------------------
# Canada
# ---------------------------------------------------------------------------

def search_canadian_bills(days: int = 7, end_date: dt.date | None = None) -> list[dict]:
    """Canadian Parliament (LEGISinfo): current-session bills with AI-related titles
    that had activity in the window. No API key needed."""
    start, end = _since(days, end_date)
    r = requests.get("https://www.parl.ca/legisinfo/en/bills/json", headers=HEADERS, timeout=60)
    r.raise_for_status()
    found = []
    for b in r.json():
        titles = f"{b.get('LongTitleEn') or ''} {b.get('ShortTitleEn') or ''}"
        if not looks_like_ai(titles):
            continue
        last = (b.get("LatestBillEventDateTime") or "")[:10]
        try:
            last_date = dt.date.fromisoformat(last)
        except ValueError:
            continue
        if not (start <= last_date <= end):
            continue
        code = (b.get("NumberCode") or "").lower()
        found.append({
            "title": f"Bill {b.get('NumberCode')}: {b.get('ShortTitleEn') or b.get('LongTitleEn')}",
            "url": f"https://www.parl.ca/legisinfo/en/bill/{b.get('ParliamentNumber')}-{b.get('SessionNumber')}/{code}",
            "date": last,
            "status": b.get("StatusNameEn"),
            "latest_event": b.get("LatestBillEventTypeNameEn"),
            "sponsor": b.get("SponsorPersonName"),
        })
    return found


def list_canada_gazette_issues(days: int = 7, end_date: dt.date | None = None) -> list[dict]:
    """Canada Gazette Part I (proposed regulations, notices) and Part II (final regulations).
    Returns the issues published in the window. Use read_webpage on an issue link to
    see its table of contents."""
    start, end = _since(days, end_date)
    issues = []
    for part, feed in [("Part I", "https://gazette.gc.ca/rss/p1-eng.xml"),
                       ("Part II", "https://gazette.gc.ca/rss/p2-eng.xml")]:
        r = requests.get(feed, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        for item in ET.fromstring(r.content).iter("item"):
            pub = item.findtext("pubDate") or ""
            try:
                d = dt.datetime.strptime(pub[:16], "%a, %d %b %Y").date()
            except ValueError:
                continue
            if start <= d <= end:
                issues.append({"part": part, "title": item.findtext("title"),
                               "url": item.findtext("link"), "date": d.isoformat()})
    return issues


# ---------------------------------------------------------------------------
# General tools
# ---------------------------------------------------------------------------

def _read_pdf(r, max_chars: int) -> dict:
    """Pull the text out of a PDF (many official rules and notices are PDFs)."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(r.content))
    text = ""
    for page in reader.pages[:15]:  # first 15 pages is plenty to understand a document
        text += (page.extract_text() or "") + "\n"
        if len(text) > max_chars:
            break
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        text = "(This PDF has no readable text, it may be a scanned image.)"
    return {"url": r.url, "type": "pdf", "pages": len(reader.pages), "text": text[:max_chars]}


def read_webpage(url: str, max_chars: int = 8000) -> dict:
    """Download a web page and return its readable text (cut to max_chars)."""
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    if "pdf" in r.headers.get("Content-Type", "").lower() or r.content[:5] == b"%PDF-":
        return _read_pdf(r, max_chars)
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = re.sub(r"\n\s*\n+", "\n", soup.get_text("\n")).strip()
    links = []
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        if label and looks_like_ai(label):
            links.append({"text": label[:200], "url": requests.compat.urljoin(r.url, a["href"])})
    return {"url": r.url, "text": text[:max_chars], "ai_related_links_on_page": links[:30]}


def web_search(llm, query: str, days: int = 7) -> list[dict]:
    """Search the web with Google (through Gemini's search grounding).
    Used for things without a clean database: regulators (OSFI, ISED, FTC, CFPB),
    the White House, provincial governments, and news coverage.
    Only returns links Google actually found, never links the AI wrote itself."""
    from google.genai import types

    prompt = (f"Search for official government or regulator announcements from the past {days} days "
              f"about: {query}. Today is {dt.date.today().isoformat()}. "
              "Briefly list each relevant item with its date and what it is.")
    resp = llm.generate(prompt, types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]))
    results = []
    meta = resp.candidates[0].grounding_metadata if resp.candidates else None
    for chunk in (getattr(meta, "grounding_chunks", None) or []):
        web = getattr(chunk, "web", None)
        if not web or not web.uri:
            continue
        url = web.uri
        try:  # Google gives redirect links; follow them to get the real address
            url = requests.get(web.uri, headers=HEADERS, timeout=15, allow_redirects=True).url
        except requests.RequestException:
            pass
        results.append({"title": web.title, "url": url})
    return [{"search_summary": (resp.text or "")[:1500]}] + results


EU_DOMAINS = ("europa.eu",)  # covers the Commission, AI Office, Parliament, Council, EUR-Lex, EBA, ESMA, EIOPA, ECB


def search_eu_sources(llm, query: str, days: int = 7) -> list[dict]:
    """European Union: searches official EU websites only (anything on europa.eu), such as the
    European Commission and its AI Office, EUR-Lex, the European Parliament, and EU financial
    regulators (EBA, ESMA, EIOPA, ECB). Results from other websites are dropped."""
    results = web_search(llm, f"{query} site:europa.eu", days)
    summary, links = results[0], results[1:]
    official = [r for r in links if any(d in (r.get("url") or "") for d in EU_DOMAINS)]
    if not official:
        summary["note"] = "No official EU pages found for this search. Try different words."
    return [summary] + official
