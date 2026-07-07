#!/usr/bin/env python3
"""Scrape the Warsaw ZTM vehicle database (buses) and render a numbering grid."""

import colorsys
import hashlib
import html
import json
import re
import time
import urllib.request
from pathlib import Path

BASE = "https://www.ztm.waw.pl/baza-danych-pojazdow/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

CARRIERS = {
    "1": "MZA",
    "3": "Mobilis",
    "6": "PKS Grodzisk",
    "17": "ReloBus",
}

CACHE = Path(".cache")
ROW_RE = re.compile(r'<a\b[^>]*class="grid-row-active"[^>]*>(.*?)</a>', re.S)
CELL_RE = re.compile(r'role="cell"[^>]*>(.*?)</div>', re.S)
LAST_PAGE_RE = re.compile(r"/page/(\d+)/")


def fetch(url: str) -> str:
    key = hashlib.md5(url.encode()).hexdigest() + ".html"
    path = CACHE / key
    if path.exists():
        return path.read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8")
    CACHE.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")
    time.sleep(0.4)
    return text


def clean(cell: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", cell)).replace("­", "").strip()


def parse_rows(page_html: str):
    for block in ROW_RE.findall(page_html):
        cells = [clean(c) for c in CELL_RE.findall(block)]
        if len(cells) >= 5:
            yield {
                "number": cells[0],
                "producent": cells[1],
                "typ": cells[2],
                "carrier_full": cells[3],
                "depot": cells[4],
            }


def last_page(page_html: str) -> int:
    i = page_html.find("grid-pager")
    pager = page_html[i : i + 2000] if i >= 0 else ""
    pages = [int(n) for n in LAST_PAGE_RE.findall(pager)]
    return max(pages) if pages else 1


def scrape():
    vehicles = []
    for cid, name in CARRIERS.items():
        first = fetch(f"{BASE}?ztm_traction=1&ztm_carrier={cid}")
        total = last_page(first)
        print(f"{name}: {total} page(s)")
        for page in range(1, total + 1):
            page_html = first if page == 1 else fetch(f"{BASE}page/{page}/?ztm_traction=1&ztm_carrier={cid}")
            for v in parse_rows(page_html):
                v["carrier"] = name
                vehicles.append(v)
    return vehicles


def type_color(producent: str, typ: str) -> str:
    h = hashlib.md5(f"{producent}|{typ}".encode()).digest()
    hue = int.from_bytes(h[:2], "big") / 65535.0
    sat = 0.45 + (h[2] / 255.0) * 0.30
    light = 0.72 + (h[3] / 255.0) * 0.12
    r, g, b = colorsys.hls_to_rgb(hue, light, sat)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def build_html(vehicles) -> str:
    grid = {}
    types = {}
    for v in vehicles:
        num = v["number"]
        if not (num.isdigit() and 1000 <= int(num) <= 9999):
            continue
        n = int(num)
        grid.setdefault(n // 100, {})[n % 100] = v
        key = (v["producent"], v["typ"])
        types.setdefault(key, {"color": type_color(*key), "count": 0})
        types[key]["count"] += 1

    present = sorted(grid)
    total = sum(len(row) for row in grid.values())

    prefix_carrier = {p: next(iter(row.values()))["carrier"] for p, row in grid.items()}

    columns = []
    prev = None
    for prefix in present:
        if prev is not None and prefix - prev > 1:
            missing = prefix - prev - 1
            columns.append({"gap": missing, "range": f"{prev+1:02d}xx–{prefix-1:02d}xx"})
        columns.append({"prefix": prefix})
        prev = prefix

    def col_carrier(i):
        col = columns[i]
        if "prefix" in col:
            return prefix_carrier[col["prefix"]]
        left = prefix_carrier[columns[i - 1]["prefix"]]
        right = prefix_carrier[columns[i + 1]["prefix"]]
        return left if left == right else None

    runs = []
    for i in range(len(columns)):
        car = col_carrier(i)
        if runs and runs[-1][0] == car and car is not None:
            runs[-1][1] += 1
        else:
            runs.append([car, 1])

    group_row = ['<th class="corner cg-corner"></th>']
    for car, span in runs:
        if car is None:
            group_row.append(f'<th class="gempty" colspan="{span}"></th>')
        else:
            group_row.append(f'<th class="gcell" colspan="{span}">{car}</th>')

    prefix_row = ['<th class="corner">nr</th>']
    for col in columns:
        if "gap" in col:
            prefix_row.append(f'<th class="gapcol" title="{col["gap"]} skipped ({col["range"]})"></th>')
        else:
            prefix_row.append(f'<th class="colh">{col["prefix"]}xx</th>')

    thead = ['<tr class="grow">', *group_row, "</tr>", '<tr class="prow">', *prefix_row, "</tr>"]

    body = []
    for suffix in range(100):
        cells = [f'<th class="rowh">{suffix:02d}</th>']
        for col in columns:
            if "gap" in col:
                cells.append('<td class="gapcol"></td>')
                continue
            v = grid[col["prefix"]].get(suffix)
            if v is None:
                cells.append('<td class="empty"></td>')
            else:
                color = types[(v["producent"], v["typ"])]["color"]
                tip = html.escape(f'{v["number"]} · {v["producent"]} {v["typ"]} · {v["carrier"]} · {v["depot"]}')
                cells.append(
                    f'<td class="c" style="background:{color}" title="{tip}">{v["number"]}</td>'
                )
        body.append("<tr>" + "".join(cells) + "</tr>")

    legend = []
    for (prod, typ), meta in sorted(types.items(), key=lambda kv: -kv[1]["count"]):
        label = html.escape(f"{prod} {typ}".strip())
        legend.append(
            f'<span class="leg"><span class="sw" style="background:{meta["color"]}"></span>'
            f'{label} <span class="cnt">{meta["count"]}</span></span>'
        )

    carrier_counts = {}
    for v in vehicles:
        num = v["number"]
        if num.isdigit() and 1000 <= int(num) <= 9999:
            carrier_counts[v["carrier"]] = carrier_counts.get(v["carrier"], 0) + 1
    carrier_line = " · ".join(f"{k}: {v}" for k, v in sorted(carrier_counts.items()))

    return f"""<!DOCTYPE html>
<html lang="pl"><head><meta charset="utf-8">
<title>Numeracja autobusów WTP (ZTM Warszawa)</title>
<style>
  :root {{ font-family: -apple-system, system-ui, sans-serif; }}
  body {{ margin: 24px; color: #1b1b1b; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color: #666; font-size: 13px; margin-bottom: 3px; }}
  .sub a {{ color: #06c; }}
  .scroll {{ overflow-x: auto; border: 1px solid #ddd; border-radius: 6px; margin-top: 14px; }}
  table {{ border-collapse: collapse; font-size: 10px; }}
  th, td {{ width: 40px; height: 20px; text-align: center; box-sizing: border-box; }}
  thead th {{ position: sticky; background: #fafafa; z-index: 2; color: #555; font-weight: 600; }}
  thead .grow th {{ top: 0; height: 22px; }}
  thead .prow th {{ top: 22px; }}
  .gcell {{ background: #eef1f4; color: #333; border-bottom: 1px solid #d5d5d5;
    border-left: 2px solid #fff; border-right: 2px solid #fff; }}
  .gempty {{ background: #fafafa; border: none; }}
  .corner, .rowh {{ position: sticky; left: 0; background: #f0f0f0; font-weight: 600; z-index: 1; color: #888; }}
  thead .corner {{ z-index: 4; }}
  .cg-corner {{ top: 0; }}
  td.c {{ color: #111; border: 1px solid rgba(255,255,255,0.6); font-variant-numeric: tabular-nums; }}
  td.empty {{ background: #fcfcfc; border: 1px solid #f2f2f2; }}
  .gapcol {{ width: 4px; min-width: 4px; padding: 0;
    background: repeating-linear-gradient(45deg,#fff,#fff 3px,#f0f0f0 3px,#f0f0f0 6px); }}
  thead .gapcol {{ background: repeating-linear-gradient(45deg,#fafafa,#fafafa 3px,#e8e8e8 3px,#e8e8e8 6px); }}
  .legend {{ margin: 16px 0 4px; display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 12px; }}
  .leg {{ display: inline-flex; align-items: center; gap: 5px; }}
  .sw {{ width: 13px; height: 13px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.12); display: inline-block; }}
  .cnt {{ color: #999; }}
</style></head>
<body>
  <h1>Numeracja autobusów WTP (ZTM Warszawa)</h1>
  <div class="sub">{total} pojazdów · {carrier_line} · numery 1000–9999 · kolor = producent + typ</div>
  <div class="sub">źródło: <a href="{BASE}?ztm_traction=1">Baza danych pojazdów ZTM Warszawa</a></div>
  <div class="scroll"><table>
    <thead>{''.join(thead)}</thead>
    <tbody>{''.join(body)}</tbody>
  </table></div>
  <div class="legend">{''.join(legend)}</div>
</body></html>
"""


def main():
    vehicles = scrape()
    Path("vehicles.json").write_text(json.dumps(vehicles, ensure_ascii=False, indent=2), encoding="utf-8")
    out = build_html(vehicles)
    Path("numeracja.html").write_text(out, encoding="utf-8")
    print(f"{len(vehicles)} vehicles scraped -> numeracja.html")


if __name__ == "__main__":
    main()
