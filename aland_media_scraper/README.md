# Åland media scraper (2024 to present)

Collects and codes news articles on Åland's demilitarisation and neutralisation from four media spheres: Åland, Finlandssvensk, Finland (Finnish-language) and Sverige. The output follows the *Ålands Media Codebook-lite*: one row per article, `id = YYYYMMDD-SRC-slug[-nn]` and the `cat_*` flags.

## Run

```
pip install -r requirements.txt
python aland_media_scraper.py                      # everything, 2024-01-01 to today
python aland_media_scraper.py --regions aland finlandssvensk
python aland_media_scraper.py --outlets NYAN AR HBL --backends sitemap wp
python aland_media_scraper.py --urls-file retriever_urls.txt   # add URLs by hand
python aland_media_scraper.py --recode             # re-code from cache without fetching
```

A full run is slow, since requests to each host are spaced 1.5 s apart. It is resumable: fetched articles are cached in `output/scrape_cache.jsonl`, so re-runs skip URLs already fetched. Try `--max-scrape 200` on a first run.

## Discovery backends

| backend | reach | notes |
|---|---|---|
| `yle` | Svenska Yle (incl. Yle Åland) + Yle, full archive | uses the public key from yle.fi's search page; update `YLE_APP_KEY` if it stops working |
| `wp` | outlets running WordPress | probed automatically; silently skipped if the outlet is not WP |
| `sitemap` | all outlets | Åland outlets are filtered by topic words in the URL slug, all other outlets by Åland words |
| `gdelt` | Finland + Sweden | **GDELT DOC only searches the last ~3 months**, so it cannot reach 2024 (nor 2022–2024 in the Sweden script) |
| `urls` | anything | URLs from Retriever, omvärldsbevakning, tips |

## Outputs (`output/`)

- `aland_media_<range>_coded.csv`: kept articles with full text and flags. `relevance_tier` is `core` (Åland + demilitarisation/neutralisation/treaty terms) or `context` (Åland + security terms such as NATO, Russia, preparedness or defence)
- `aland_media_<range>_coding_template.csv`: Header/Stance/Actor/Occupation for manual coding
- `aland_media_<range>_stubs.csv`: paywalled/teaser articles that look relevant; fetch them via Retriever
- `aland_media_<range>_rejected.csv`: audit trail
- `candidates.csv`: everything discovered, before scraping

## Changes to the codebook regexes

The Swedish baselines follow the codebook with three repairs: `cat_VPLIKT` and `cat_IDENT` get the missing `*`, and `cat_RUSSIA` gets `.{0,40}` between *konsulat* and *ryss*. Finnish and English equivalents have been added (e.g. *demilitarisointi*, *Ahvenanmaa*, *Venäjä*, *asevelvollisuus*, *varautuminen*). `cat_ALAND` now also matches inflected forms, *Ahvenanmaa*, *Mariehamn* and *Maarianhamina*.

## Limitations

- Paywalls (ÅT, HBL, HS, DN, SvD and others) yield teasers only. These end up in `stubs`, so use Retriever/Mediearkivet for the full text.
- Ålandstidningen is best taken from Retriever, as before; add its URLs via `--urls-file`.
- Sitemap filtering depends on informative URL slugs. Where an outlet uses numeric URLs, use `--include-unslugged` (gives many more fetches).
- robots.txt is respected by default.
