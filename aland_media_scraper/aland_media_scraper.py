# -*- coding: utf-8 -*-
"""
Åland demilitarisation/neutralisation media scraper, 2024 to present.

Covers four media spheres:
  Åland           Ålandstidningen, Nya Åland, Ålands Radio
  Finlandssvensk  Svenska Yle, HBL, Vasabladet, ÖT, ÅU, Östnyland, Västra Nyland, Syd-Österbotten
  Finland         Yle, HS, Iltalehti, Ilta-Sanomat, MTV Uutiset, Turun Sanomat, Aamulehti, Kaleva
  Sverige         SVT, Sveriges Radio, DN, SvD, Aftonbladet, Expressen, GP, Sydsvenskan, Omni

Pipeline:
  1. DISCOVER candidate URLs from several backends (each optional):
       yle      Yle search API (Svenska Yle + Finnish Yle), full archive
       wp       WordPress REST search, probed per outlet (works only on WP sites)
       sitemap  outlet sitemaps, filtered by date and by keywords in URL slug / news:title
       gdelt    GDELT DOC 2.0 API. NB: rolling window of the last ~3 months only, so it
                cannot reach back to 2024; useful for keeping the corpus current
       urls     a text/CSV file of URLs you add by hand (Retriever, omvärldsbevakning, tips)
  2. SCRAPE each candidate (trafilatura), respecting robots.txt and a per-host delay.
     Results are cached in scrape_cache.jsonl so re-runs skip already fetched URLs and
     re-coding with changed regexes needs no network.
  3. FILTER on date range and relevance (Åland referent + demilitarisation/neutralisation
     or security context), and CODE with the codebook's cat_* flags (Swedish baseline
     regexes from the codebook, extended with Finnish and English equivalents).
  4. WRITE codebook-shaped CSVs (one row = one article, id = YYYYMMDD-SRC-slug[-nn]).

Usage:
  python aland_media_scraper.py
  python aland_media_scraper.py --regions aland finlandssvensk --backends yle sitemap
  python aland_media_scraper.py --discover-only          # just build candidates.csv
  python aland_media_scraper.py --recode                 # re-code from cache, no fetching
  python aland_media_scraper.py --urls-file extra_urls.txt --backends urls
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import random
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests

try:
    import trafilatura
except ImportError:  # discovery still works without it
    trafilatura = None

# =========================
# CONFIG
# =========================

DEFAULT_START = "2024-01-01"
DEFAULT_END = date.today().isoformat()

PER_HOST_DELAY = 1.5           # seconds between requests to the same host
REQUEST_TIMEOUT = 40
MAX_RETRIES = 3

THIN_TEXT_LEN = 900            # below this, treat as paywall/teaser
MIN_ALAND_MENTIONS = 2         # body mentions needed for "context" tier without title match
SITEMAP_MAX_FILES = 4000       # per outlet, safety cap on child sitemaps
YLE_PAGE_SIZE = 100
YLE_MAX_PER_QUERY = 2000

# Public key pair used by yle.fi's own search page. If Yle rotates it, open
# yle.fi/haku in a browser, watch the network tab and paste the new values here.
YLE_APP_ID = "hakuylefi_v2_prod"
YLE_APP_KEY = "4c1422b466ee676e03c4ba9866c0921f"
YLE_SEARCH_URL = "https://yle-fi-search.api.yle.fi/v1/search"

GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_WINDOW_DAYS = 90

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# =========================
# OUTLETS
# =========================

@dataclass
class Outlet:
    code: str            # codebook source code (ALST, AR, NYAN, …)
    name: str
    domain: str
    region: str          # Åland | Finlandssvensk | Finland | Sverige
    lang: str            # sv | fi
    sitemaps: List[str] = field(default_factory=list)  # extra known sitemap URLs
    local: bool = False  # Åland outlet: everything is about Åland, so filter on topic instead


OUTLETS: List[Outlet] = [
    # --- Åland ---
    Outlet("ALST", "Ålandstidningen", "alandstidningen.ax", "Åland", "sv", local=True),
    Outlet("NYAN", "Nya Åland", "nyan.ax", "Åland", "sv", local=True),
    Outlet("AR", "Ålands Radio", "alandsradio.ax", "Åland", "sv", local=True),
    # --- Finlandssvensk ---
    Outlet("SYLE", "Svenska Yle", "svenska.yle.fi", "Finlandssvensk", "sv"),
    Outlet("HBL", "Hufvudstadsbladet", "hbl.fi", "Finlandssvensk", "sv"),
    Outlet("VBL", "Vasabladet", "vasabladet.fi", "Finlandssvensk", "sv"),
    Outlet("OT", "Österbottens Tidning", "osterbottenstidning.fi", "Finlandssvensk", "sv"),
    Outlet("AU", "Åbo Underrättelser", "abounderrattelser.fi", "Finlandssvensk", "sv"),
    Outlet("ON", "Östnyland", "ostnyland.fi", "Finlandssvensk", "sv"),
    Outlet("VN", "Västra Nyland", "vastranyland.fi", "Finlandssvensk", "sv"),
    Outlet("SO", "Syd-Österbotten", "syd-osterbotten.fi", "Finlandssvensk", "sv"),
    # --- Finland (finskspråkig) ---
    Outlet("YLE", "Yle", "yle.fi", "Finland", "fi"),
    Outlet("HS", "Helsingin Sanomat", "hs.fi", "Finland", "fi"),
    Outlet("IL", "Iltalehti", "iltalehti.fi", "Finland", "fi"),
    Outlet("IS", "Ilta-Sanomat", "is.fi", "Finland", "fi"),
    Outlet("MTV", "MTV Uutiset", "mtvuutiset.fi", "Finland", "fi"),
    Outlet("TS", "Turun Sanomat", "ts.fi", "Finland", "fi"),
    Outlet("AL", "Aamulehti", "aamulehti.fi", "Finland", "fi"),
    Outlet("KAL", "Kaleva", "kaleva.fi", "Finland", "fi"),
    # --- Sverige ---
    Outlet("SVT", "SVT Nyheter", "svt.se", "Sverige", "sv"),
    Outlet("SR", "Sveriges Radio", "sverigesradio.se", "Sverige", "sv"),
    Outlet("DN", "Dagens Nyheter", "dn.se", "Sverige", "sv"),
    Outlet("SVD", "Svenska Dagbladet", "svd.se", "Sverige", "sv"),
    Outlet("AB", "Aftonbladet", "aftonbladet.se", "Sverige", "sv"),
    Outlet("EXP", "Expressen", "expressen.se", "Sverige", "sv"),
    Outlet("GP", "Göteborgs-Posten", "gp.se", "Sverige", "sv"),
    Outlet("SDS", "Sydsvenskan", "sydsvenskan.se", "Sverige", "sv"),
    Outlet("OMNI", "Omni", "omni.se", "Sverige", "sv"),
]

REGION_KEYS = {
    "aland": "Åland",
    "finlandssvensk": "Finlandssvensk",
    "finland": "Finland",
    "sverige": "Sverige",
}

FINLANDSSVENSK_DOMAINS = {o.domain for o in OUTLETS if o.region == "Finlandssvensk"}

# =========================
# SEARCH TERMS
# =========================

QUERIES = {
    "sv": [
        "demilitarisering Åland", "Ålands demilitarisering", "demilitariserade Åland",
        "neutralisering Åland", "Ålandskonventionen", "Ålandsöverenskommelsen",
        "Ålandsfrågan", "Åland Nato", "Åland försvar", "Åland säkerhetspolitik",
        "ryska konsulatet Mariehamn", "Åland militär",
    ],
    "fi": [
        "Ahvenanmaan demilitarisointi", "Ahvenanmaa demilitarisointi",
        "demilitarisoitu Ahvenanmaa", "Ahvenanmaan sopimus", "Ahvenanmaan sopimukset",
        "Ahvenanmaa Nato", "Ahvenanmaa puolustus", "Ahvenanmaan konsulaatti",
        "Ahvenanmaan asema", "Ahvenanmaan linnoittaminen",
    ],
}

# Tokens looked for in URL slugs / news:title (diacritics stripped, lowercased).
SLUG_ALAND = ("aland", "ahvenanma", "mariehamn", "maarianhamin")
SLUG_TOPIC = (
    "demilitar", "avmilitar", "neutralis", "nato", "forsvar", "sakerhet", "militar",
    "beredskap", "varnplikt", "konsulat", "ryss", "konvention", "puolustu",
    "turvallisuu", "sotila", "konsulaat", "venaj", "asevelvol", "varautum",
)

# =========================
# CODEBOOK REGEXES
# =========================
# Swedish parts follow the codebook baselines (2025-09-24) with two repairs:
# cat_VPLIKT and cat_IDENT lacked a trailing "*" and cat_RUSSIA's "." between
# "konsulat" and "ryss" is widened to ".{0,40}". Finnish/English parts are additions.

W = r"[a-zåäö\-]*"

CODES: Dict[str, str] = {
    "cat_DEMIL": rf"\b(?:de|av)militari[sz]{W}",
    "cat_NEUTR": rf"\bneutrali[sz]{W}",
    "cat_BERED": rf"\bberedskap{W}|\bcivilförsvar{W}|\btotalförsvar{W}"
                 rf"|\bvarautumi{W}|\bväestönsuojel{W}|\bhuoltovarmuu{W}|\bpreparedness\b",
    "cat_VPLIKT": rf"v[äa]rnplikt{W}|\bcivilplikt{W}|\basevelvolli{W}|\bsiviilipalvelu{W}|\bconscription\b",
    "cat_NATO": rf"\bnato{W}",
    "cat_RUSSIA": rf"\bryssland{W}|\bryska\s+konsulat{W}|\bkonsulat{W}.{{0,40}}\bryss"
                  rf"|\bvenäj[äa]{W}|\bvenäläi{W}|\bkonsulaat{W}|\brussia{W}",
    "cat_IDENT": rf"identitet{W}|fredens\s+öar|\bidentiteet{W}|\brauhan\s+saar{W}|\bidentity\b",
    "cat_MINSKY": rf"minoritetsskydd{W}|vähemmistösuoj{W}",
    "cat_MINOR": rf"\bminoritet{W}|\bvähemmistö{W}|\bminorit(?:y|ies)\b",
    "cat_ALAND": rf"\b[åa]land{W}|\bahvenanma{W}|\bmariehamn{W}|\bmaarianhamin{W}|åländsk{W}|ålänning{W}",
    "cat_ALPER": rf"åländsk{W}\W{{0,20}}perspektiv|perspektiv\W{{0,20}}åländsk{W}",
    "cat_OPPOLL": rf"enkät{W}|opinionsmätning{W}|gallup{W}|mielipidemittau{W}|\bkysely{W}",
}
FLAG_COLS = list(CODES.keys())
CODE_RE = {k: re.compile(v, re.IGNORECASE | re.UNICODE) for k, v in CODES.items()}

# Relevance helpers (not codebook categories)
TREATY_RE = re.compile(
    rf"ålandskonvention{W}|ålandsöverenskommelse{W}|ålandsfråga{W}|ålandsservitut{W}"
    rf"|\b1921\s+års\s+(?:konvention|ålandskonvention){W}|\bkrimkriget{W}"
    rf"|ahvenanmaan\s+(?:sopimu|demilitar|kysymy|linnoitta){W}|ahvenanmaa-sopimu{W}"
    rf"|åland\s+(?:islands\s+)?convention",
    re.IGNORECASE | re.UNICODE,
)
SECURITY_RE = re.compile(
    rf"\bförsvar{W}|\bsäkerhetspoliti{W}|\bmilitär{W}|\bpuolustu{W}|\bturvallisuu{W}"
    rf"|\bsotila{W}|\bdefen[cs]e\b|\bmilitary\b|\bsecurity\s+polic{W}",
    re.IGNORECASE | re.UNICODE,
)
SECURITY_CATS = ("cat_NATO", "cat_RUSSIA", "cat_BERED", "cat_VPLIKT")

BOILERPLATE = (
    "cookie", "prenumerera", "logga in", "annons", "nyhetsbrev", "integritetspolicy",
    "godkänn", "samtycke", "tilaa", "kirjaudu", "evästeet", "mainos", "subscribe",
)

# =========================
# OUTPUT COLUMNS
# =========================

ARTICLE_COLS = [
    "id", "Date", "date_iso", "title", "url", "source", "source_code", "region", "language",
    "section", "byline", "lead", "full_text", "word_count", "seeds", "codes",
    "relevance_tier", "aland_mentions", "aland_in_title", "topic_hits", "security_hits",
    "scrape_quality", "notes",
] + FLAG_COLS

CANDIDATE_COLS = ["url", "title", "date_hint", "outlet_code", "region", "language", "backend", "query"]

# =========================
# HTTP
# =========================

class Http:
    """requests.Session with per-host throttling, retries and robots.txt checks."""

    def __init__(self, user_agent: str, respect_robots: bool = True):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": user_agent,
            "Accept-Language": "sv-FI,sv;q=0.9,fi;q=0.8,en;q=0.7",
        })
        self.ua = user_agent
        self.respect_robots = respect_robots
        self._last: Dict[str, float] = {}
        self._robots: Dict[str, Optional[RobotFileParser]] = {}

    def _throttle(self, host: str) -> None:
        wait = PER_HOST_DELAY - (time.time() - self._last.get(host, 0.0))
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.4))
        self._last[host] = time.time()

    def robots(self, url: str) -> Optional[RobotFileParser]:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = None
            try:
                self._throttle(p.netloc)
                r = self.s.get(base + "/robots.txt", timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    rp = RobotFileParser()
                    rp.parse(r.text.splitlines())
            except requests.RequestException:
                rp = None
            self._robots[base] = rp
        return self._robots[base]

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        rp = self.robots(url)
        return True if rp is None else rp.can_fetch(self.ua, url)

    def get(self, url: str, params: Optional[dict] = None, check_robots: bool = True) -> Optional[requests.Response]:
        if check_robots and not self.allowed(url):
            log(f"    robots.txt disallows {url[:100]}")
            return None
        host = urlparse(url).netloc
        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle(host)
            try:
                r = self.s.get(url, params=params, timeout=REQUEST_TIMEOUT)
            except requests.RequestException as e:
                log(f"    {type(e).__name__} on {url[:90]} (attempt {attempt})")
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(30, 3 * 2 ** attempt))
                continue
            return None  # 403/404 etc: not worth retrying
        return None

# =========================
# HELPERS
# =========================

def log(msg: str) -> None:
    print(msg, flush=True)


def strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|ref$|share|cmpid|xtor|at_)", re.I)


def canon_url(url: str) -> str:
    p = urlparse(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING_PARAMS.match(k)]
    netloc = p.netloc.lower()
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower() or "https", netloc, path, "", urlencode(q), ""))


def host_of(url: str) -> str:
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def outlet_for(url: str) -> Optional[Outlet]:
    h = host_of(url)
    best = None
    for o in OUTLETS:
        if h == o.domain or h.endswith("." + o.domain):
            if best is None or len(o.domain) > len(best.domain):  # svenska.yle.fi beats yle.fi
                best = o
    return best


def region_for_unknown(url: str) -> Tuple[str, str]:
    h = host_of(url)
    if h.endswith(".ax"):
        return "Åland", "sv"
    if h.endswith(".fi"):
        return ("Finlandssvensk", "sv") if h in FINLANDSSVENSK_DOMAINS else ("Finland", "fi")
    if h.endswith(".se"):
        return "Sverige", "sv"
    return "", ""


def source_code_fallback(name: str) -> str:
    letters = re.sub(r"[^A-Za-z]", "", strip_diacritics(name)).upper()
    return letters[:4] or "NSRC"


DATE_PATTERNS = [
    re.compile(r"(20\d{2})-(\d{2})-(\d{2})"),
    re.compile(r"(20\d{2})(\d{2})(\d{2})(?:T|\d{6}|\b)"),
    re.compile(r"(\d{1,2})\.(\d{1,2})\.(20\d{2})"),
]


def parse_date(s: Optional[str]) -> Optional[date]:
    """Tolerant parse: ISO, YYYYMMDD[THHMMSS], DD.MM.YYYY."""
    if not s:
        return None
    s = str(s).strip()
    for i, rx in enumerate(DATE_PATTERNS):
        m = rx.search(s)
        if not m:
            continue
        try:
            if i == 2:
                d, mo, y = (int(x) for x in m.groups())
            else:
                y, mo, d = (int(x) for x in m.groups())
            return date(y, mo, d)
        except ValueError:
            continue
    return None


URL_DATE_RE = re.compile(r"/(20\d{2})[/-](\d{1,2})(?:[/-](\d{1,2}))?(?:/|-|$)")


def date_from_url(url: str) -> Optional[date]:
    m = URL_DATE_RE.search(urlparse(url).path)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
        except ValueError:
            return None
    m = DATE_PATTERNS[0].search(urlparse(url).path)  # only unambiguous YYYY-MM-DD; bare digit runs are often IDs
    return parse_date(m.group(0)) if m else None


def slug_tokens(url: str, title: str = "") -> List[str]:
    text = strip_diacritics(urlparse(url).path + " " + title).lower()
    return [t for t in re.split(r"[^a-z0-9]+", text) if t]


def tokens_match(tokens: Iterable[str], stems: Tuple[str, ...]) -> bool:
    return any(t.startswith(s) for t in tokens for s in stems)


def make_slug(title: str, max_len: int = 60) -> str:
    s = strip_diacritics(title or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_len].rstrip("-") or "untitled"


def clean_text(text: str) -> str:
    out = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if len(ln) < 25:
            continue
        low = ln.lower()
        if len(ln) < 200 and any(b in low for b in BOILERPLATE):
            continue
        out.append(ln)
    return "\n".join(out)


def count(rx: re.Pattern, text: str) -> int:
    return len(rx.findall(text or ""))

# =========================
# DISCOVERY BACKENDS
# =========================

Candidate = Dict[str, str]


def make_candidate(url: str, backend: str, query: str = "", title: str = "", date_hint: str = "",
                   outlet: Optional[Outlet] = None) -> Candidate:
    o = outlet or outlet_for(url)
    region, lang = (o.region, o.lang) if o else region_for_unknown(url)
    return {
        "url": canon_url(url), "title": title or "", "date_hint": date_hint or "",
        "outlet_code": o.code if o else "", "region": region, "language": lang,
        "backend": backend, "query": query,
    }


def in_range(d: Optional[date], start: date, end: date) -> bool:
    return d is None or start <= d <= end


# --- Yle -------------------------------------------------------------------

def discover_yle(http: Http, start: date, end: date, regions: set) -> List[Candidate]:
    langs = []
    if "Finlandssvensk" in regions or "Åland" in regions:
        langs.append("sv")  # Svenska Yle includes Yle Åland
    if "Finland" in regions:
        langs.append("fi")
    out: List[Candidate] = []
    for lang in langs:
        for q in QUERIES[lang]:
            log(f"  [yle/{lang}] {q}")
            offset, n_query = 0, 0
            while offset < YLE_MAX_PER_QUERY:
                params = {
                    "app_id": YLE_APP_ID, "app_key": YLE_APP_KEY, "query": q,
                    "type": "article", "language": lang, "offset": offset, "limit": YLE_PAGE_SIZE,
                }
                r = http.get(YLE_SEARCH_URL, params=params, check_robots=False)
                if r is None:
                    log("    Yle search failed (key rotated or blocked?); skipping")
                    break
                try:
                    data = r.json()
                except ValueError:
                    break
                items = data.get("data") or []
                if not items:
                    break
                older_than_start = 0
                for it in items:
                    url = it.get("url")
                    if isinstance(url, dict):
                        url = url.get("full") or url.get("short")
                    if not url:
                        continue
                    pub = it.get("datePublished") or it.get("published") or ""
                    d = parse_date(pub)
                    if d and d < start:
                        older_than_start += 1
                    if not in_range(d, start, end):
                        continue
                    title = it.get("headline") or it.get("title") or ""
                    if isinstance(title, dict):
                        title = title.get("full") or ""
                    out.append(make_candidate(url, f"yle_{lang}", q, title, pub))
                    n_query += 1
                offset += len(items)
                # Results are relevance-sorted, so we cannot stop on the first old item;
                # stop when a whole page is out of range.
                if older_than_start == len(items) or len(items) < YLE_PAGE_SIZE:
                    break
            log(f"    → {n_query} in range")
    return out


# --- WordPress REST --------------------------------------------------------

def discover_wordpress(http: Http, outlets: List[Outlet], start: date, end: date) -> List[Candidate]:
    out: List[Candidate] = []
    for o in outlets:
        base = f"https://{'www.' if o.domain.count('.') == 1 else ''}{o.domain}"
        probe = http.get(f"{base}/wp-json/wp/v2/posts", params={"per_page": 1, "_fields": "id"})
        if probe is None or not probe.text.lstrip().startswith("["):
            continue
        log(f"  [wp] {o.name}: WordPress REST available")
        for q in QUERIES[o.lang]:
            q_eff = q if not o.local else re.sub(r"\b(?:Åland|Ålands|Ahvenanmaan?)\b", "", q).strip() or q
            page = 1
            while True:
                params = {
                    "search": q_eff, "per_page": 100, "page": page,
                    "after": f"{start.isoformat()}T00:00:00", "before": f"{end.isoformat()}T23:59:59",
                    "_fields": "link,date,title",
                }
                r = http.get(f"{base}/wp-json/wp/v2/posts", params=params)
                if r is None:
                    break
                try:
                    items = r.json()
                except ValueError:
                    break
                if not isinstance(items, list) or not items:
                    break
                for it in items:
                    title = (it.get("title") or {}).get("rendered", "")
                    out.append(make_candidate(it.get("link", ""), "wp", q_eff, re.sub("<[^>]+>", "", title),
                                              it.get("date", ""), o))
                if len(items) < 100:
                    break
                page += 1
    return out


# --- Sitemaps --------------------------------------------------------------

def _xml_root(content: bytes) -> Optional[ET.Element]:
    if content[:2] == b"\x1f\x8b":
        try:
            content = gzip.decompress(content)
        except OSError:
            return None
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    for el in root.iter():  # strip namespaces
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _child_text(el: ET.Element, *path: str) -> str:
    cur = el
    for p in path:
        nxt = cur.find(p)
        if nxt is None:
            return ""
        cur = nxt
    return (cur.text or "").strip()


def sitemap_roots(http: Http, o: Outlet) -> List[str]:
    found = list(o.sitemaps)
    for host in (f"https://www.{o.domain}", f"https://{o.domain}"):
        r = http.get(host + "/robots.txt", check_robots=False)
        if r is not None:
            found += [ln.split(":", 1)[1].strip() for ln in r.text.splitlines()
                      if ln.lower().startswith("sitemap:")]
            if found:
                break
    if not found:
        found = [f"https://www.{o.domain}/sitemap.xml", f"https://www.{o.domain}/sitemap_index.xml"]
    return list(dict.fromkeys(found))


def sitemap_child_out_of_range(loc: str, lastmod: str, start: date, end: date) -> bool:
    """Skip child sitemaps clearly outside the window (by lastmod or a date in the URL)."""
    lm = parse_date(lastmod)
    if lm and lm < start:
        return True  # nothing in it was touched since before the window
    m = re.search(r"(?<!\d)(20[12]\d)(?:[-_/]?(0[1-9]|1[0-2]))?(?:[-_/]?\d{2})?(?!\d)", urlparse(loc).path)
    if m:
        y = int(m.group(1))
        mo = int(m.group(2)) if m.group(2) and 1 <= int(m.group(2)) <= 12 else None
        if y < start.year or y > end.year:
            return True
        if mo and (date(y, mo, 28) < start or date(y, mo, 1) > end):
            return True
    return False


def discover_sitemaps(http: Http, outlets: List[Outlet], start: date, end: date,
                      include_unslugged: bool) -> List[Candidate]:
    out: List[Candidate] = []
    for o in outlets:
        log(f"  [sitemap] {o.name}")
        queue = sitemap_roots(http, o)
        seen, n_files, n_hits, n_unslugged = set(), 0, 0, 0
        while queue and n_files < SITEMAP_MAX_FILES:
            sm = queue.pop(0)
            if sm in seen:
                continue
            seen.add(sm)
            r = http.get(sm)
            n_files += 1
            if r is None:
                continue
            root = _xml_root(r.content)
            if root is None:
                continue
            if root.tag == "sitemapindex":
                for s in root.findall("sitemap"):
                    loc, lm = _child_text(s, "loc"), _child_text(s, "lastmod")
                    if loc and not sitemap_child_out_of_range(loc, lm, start, end):
                        queue.append(loc)
                continue
            for u in root.findall("url"):
                loc = _child_text(u, "loc")
                if not loc:
                    continue
                news_title = _child_text(u, "news", "title")
                pub = _child_text(u, "news", "publication_date")
                lastmod = _child_text(u, "lastmod")
                d = parse_date(pub) or date_from_url(loc)
                if d and not in_range(d, start, end):
                    continue
                lm = parse_date(lastmod)
                if not d and lm and lm < start:
                    continue
                toks = slug_tokens(loc, news_title)
                words = [t for t in toks if t.isalpha() and len(t) > 3]
                if o.local:
                    hit = tokens_match(toks, SLUG_TOPIC)
                else:
                    hit = tokens_match(toks, SLUG_ALAND)
                if not hit and len(words) < 3 and include_unslugged:
                    hit = True
                    n_unslugged += 1
                if hit:
                    out.append(make_candidate(loc, "sitemap", "", news_title,
                                              pub or (d.isoformat() if d else lastmod), o))
                    n_hits += 1
        log(f"    → {n_files} sitemap files, {n_hits} candidates"
            + (f" ({n_unslugged} without informative slug)" if n_unslugged else ""))
        if n_files >= SITEMAP_MAX_FILES:
            log(f"    ⚠ hit SITEMAP_MAX_FILES={SITEMAP_MAX_FILES}; raise it for full coverage")
    return out


# --- GDELT -----------------------------------------------------------------

def discover_gdelt(http: Http, start: date, end: date, regions: set) -> List[Candidate]:
    window_start = max(start, date.today() - timedelta(days=GDELT_WINDOW_DAYS))
    if window_start > end:
        log("  [gdelt] requested window lies entirely outside GDELT's ~3-month search window; skipping")
        return []
    if window_start > start:
        log(f"  [gdelt] NB: GDELT only searches ~{GDELT_WINDOW_DAYS} days back; using {window_start}–{end}")
    aland = "(Åland OR Ahvenanmaa OR Ahvenanmaan OR Mariehamn OR Maarianhamina OR \"Aland Islands\")"
    topic = ("(demilitarisering OR demilitariserat OR demilitarisointi OR neutralisering OR Nato "
             "OR försvar OR puolustus OR konsulat OR konsulaatti OR militär OR säkerhet)")
    countries = []
    if regions & {"Åland", "Finlandssvensk", "Finland"}:
        countries.append("Finland")
    if "Sverige" in regions:
        countries.append("Sweden")
    out: List[Candidate] = []
    for c in countries:
        q = f"{aland} {topic} sourcecountry:{c}"
        log(f"  [gdelt] {q}")
        params = {
            "query": q, "mode": "ArtList", "format": "json", "maxrecords": 250, "sort": "DateDesc",
            "startdatetime": window_start.strftime("%Y%m%d") + "000000",
            "enddatetime": end.strftime("%Y%m%d") + "235959",
        }
        # GDELT returns at most 250 per call and has no offset parameter, so walk
        # backwards in time by moving enddatetime to the oldest seen date.
        seen_oldest = None
        for _ in range(40):
            r = http.get(GDELT_ENDPOINT, params=params, check_robots=False)
            if r is None or not r.text.lstrip().startswith("{"):
                break
            arts = r.json().get("articles") or []
            for a in arts:
                if a.get("url"):
                    out.append(make_candidate(a["url"], "gdelt", q, a.get("title", ""), a.get("seendate", "")))
            if len(arts) < 250:
                break
            oldest = min(a.get("seendate", "") for a in arts)
            if not oldest or oldest == seen_oldest:
                break
            seen_oldest = oldest
            params["enddatetime"] = re.sub(r"\D", "", oldest)[:14]
    log(f"    → {len(out)} GDELT hits")
    return out


# --- Manual URL list -------------------------------------------------------

def discover_urls_file(path: Path) -> List[Candidate]:
    out: List[Candidate] = []
    text = path.read_text(encoding="utf-8-sig")
    for m in re.finditer(r"https?://[^\s\"',;<>]+", text):
        out.append(make_candidate(m.group(0), "manual", path.name))
    log(f"  [urls] {len(out)} URLs from {path}")
    return out

# =========================
# SCRAPING
# =========================

def extract(http: Http, url: str) -> dict:
    r = http.get(url)
    if r is None:
        return {"status": "fetch_failed"}
    html = r.text
    res = {"status": "ok", "final_url": r.url, "text": "", "title": "", "date": "", "author": "",
           "description": "", "categories": "", "sitename": ""}
    if trafilatura is None:
        res["status"] = "no_trafilatura"
        return res
    kwargs = dict(url=url, include_comments=False, include_tables=False, favor_recall=True)
    try:
        try:
            doc = trafilatura.bare_extraction(html, with_metadata=True, **kwargs)
        except TypeError:  # older trafilatura without with_metadata
            doc = trafilatura.bare_extraction(html, **kwargs)
    except Exception as e:  # trafilatura can raise on odd markup
        return {"status": f"extract_error:{type(e).__name__}"}
    if doc is None:
        res["status"] = "extract_empty"
        return res
    d = doc.as_dict() if hasattr(doc, "as_dict") else dict(doc)
    for k in ("text", "title", "date", "author", "description", "sitename"):
        res[k] = d.get(k) or ""
    cats = d.get("categories") or ""
    res["categories"] = ", ".join(cats) if isinstance(cats, list) else str(cats)
    return res


def load_cache(path: Path) -> Dict[str, dict]:
    cache: Dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for ln in f:
                try:
                    rec = json.loads(ln)
                    cache[rec["url"]] = rec
                except (ValueError, KeyError):
                    continue
    return cache

# =========================
# CODING
# =========================

def code_article(cand: Candidate, ext: dict, start: date, end: date) -> Tuple[str, dict]:
    """Return (bucket, row) where bucket is kept | stub | rejected."""
    url = cand["url"]
    o = outlet_for(url)
    title = ext.get("title") or cand.get("title") or ""
    lead = ext.get("description") or ""
    full_text = ext.get("text") or ""
    body = clean_text(full_text)
    blob = "\n".join([title, lead, body])

    d = parse_date(ext.get("date")) or parse_date(cand.get("date_hint")) or date_from_url(url)
    source = o.name if o else (ext.get("sitename") or host_of(url))
    code = o.code if o else source_code_fallback(source)

    flags = {k: int(bool(rx.search(blob))) for k, rx in CODE_RE.items()}
    aland_body = count(CODE_RE["cat_ALAND"], body)
    aland_title = count(CODE_RE["cat_ALAND"], title + " " + lead)
    topic_hits = count(CODE_RE["cat_DEMIL"], blob) + count(CODE_RE["cat_NEUTR"], blob) + count(TREATY_RE, blob)
    security_hits = count(SECURITY_RE, blob) + sum(count(CODE_RE[c], blob) for c in SECURITY_CATS)
    quality = "empty" if not body else ("thin" if len(body) < THIN_TEXT_LEN else "ok")

    local = bool(o and o.local)
    has_aland = local or aland_title > 0 or aland_body >= 1
    if has_aland and topic_hits > 0:
        tier = "core"
    elif has_aland and security_hits > 0 and (local or aland_title > 0 or aland_body >= MIN_ALAND_MENTIONS):
        tier = "context"
    else:
        tier = ""

    notes = []
    if not d:
        notes.append("datum saknas")
    if quality != "ok":
        notes.append("tunn text: betalvägg? hämta via Retriever")
    if flags["cat_NEUTR"] and not flags["cat_ALAND"]:
        notes.append("NEUTR utan Åland: kontrollera betydelse")

    row = {
        "id": "",  # assigned later
        "Date": ext.get("date") or cand.get("date_hint") or "",
        "date_iso": d.isoformat() if d else "",
        "title": title, "url": url, "source": source, "source_code": code,
        "region": (o.region if o else cand.get("region", "")),
        "language": (o.lang if o else cand.get("language", "")),
        "section": ext.get("categories", ""), "byline": ext.get("author", ""),
        "lead": lead, "full_text": full_text, "word_count": len(full_text.split()) if full_text else "",
        "seeds": f"{cand.get('backend', '')}:{cand.get('query', '')}".rstrip(":"),
        "codes": ";".join(k for k, v in flags.items() if v),
        "relevance_tier": tier, "aland_mentions": aland_body, "aland_in_title": aland_title,
        "topic_hits": topic_hits, "security_hits": security_hits,
        "scrape_quality": quality, "notes": "; ".join(notes),
        **flags,
    }

    if d and not (start <= d <= end):
        row["notes"] = "utanför datumintervall"
        return "rejected", row
    if ext.get("status") != "ok" or quality != "ok":
        # Paywalled or unreachable: keep as a lead if title/lead/URL point to the topic.
        toks = slug_tokens(url, title + " " + lead)
        if tier or (tokens_match(toks, SLUG_TOPIC) and (local or tokens_match(toks, SLUG_ALAND))):
            return "stub", row
        row["notes"] = f"{ext.get('status')}; {row['notes']}".strip("; ")
        return "rejected", row
    return ("kept" if tier else "rejected"), row


def assign_ids(rows: List[dict]) -> None:
    used: Dict[str, int] = {}
    for r in sorted(rows, key=lambda r: (r["date_iso"], r["source_code"], r["title"])):
        ymd = (r["date_iso"] or "00000000").replace("-", "")
        base = f"{ymd}-{r['source_code']}-{make_slug(r['title'])}"
        n = used.get(base, 0)
        r["id"] = base if n == 0 else f"{base}-{n:02d}"
        used[base] = n + 1

# =========================
# OUTPUT
# =========================

def write_csv(rows: List[dict], path: Path, cols: List[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_ALL, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    log(f"  wrote {path} ({len(rows)} rows)")


def write_template(rows: List[dict], path: Path) -> None:
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "Header": r["title"], "Stance": "", "Actor": "", "Occupation": "",
            "Country": r["region"], "Date": r["date_iso"], "Outlet": r["source"], "url": r["url"],
            "relevance_tier": r["relevance_tier"], "codes": r["codes"],
        })
    write_csv(out, path, list(out[0].keys()) if out else ["id"])

# =========================
# MAIN
# =========================

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=DEFAULT_END)
    ap.add_argument("--regions", nargs="+", default=list(REGION_KEYS), choices=list(REGION_KEYS))
    ap.add_argument("--backends", nargs="+", default=["yle", "wp", "sitemap", "gdelt"],
                    choices=["yle", "wp", "sitemap", "gdelt", "urls"])
    ap.add_argument("--outlets", nargs="+", help="limit to these source codes, e.g. NYAN AR HBL")
    ap.add_argument("--urls-file", type=Path, help="text/CSV file with extra URLs (adds the 'urls' backend)")
    ap.add_argument("--outdir", type=Path, default=Path("output"))
    ap.add_argument("--discover-only", action="store_true")
    ap.add_argument("--recode", action="store_true", help="re-code cached articles; no network")
    ap.add_argument("--include-unslugged", action="store_true",
                    help="sitemaps: also scrape URLs whose slug has no words (can be many)")
    ap.add_argument("--max-scrape", type=int, default=0, help="stop after N new fetches (0 = no limit)")
    ap.add_argument("--user-agent", default=USER_AGENT)
    ap.add_argument("--ignore-robots", action="store_true",
                    help="do not check robots.txt (only where you have permission)")
    args = ap.parse_args()

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    regions = {REGION_KEYS[r] for r in args.regions}
    outlets = [o for o in OUTLETS if o.region in regions
               and (not args.outlets or o.code in {c.upper() for c in args.outlets})]
    args.outdir.mkdir(parents=True, exist_ok=True)
    cand_path = args.outdir / "candidates.csv"
    cache_path = args.outdir / "scrape_cache.jsonl"
    http = Http(args.user_agent, respect_robots=not args.ignore_robots)

    log(f"Åland media scraper | {start} → {end} | regions: {', '.join(sorted(regions))}")

    # ---- 1. discovery ----
    candidates: List[Candidate] = []
    if args.recode:
        if cand_path.exists():
            with cand_path.open(encoding="utf-8-sig") as f:
                candidates = list(csv.DictReader(f))
    else:
        backends = set(args.backends) | ({"urls"} if args.urls_file else set())
        log("\n🔎 Discovering candidates…")
        if "yle" in backends:
            candidates += discover_yle(http, start, end, regions)
        if "wp" in backends:
            candidates += discover_wordpress(http, [o for o in outlets if "yle.fi" not in o.domain], start, end)
        if "sitemap" in backends:
            candidates += discover_sitemaps(http, [o for o in outlets if "yle.fi" not in o.domain],
                                            start, end, args.include_unslugged)
        if "gdelt" in backends:
            candidates += discover_gdelt(http, start, end, regions)
        if "urls" in backends and args.urls_file:
            candidates += discover_urls_file(args.urls_file)

        # Keep only the requested regions; merge duplicates, keeping all seeds.
        merged: Dict[str, Candidate] = {}
        for c in candidates:
            if c["region"] not in regions and c["backend"] != "manual":
                continue
            if args.outlets and c["outlet_code"] not in {x.upper() for x in args.outlets} and c["backend"] != "manual":
                continue
            prev = merged.get(c["url"])
            if prev:
                prev["backend"] = ";".join(sorted(set(prev["backend"].split(";")) | {c["backend"]}))
                if c["query"] and c["query"] not in prev["query"]:
                    prev["query"] = (prev["query"] + " | " + c["query"]).strip(" |")
                prev["title"] = prev["title"] or c["title"]
                prev["date_hint"] = prev["date_hint"] or c["date_hint"]
            else:
                merged[c["url"]] = dict(c)
        candidates = list(merged.values())
        write_csv(candidates, cand_path, CANDIDATE_COLS)

    log(f"\n✅ {len(candidates)} unique candidates")
    if args.discover_only:
        return
    if trafilatura is None and not args.recode:
        sys.exit("trafilatura is not installed: pip install trafilatura")

    # ---- 2. scrape ----
    cache = load_cache(cache_path)
    todo = [c for c in candidates if c["url"] not in cache]
    log(f"\n📰 Scraping {len(todo)} new URLs ({len(cache)} cached)…")
    if not args.recode:
        with cache_path.open("a", encoding="utf-8") as cf:
            for i, c in enumerate(todo, 1):
                if args.max_scrape and i > args.max_scrape:
                    log(f"  reached --max-scrape={args.max_scrape}; re-run to continue")
                    break
                log(f"  [{i}/{len(todo)}] {c['url'][:100]}")
                ext = extract(http, c["url"])
                ext["url"] = c["url"]
                cache[c["url"]] = ext
                cf.write(json.dumps(ext, ensure_ascii=False) + "\n")
                cf.flush()

    # ---- 3. code ----
    kept, stubs, rejected = [], [], []
    seen_final = set()
    for c in candidates:
        ext = cache.get(c["url"])
        if ext is None:
            continue
        final = canon_url(ext.get("final_url") or c["url"])
        if final in seen_final:
            continue  # redirect duplicates
        seen_final.add(final)
        bucket, row = code_article(c, ext, start, end)
        {"kept": kept, "stub": stubs, "rejected": rejected}[bucket].append(row)

    for rows in (kept, stubs):
        assign_ids(rows)
    kept.sort(key=lambda r: r["id"])
    stubs.sort(key=lambda r: r["id"])

    # ---- 4. write ----
    tag = f"{start.year}_{end.isoformat()}"
    log("\n💾 Writing…")
    write_csv(kept, args.outdir / f"aland_media_{tag}_coded.csv", ARTICLE_COLS)
    write_template(kept, args.outdir / f"aland_media_{tag}_coding_template.csv")
    write_csv(stubs, args.outdir / f"aland_media_{tag}_stubs.csv",
              [c for c in ARTICLE_COLS if c != "full_text"])
    write_csv(rejected, args.outdir / f"aland_media_{tag}_rejected.csv",
              [c for c in ARTICLE_COLS if c not in ("full_text", "lead")])

    log(f"\n📊 kept={len(kept)} (core={sum(r['relevance_tier'] == 'core' for r in kept)}, "
        f"context={sum(r['relevance_tier'] == 'context' for r in kept)}) | "
        f"stubs={len(stubs)} | rejected={len(rejected)}")
    by_region: Dict[str, int] = {}
    for r in kept:
        by_region[r["region"] or "?"] = by_region.get(r["region"] or "?", 0) + 1
    for k, v in sorted(by_region.items()):
        log(f"   {k:<16}{v}")
    if kept:
        log("\n   flag counts:")
        for k in FLAG_COLS:
            log(f"   {k:<12}{sum(r[k] for r in kept)}")
    log("\n✅ Done.")


if __name__ == "__main__":
    main()
