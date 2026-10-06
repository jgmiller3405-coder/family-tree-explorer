"""Parse the Ancestry GEDCOM into ancestry-site/data.json (with cached geocoding)."""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

GED = Path.home() / "Ancestry" / "Mill A Family Tree.ged"
OUT = Path(__file__).parent
CACHE = OUT / "geocache.json"

COUNTRY = {
    "usa": "United States", "united states": "United States", "united states of america": "United States",
    "us": "United States", "england": "England", "scotland": "Scotland", "wales": "Wales",
    "united kingdom": "United Kingdom", "great britain": "United Kingdom", "uk": "United Kingdom",
    "deutschland": "Germany", "germany": "Germany", "suisse": "Switzerland", "switzerland": "Switzerland",
    "ireland": "Ireland", "france": "France", "netherlands": "Netherlands", "canada": "Canada",
}
US_STATES = set(
    "Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia Hawaii Idaho "
    "Illinois Indiana Iowa Kansas Kentucky Louisiana Maine Maryland Massachusetts Michigan Minnesota Mississippi "
    "Missouri Montana Nebraska Nevada Ohio Oklahoma Oregon Pennsylvania Tennessee Texas Utah Vermont Virginia "
    "Washington Wisconsin Wyoming".split()
) | {"New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
     "Rhode Island", "South Carolina", "South Dakota", "West Virginia", "District of Columbia"}
ABBR = {"NH": "New Hampshire", "MA": "Massachusetts", "CT": "Connecticut", "NY": "New York", "VA": "Virginia",
        "NC": "North Carolina", "SC": "South Carolina", "PA": "Pennsylvania", "NJ": "New Jersey", "MD": "Maryland",
        "OH": "Ohio", "IN": "Indiana", "KS": "Kansas", "GA": "Georgia", "KY": "Kentucky", "TN": "Tennessee"}


def parse_records(text):
    recs, cur, stack = [], None, []
    for line in text.splitlines():
        m = re.match(r"(\d+) (@\S+@ )?(\S+)(?: (.*))?$", line)
        if not m:
            continue
        lvl, xref, tag, val = int(m[1]), m[2], m[3], (m[4] or "")
        if lvl == 0:
            cur = {"id": xref.strip().strip("@") if xref else None, "type": tag, "kids": []}
            recs.append(cur)
            stack = [cur]
        elif cur is not None:
            node = {"tag": tag, "val": val, "kids": []}
            del stack[lvl:]
            stack[-1]["kids"].append(node)
            stack.append(node)
    return recs


def sub(node, tag):
    return next((k for k in node["kids"] if k["tag"] == tag), None)


def subval(node, *path):
    for t in path:
        node = sub(node, t) if node else None
    return node["val"] if node else None


def find(node, tag):
    """First value of `tag` anywhere beneath node."""
    for k in node["kids"]:
        if k["tag"] == tag:
            return k["val"]
        v = find(k, tag)
        if v:
            return v
    return None


def year(s):
    m = re.findall(r"\b(1[0-9]{3}|20[0-2][0-9])\b", s or "")
    return int(m[0]) if m else None


def parse_place(p):
    if not p:
        return None
    parts = [x.strip() for x in re.sub(r"^of ", "", p.strip()).split(",") if x.strip()]
    if not parts:
        return None
    country = state = None
    if parts[-1].lower() in COUNTRY:
        country = COUNTRY[parts.pop().lower()]
        if country == "United Kingdom" and parts and parts[-1].lower() in COUNTRY:
            country = COUNTRY[parts.pop().lower()]
    for i in range(len(parts) - 1, -1, -1):
        s = ABBR.get(parts[i], parts[i])
        if s in US_STATES:
            state, country = s, country or "United States"
            parts = parts[:i]
            break
    if country is None:
        country = parts[-1] if len(parts) > 1 else "Unknown"
    region = state or (parts[-1] if country in ("England", "Wales", "Scotland") and len(parts) > 1 else None)
    city = parts[0] if parts and parts[0] != region else None
    q = ", ".join(x for x in (city, region, country) if x and x != "Unknown")
    return {"raw": p, "q": q, "city": city, "region": region, "country": country}


CC = {"United States": "US", "England": "GB", "Scotland": "GB", "Wales": "GB", "United Kingdom": "GB", "Germany": "DE",
      "Switzerland": "CH", "Ireland": "IE", "France": "FR", "Netherlands": "NL", "Canada": "CA"}
GB_ADMIN = {"England": "ENG", "Scotland": "SCT", "Wales": "WLS"}


def make_resolver():
    """Offline geocoder: cached Nominatim hits, then geonamescache cities, then state/country centroids."""
    import geonamescache
    from collections import defaultdict
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    cities = defaultdict(list)
    regions, countries, state_names = defaultdict(list), defaultdict(list), geonamescache.GeonamesCache().get_us_states()
    abbr = {v["name"]: k for k, v in state_names.items()}
    for c in geonamescache.GeonamesCache().get_cities().values():
        pt = (c["latitude"], c["longitude"], c["population"])
        cities[(c["name"].lower(), c["countrycode"])].append((c["admin1code"], pt))
        regions[(c["countrycode"], c["admin1code"])].append(pt)
        countries[c["countrycode"]].append(pt)
    mean = lambda pts: [sum(x[0] for x in pts) / len(pts), sum(x[1] for x in pts) / len(pts)]

    def resolve(pl):
        if cache.get(pl["q"]):
            return cache[pl["q"]]
        cc = CC.get(pl["country"])
        if not cc:
            return None
        admin = abbr.get(pl["region"]) if cc == "US" else GB_ADMIN.get(pl["country"])
        if pl["city"]:
            hits = cities.get((pl["city"].lower(), cc), [])
            hits = [h for h in hits if admin is None or h[0] == admin] or ([] if admin and cc == "US" else hits)
            if hits:
                best = max(hits, key=lambda h: h[1][2])[1]
                return [best[0], best[1]]
        if admin and regions.get((cc, admin)):
            return mean(regions[(cc, admin)])
        return mean(countries[cc]) if countries.get(cc) else None
    return resolve


def main():
    recs = parse_records(GED.read_text(encoding="utf-8-sig"))
    people, fams, media = {}, {}, {}
    for r in recs:
        if r["type"] == "OBJE":
            file_ = sub(r, "FILE") or {"kids": []}
            meta = subval(r, "_META") or ""
            cem = re.search(r"<cemetery>([^<]+)</cemetery>", meta)
            media[r["id"]] = {
                "type": find(file_, "_MTYPE") or "other",
                "title": subval(file_, "TITL") or "",
                "desc": (subval(r, "_DSCR") or "").strip(),
                "cem": cem.group(1).strip() if cem else "",
            }
    for r in recs:
        if r["type"] == "INDI":
            nm = subval(r, "NAME") or ""
            famc = subval(r, "FAMC")
            refs = [k["val"].strip("@") for k in r["kids"] if k["tag"] == "OBJE"]
            people[r["id"]] = {
                "id": r["id"], "name": re.sub(r"\s+", " ", nm.replace("/", "")).strip() or "Unknown",
                "surname": (subval(r, "NAME", "SURN") or "").strip(), "sex": subval(r, "SEX") or "U",
                "by": year(subval(r, "BIRT", "DATE")), "dy": year(subval(r, "DEAT", "DATE")),
                "bp": parse_place(subval(r, "BIRT", "PLAC")), "dp": parse_place(subval(r, "DEAT", "PLAC")),
                "bdate": subval(r, "BIRT", "DATE"), "ddate": subval(r, "DEAT", "DATE"),
                "famc": famc.strip("@") if famc else None,
                "fams": [k["val"].strip("@") for k in r["kids"] if k["tag"] == "FAMS"],
                "deatTag": sub(r, "DEAT") is not None,
                "refs": refs,
            }
        elif r["type"] == "FAM":
            fams[r["id"]] = {
                "h": (subval(r, "HUSB") or "").strip("@") or None, "w": (subval(r, "WIFE") or "").strip("@") or None,
                "c": [k["val"].strip("@") for k in r["kids"] if k["tag"] == "CHIL"],
            }
    root = next(p["id"] for p in people.values() if p["name"] == "Jason Miller" and p["by"] == 2005)

    # generation (ancestors only) and paternal/maternal side
    gen, q = {root: 0}, [root]
    while q:
        x = q.pop(0)
        f = fams.get(people[x]["famc"])
        for par in ((f["h"], f["w"]) if f else ()):
            if par in people and par not in gen:
                gen[par] = gen[x] + 1
                q.append(par)
    side = {}

    def mark(pid, s):
        st = [pid]
        while st:
            a = st.pop()
            if a in side or a not in people:
                continue
            side[a] = s
            ff = fams.get(people[a]["famc"])
            if ff:
                st += [ff["h"], ff["w"]]

    f = fams.get(people[root]["famc"])
    if f:
        mark(f["h"], "Paternal")
        mark(f["w"], "Maternal")

    for p in people.values():
        # keep only records with something to show; portraits with no text are just counted
        items = [media[x] for x in p.pop("refs") if x in media]
        p["portraits"] = sum(1 for m in items if m["type"] == "portrait" and not (m["title"] or m["desc"]))
        p["media"] = [m for m in items if m["title"] or m["desc"] or m["cem"] or m["type"] != "portrait"]
        p["military"] = any(re.search(r"veteran|war|soldier|militia", (m["title"] + " " + m["desc"]).lower()) for m in p["media"])
    for pid, p in people.items():
        p["gen"], p["side"] = gen.get(pid), side.get(pid)
        p["nchild"] = sum(len(fams[s]["c"]) for s in p["fams"] if s in fams)
        p["age"] = p["dy"] - p["by"] if p["dy"] and p["by"] and 0 <= p["dy"] - p["by"] < 110 else None
        # privacy: anyone born after 1925 with no recorded death is treated as living and redacted
        p["living"] = p["dy"] is None and not p["deatTag"] and (p["by"] is None or p["by"] > 1925)
        del p["deatTag"]

    resolve = make_resolver()
    for p in people.values():
        if p["living"]:
            p.update(name="Living", surname="", bdate=None, ddate=None, bp=None, dp=None, by=None, dy=None, military=False, media=[], portraits=0)
            continue
        for k in ("bp", "dp"):
            if p[k]:
                p[k]["ll"] = resolve(p[k])
    blob = json.dumps({"root": root, "people": people, "fams": fams}, separators=(",", ":"))
    (OUT / "data.json").write_text(blob)
    (OUT / "data.js").write_text("const DATA=" + blob + ";\n")
    print(len(people), "people,", len(fams), "families; living redacted:", sum(p["living"] for p in people.values()))


if __name__ == "__main__":
    main()
