# Miller Family Tree Explorer

An interactive, static website for exploring a family tree exported from Ancestry as a GEDCOM file (1,108 people, 656 families).

## Viewing the site

```
git clone https://github.com/jgmiller3405-coder/family-tree-explorer
cd family-tree-explorer
python -m http.server 8000
```

Open http://localhost:8000. Opening `index.html` directly also works. The map tiles, D3 and Leaflet load from CDNs, so you need an internet connection.

## Tabs

| Tab | What it shows |
| --- | --- |
| Pedigree | Ancestors of the focus person, laid out left to right. Click a person for details and to refocus. |
| Descendants | A collapsible tree of descendants. Click a person to expand or collapse. |
| Fan chart | Ancestors in concentric rings, with the paternal line on one half and the maternal line on the other. |
| Map | Birth and death places, with birth-to-death lines, a year slider with play, and an optional layer of cemetery and headstone records. |
| Timeline | Lifespan bars sorted by birth year. |
| Stats | Countries, states, cities, surnames, centuries, age at death, family size and migration between countries. |

## Filters

Filters apply to every tab. Non-matching people are dimmed, or hidden with "Hide non-matches".

- Place type (birth, death or either), country, state or region, and city
- Surname, sex, and paternal or maternal line
- Birth-year range and age-at-death range
- Military note, and record type (headstone, document, portrait, story, or cemetery mentioned)
- Name search, which also covers the text of attached records
- Tree depth

"Color by" works on every tab: birth country, state, line, century, sex, generation or age at death.

## Data

The GEDCOM includes metadata for 502 media items (type, title, description, cemetery) but not the image files. The person panel lists these records for each person.

The GEDCOM has no occupation or residence fields, so job and "lived" filters are not available. Re-export from Ancestry with that data and extend `build_data.py` to add them.

- Birth and death places are geocoded offline with `geonamescache`. Cities with about 15,000 or more people are matched exactly. Smaller places fall back to the state or region center, then the country center, so some map points are approximate.
- Anyone born after 1925 with no recorded death is treated as living and shown as "Living", with names, dates and places removed.

## Rebuilding the data

`build_data.py` reads `~/Ancestry/Mill A Family Tree.ged` and writes `data.js`, which the page loads. It needs `geonamescache`, so run it from the `fda-python` project with `uv run python ancestry-site/build_data.py`. `data.js` contains personal information about the people in the tree, so keep this repository private.
