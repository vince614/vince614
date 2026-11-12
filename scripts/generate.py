#!/usr/bin/env python3
"""Génère les cartes SVG du profil (stats, langages, texte tapé) sans service tiers.

Usage : python3 scripts/generate.py <username> <dossier_sortie>
Variable d'environnement optionnelle : GITHUB_TOKEN (nécessaire pour les contributions).
"""
import json
import os
import sys
import urllib.request
from html import escape

USER = sys.argv[1] if len(sys.argv) > 1 else "vince614"
OUT = sys.argv[2] if len(sys.argv) > 2 else "dist"
TOKEN = os.environ.get("GITHUB_TOKEN", "")

BG, BORDER, TITLE, TEXT, ACCENT = "#0D1117", "#30363D", "#E100FF", "#C9D1D9", "#00D4FF"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"


def api(url, data=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch():
    user = api(f"https://api.github.com/users/{USER}")
    repos, page = [], 1
    while True:
        batch = api(f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}&type=owner")
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    own = [r for r in repos if not r["fork"]]
    langs = {}
    for r in own:
        for k, v in api(r["languages_url"]).items():
            langs[k] = langs.get(k, 0) + v
    stats = {
        "Total stars": sum(r["stargazers_count"] for r in own),
        "Public repos": user["public_repos"],
        "Followers": user["followers"],
    }
    if TOKEN:
        q = """query($login:String!){ user(login:$login){
          contributionsCollection{ totalCommitContributions restrictedContributionsCount
            contributionCalendar{ totalContributions } }
          pullRequests{ totalCount } issues{ totalCount } } }"""
        u = api("https://api.github.com/graphql", {"query": q, "variables": {"login": USER}})["data"]["user"]
        cc = u["contributionsCollection"]
        stats = {
            "Contributions (last year)": cc["contributionCalendar"]["totalContributions"],
            "Commits (last year)": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
            "Pull requests": u["pullRequests"]["totalCount"],
            "Issues": u["issues"]["totalCount"],
            **stats,
        }
    return user, stats, langs


def card(w, h, title, inner):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#7F00FF"/><stop offset=".5" stop-color="#E100FF"/><stop offset="1" stop-color="#00D4FF"/>
</linearGradient></defs>
<style>
.t{{font:600 18px {FONT};fill:url(#g)}} .l{{font:400 14px {FONT};fill:{TEXT}}} .v{{font:700 14px {FONT};fill:{ACCENT}}}
.row{{opacity:0;animation:in .6s ease-out forwards}} @keyframes in{{from{{opacity:0;transform:translateX(-10px)}}to{{opacity:1;transform:none}}}}
.bar{{transform-box:fill-box;transform:scaleX(0);animation:grow 1.2s ease-out forwards}} @keyframes grow{{to{{transform:scaleX(1)}}}}
</style>
<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="10" fill="{BG}" stroke="{BORDER}"/>
<text x="25" y="35" class="t">{escape(title)}</text>
{inner}
</svg>"""


def stats_svg(user, stats):
    rows = []
    for i, (k, v) in enumerate(stats.items()):
        y = 70 + i * 28
        rows.append(
            f'<g class="row" style="animation-delay:{0.15 * i:.2f}s">'
            f'<circle cx="32" cy="{y-5}" r="4" fill="{TITLE}"/>'
            f'<text x="45" y="{y}" class="l">{escape(k)}</text>'
            f'<text x="400" y="{y}" class="v" text-anchor="end">{v:,}</text></g>'.replace(",", " ")
            if isinstance(v, int) else ""
        )
    h = 70 + len(stats) * 28
    name = user.get("name") or USER
    return card(430, h, f"{name}'s GitHub stats", "\n".join(rows))


COLORS = {"TypeScript": "#3178C6", "JavaScript": "#F7DF1E", "PHP": "#777BB4", "CSS": "#663399",
          "HTML": "#E34C26", "Python": "#3572A5", "SCSS": "#C6538C", "Shell": "#89E051", "Vue": "#41B883"}


def langs_svg(langs, n=6):
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:n]
    x, bar = 25, []
    for k, v in top:
        w = 380 * v / total
        bar.append(f'<rect x="{x:.1f}" y="55" width="{w:.1f}" height="10" fill="{COLORS.get(k, "#8B949E")}"/>')
        x += w
    items = []
    for i, (k, v) in enumerate(top):
        cx, cy = 25 + (i % 2) * 200, 95 + (i // 2) * 26
        items.append(
            f'<g class="row" style="animation-delay:{0.15 * i:.2f}s">'
            f'<circle cx="{cx+5}" cy="{cy-5}" r="5" fill="{COLORS.get(k, "#8B949E")}"/>'
            f'<text x="{cx+16}" y="{cy}" class="l">{escape(k)} <tspan class="v">{100*v/total:.1f}%</tspan></text></g>'
        )
    h = 95 + ((len(top) + 1) // 2) * 26
    inner = ('<clipPath id="c"><rect x="25" y="55" width="380" height="10" rx="5"/></clipPath>'
             f'<g clip-path="url(#c)"><g class="bar">{"".join(bar)}</g></g>' + "".join(items))
    return card(430, h, "Most used languages", inner)


def typing_svg(lines, w=640, h=50, size=24, per=4.0):
    """Effet machine à écrire en SMIL : chaque ligne s'écrit, reste, puis s'efface."""
    T, cw = per * len(lines), size * 0.6
    parts = []
    for i, line in enumerate(lines):
        tw = len(line) * cw
        x0 = (w - tw) / 2
        a, b, c, d = (i * per) / T, (i * per + 1.6) / T, (i * per + per - 0.4) / T, (i * per + per) / T
        kt = sorted({0.0, a, b, c, d, 1.0})
        def vals(f):
            return ";".join(f(t) for t in kt)
        width = vals(lambda t: f"{tw:.1f}" if b <= t <= c else "0")
        op = vals(lambda t: "1" if a <= t < d and t != d else "0")
        keyt = ";".join(f"{t:.4f}" for t in kt)
        parts.append(f"""<clipPath id="c{i}"><rect x="{x0:.1f}" y="0" height="{h}" width="0">
<animate attributeName="width" dur="{T}s" repeatCount="indefinite" values="{width}" keyTimes="{keyt}"/></rect></clipPath>
<g clip-path="url(#c{i})" opacity="0"><animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" calcMode="discrete" values="{op}" keyTimes="{keyt}"/>
<text x="{x0:.1f}" y="{h/2+size/3:.1f}" font-family="'Fira Code',Consolas,'Courier New',monospace" font-size="{size}" font-weight="600" fill="#C86BFA">{escape(line)}</text></g>""")
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n' + "\n".join(parts) + "\n</svg>"


def main():
    os.makedirs(OUT, exist_ok=True)
    lines = ["TypeScript & Next.js enthusiast", "PHP | Symfony | Magento 2",
             "Discord bots & APIs builder", "Creator of DiscordInvites.net"]
    with open(f"{OUT}/typing.svg", "w") as f:
        f.write(typing_svg(lines))
    user, stats, langs = fetch()
    with open(f"{OUT}/stats.svg", "w") as f:
        f.write(stats_svg(user, stats))
    with open(f"{OUT}/langs.svg", "w") as f:
        f.write(langs_svg(langs))
    print("OK", stats, sorted(langs, key=lambda k: -langs[k])[:6])


if __name__ == "__main__":
    main()
