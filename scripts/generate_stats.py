"""Erzeugt die Statistik-Karten fuer die Profil-README als SVG (hell und dunkel).

Ausgabe in assets/:
    stats.svg / stats-dark.svg   Kennzahlen (Repos, Sterne, Commits, PRs, Issues, Follower)
    langs.svg / langs-dark.svg   meistgenutzte Sprachen nach Code-Menge

Nur Python-Standardbibliothek. Im Workflow liefert GITHUB_TOKEN das hoehere
Rate-Limit; lokal geht es auch ohne Token (dann nur wenige Abfragen pro Stunde).

Benutzung:
    python scripts/generate_stats.py [benutzername]
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
API = "https://api.github.com"

# Jupyter-Notebooks bestehen zum Grossteil aus JSON-Ausgaben und wuerden die Statistik verzerren.
EXCLUDE_LANGUAGES = {"Jupyter Notebook"}
TOP_LANGUAGES = 8

LANGUAGE_COLORS = {
    "C#": "#178600", "Python": "#3572A5", "JavaScript": "#F1E05A", "TypeScript": "#3178C6",
    "Vue": "#41B883", "HTML": "#E34C26", "CSS": "#663399", "GDScript": "#355570",
    "SCSS": "#C6538C", "Shell": "#89E051", "PowerShell": "#012456", "Batchfile": "#C1F12E",
}
FALLBACK_COLORS = ["#00A8C6", "#F4C518", "#4DCBE0", "#007A91", "#F9D659", "#8C8C8C"]

THEMES = {
    "light": {"bg": "#FFFFFF", "border": "#D6D6D6", "title": "#007A91", "text": "#5A5A5A",
              "muted": "#8C8C8C", "accent": "#00A8C6", "track": "#F2F2F2"},
    "dark": {"bg": "#1E1E1E", "border": "#3A3A3A", "title": "#4DCBE0", "text": "#D6D6D6",
             "muted": "#8C8C8C", "accent": "#F4C518", "track": "#3A3A3A"},
}
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"
WIDTH, HEIGHT = 495, 195


def request(path: str) -> dict | list:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-stats-script"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = path if path.startswith("http") else API + path
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return json.load(response)


def own_repositories(user: str) -> list[dict]:
    repos, page = [], 1
    while True:
        chunk = request(f"/users/{user}/repos?per_page=100&page={page}&type=owner")
        repos += chunk
        if len(chunk) < 100:
            return [repo for repo in repos if not repo["fork"]]
        page += 1


def search_count(kind: str, query: str) -> int:
    return request(f"/search/{kind}?q={urllib.parse.quote(query)}&per_page=1")["total_count"]


def collect(user: str) -> tuple[dict, Counter]:
    profile = request(f"/users/{user}")
    repos = own_repositories(user)
    since = (date.today() - timedelta(days=365)).isoformat()

    languages: Counter = Counter()
    for repo in repos:
        for name, size in request(f"/repos/{user}/{repo['name']}/languages").items():
            if name not in EXCLUDE_LANGUAGES:
                languages[name] += size

    stats = {
        "Public repos": len(repos),
        "Stars earned": sum(repo["stargazers_count"] for repo in repos),
        "Commits (1 year)": search_count("commits", f"author:{user} author-date:>={since}"),
        "Pull requests": search_count("issues", f"author:{user} type:pr is:public"),
        "Issues": search_count("issues", f"author:{user} type:issue is:public"),
        "Followers": profile["followers"],
    }
    return stats, languages


def card(theme: str, title: str, body: str) -> str:
    c = THEMES[theme]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{escape(title)}">
  <title>{escape(title)}</title>
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="8" fill="{c['bg']}" stroke="{c['border']}"/>
  <text x="25" y="35" font-family="{FONT}" font-size="18" font-weight="600" fill="{c['title']}">{escape(title)}</text>
{body}
  <text x="{WIDTH - 25}" y="{HEIGHT - 12}" text-anchor="end" font-family="{FONT}" font-size="10" fill="{c['muted']}">updated {date.today().isoformat()}</text>
</svg>
"""


def stats_card(theme: str, stats: dict) -> str:
    c = THEMES[theme]
    cells = []
    for index, (label, value) in enumerate(stats.items()):
        x = 25 + (index % 3) * 150
        y = 85 + (index // 3) * 55
        cells.append(
            f'  <text x="{x}" y="{y}" font-family="{FONT}" font-size="26" font-weight="700" fill="{c["accent"]}">{value:,}</text>\n'
            f'  <text x="{x}" y="{y + 20}" font-family="{FONT}" font-size="12" fill="{c["text"]}">{escape(label)}</text>'
        )
    return card(theme, "GitHub stats", "\n".join(cells))


def language_color(name: str, index: int) -> str:
    return LANGUAGE_COLORS.get(name, FALLBACK_COLORS[index % len(FALLBACK_COLORS)])


def languages_card(theme: str, languages: Counter) -> str:
    c = THEMES[theme]
    total = sum(languages.values()) or 1
    top = languages.most_common(TOP_LANGUAGES)
    other = total - sum(size for _, size in top)
    if other > 0:
        top.append(("Other", other))

    bar_x, bar_width = 25, WIDTH - 50
    parts = [f'  <clipPath id="bar-{theme}"><rect x="{bar_x}" y="50" width="{bar_width}" height="10" rx="5"/></clipPath>',
             f'  <rect x="{bar_x}" y="50" width="{bar_width}" height="10" rx="5" fill="{c["track"]}"/>',
             f'  <g clip-path="url(#bar-{theme})">']
    x = float(bar_x)
    for index, (name, size) in enumerate(top):
        width = bar_width * size / total
        color = c["muted"] if name == "Other" else language_color(name, index)
        parts.append(f'    <rect x="{x:.2f}" y="50" width="{width:.2f}" height="10" fill="{color}"/>')
        x += width
    parts.append("  </g>")

    for index, (name, size) in enumerate(top):
        col, row = divmod(index, 5)
        lx, ly = 25 + col * 230, 88 + row * 20
        color = c["muted"] if name == "Other" else language_color(name, index)
        parts.append(
            f'  <circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{color}"/>\n'
            f'  <text x="{lx + 18}" y="{ly}" font-family="{FONT}" font-size="12" fill="{c["text"]}">{escape(name)}'
            f'<tspan fill="{c["muted"]}"> {size / total * 100:.1f}%</tspan></text>'
        )
    return card(theme, "Top languages", "\n".join(parts))


def main() -> None:
    user = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_REPOSITORY_OWNER", "TranceMeli")
    stats, languages = collect(user)
    OUT.mkdir(exist_ok=True)
    for theme, suffix in (("light", ""), ("dark", "-dark")):
        (OUT / f"stats{suffix}.svg").write_text(stats_card(theme, stats), encoding="utf-8")
        (OUT / f"langs{suffix}.svg").write_text(languages_card(theme, languages), encoding="utf-8")
    print(stats)
    print(languages.most_common(TOP_LANGUAGES))


if __name__ == "__main__":
    main()
