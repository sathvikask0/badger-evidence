"""Render reading notes (notes/*.md) as site pages. Stdlib only, so the Pages build needs no extra packages.

The Markdown in notes/ is the source of truth; pages are generated from it at build/serve time.
Supports the subset the notes use: headings, paragraphs, bold/italic/code, links, rules, lists and tables.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

NOTES = Path(__file__).resolve().parent.parent / "notes"
REPO = "https://github.com/sathvikask0/badger-evidence/blob/main/notes/"


def inline(text: str) -> str:
    out, links = html.escape(text, quote=False), []

    def stash(m):
        links.append(f'<a href="{html.escape(m[2])}">{m[1]}</a>')
        return f"\x00{len(links) - 1}\x00"

    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", stash, out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", out)
    out = re.sub(r"\x00(\d+)\x00", lambda m: links[int(m[1])], out)
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", text).lower()).strip("-")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def render_markdown(text: str) -> tuple[str, str, list[tuple[str, str]]]:
    """Return (title, body_html, [(id, h2 text)])."""
    lines, i, parts, title, toc = text.splitlines(), 0, [], "", []
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if re.fullmatch(r"\s*(-{3,}|\*{3,})\s*", line):
            parts.append("<hr>")
            i += 1
            continue
        h = re.match(r"(#{1,6})\s+(.*)", line)
        if h:
            level, content = len(h[1]), inline(h[2].strip())
            if level == 1 and not title:
                title = content
            else:
                anchor = _slug(content)
                if level == 2:
                    toc.append((anchor, content))
                parts.append(f'<h{level} id="{anchor}">{content}</h{level}>')
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", lines[i + 1]):
            head = "".join(f"<th>{inline(c)}</th>" for c in _cells(line))
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in _cells(lines[i])) + "</tr>")
                i += 1
            parts.append(f'<div class="md-table"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
            continue
        lm = re.match(r"\s*([-*]|\d+\.)\s+", line)
        if lm:
            tag = "ol" if lm[1][0].isdigit() else "ul"
            items = []
            while i < len(lines) and re.match(r"\s*([-*]|\d+\.)\s+", lines[i]):
                items.append(inline(re.sub(r"\s*([-*]|\d+\.)\s+", "", lines[i], count=1)))
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():
                    items[-1] += " " + inline(lines[i].strip())
                    i += 1
            parts.append(f"<{tag}>" + "".join(f"<li>{x}</li>" for x in items) + f"</{tag}>")
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(r"(#{1,6}\s|\s*\||\s*([-*]|\d+\.)\s+|\s*-{3,}\s*$)", lines[i]):
            para.append(inline(lines[i].strip()))
            i += 1
        parts.append("<p>" + "<br>".join(para) + "</p>")
    return title or "Notes", "\n".join(parts), toc


PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light dark">
    <meta name="theme-color" content="#1d5c46">
    <title>{title_text} · Badger Evidence</title>
    <link rel="icon" href="../favicon.svg" type="image/svg+xml">
    <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
    <link rel="stylesheet" href="../style.css">
    <script>try{{var t=localStorage.getItem("be-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t;}}catch(e){{}}</script>
    <style>
      .nav-links{{display:flex;gap:18px;margin-right:18px;font-size:13px;font-weight:600}}
      .nav-links a{{color:var(--muted);text-decoration:none}}.nav-links a[aria-current]{{color:var(--ink)}}.nav-links a:hover{{color:var(--ink)}}
      .md-main{{max-width:980px}}
      .md-back{{display:inline-block;font-family:var(--mono);font-size:12px;color:var(--muted);text-decoration:none;margin:4px 0 22px}}.md-back:hover{{color:var(--ink)}}
      .md-hero h1{{font-family:var(--serif);font-weight:400;font-size:clamp(32px,4vw,50px);letter-spacing:-.5px;line-height:1.1;margin:10px 0 0;max-width:22ch}}
      .md-toc{{display:flex;flex-wrap:wrap;gap:6px 18px;margin:22px 0 8px;padding:14px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);font-size:12.5px}}
      .md-toc a{{color:var(--muted);text-decoration:none}}.md-toc a:hover{{color:var(--ink)}}
      .md{{max-width:72ch;font-size:15px;line-height:1.8;color:var(--ink);padding-bottom:40px}}
      .md p{{margin:0 0 14px}}
      .md h2{{font-family:var(--serif);font-weight:400;font-size:32px;letter-spacing:-.2px;margin:40px 0 12px;scroll-margin-top:20px}}
      .md h3{{font-size:16px;font-weight:650;margin:28px 0 8px}}
      .md hr{{border:0;border-top:1px solid var(--line);margin:36px 0 0}}
      .md ul,.md ol{{padding-left:22px;margin:0 0 16px}}.md li{{margin-bottom:6px}}
      .md code{{font-family:var(--mono);font-size:.88em;background:var(--teal-soft);padding:1px 5px;border-radius:4px}}
      .md strong{{font-weight:650}}
      .md-table{{overflow-x:auto;margin:8px 0 22px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);max-width:none;width:min(980px,100%)}}
      .md table{{border-collapse:collapse;width:100%;font-size:13px;line-height:1.6}}
      .md th{{text-align:left;font-size:11px;letter-spacing:.3px;color:var(--muted);font-weight:650;padding:10px 12px;border-bottom:1px solid var(--line);white-space:nowrap}}
      .md td{{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}}.md tr:last-child td{{border-bottom:0}}
      .md-links{{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 10px}}
      @media(max-width:760px){{.nav-links{{gap:12px;margin-right:8px;font-size:12px}}.md{{font-size:14px}}.md h2{{font-size:26px}}}}
    </style>
  </head>
  <body>
    <header class="site-header">
      <a class="brand" href="../" aria-label="Badger Evidence home">
        <svg class="brand-mark" viewBox="0 0 36 36" aria-hidden="true"><path d="M18 2 33 10v16l-15 8L3 26V10Z" fill="currentColor"/><path d="m10 11 7 4v13l-7-5Zm16 0-7 4v13l7-5Z" fill="#fff"/><path d="m14 9 4-2 4 2-4 3Z" fill="#72d2bc"/></svg>
        <span>Badger <strong>Evidence</strong></span>
      </a>
      <div class="header-meta"><nav class="nav-links" aria-label="Pages"><a href="../">Atlas</a><a href="../findings.html">Findings</a><a href="../notes.html" aria-current="page">Notes</a></nav><button id="theme-toggle" class="theme-toggle" type="button" aria-label="Colour theme: automatic">Auto</button></div>
    </header>

    <main class="md-main">
      <a class="md-back" href="../notes.html">&larr; All notes</a>
      <section class="md-hero">
        <p class="eyebrow">Reading notes</p>
        <h1>{title}</h1>
      </section>
      <nav class="md-toc" aria-label="Sections">{toc}</nav>
      <article class="md">
{body}
        <div class="md-links"><a class="button button-secondary" href="{source}">View Markdown source</a></div>
      </article>
      <footer class="site-footer"><span>Badger Bioworks <span aria-hidden="true">/</span> Evidence before inference.</span><span>Notes are personal readings, not peer review.</span></footer>
    </main>

    <script>
    (function () {{
      var THEMES = ["auto", "light", "dark"], btn = document.getElementById("theme-toggle");
      function apply(th) {{ if (th === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = th; btn.textContent = th[0].toUpperCase() + th.slice(1); btn.setAttribute("aria-label", "Colour theme: " + th); }}
      apply(document.documentElement.dataset.theme || "auto");
      btn.addEventListener("click", function () {{ var cur = document.documentElement.dataset.theme || "auto", next = THEMES[(THEMES.indexOf(cur) + 1) % 3]; apply(next); try {{ if (next === "auto") localStorage.removeItem("be-theme"); else localStorage.setItem("be-theme", next); }} catch (e) {{}} }});
    }})();
    </script>
  </body>
</html>
"""


def render_note(path: Path) -> str:
    title, body, toc = render_markdown(path.read_text(encoding="utf-8"))
    return PAGE.format(
        title=title,
        title_text=html.escape(re.sub(r"<[^>]+>", "", html.unescape(title)), quote=False),
        toc="".join(f'<a href="#{a}">{t}</a>' for a, t in toc),
        body=body,
        source=REPO + path.name,
    )


def note_paths(notes_dir: Path = NOTES) -> list[Path]:
    return sorted(notes_dir.glob("*.md")) if notes_dir.exists() else []


def build_notes(output: Path, notes_dir: Path = NOTES) -> list[Path]:
    (output / "notes").mkdir(parents=True, exist_ok=True)
    written = []
    for path in note_paths(notes_dir):
        target = output / "notes" / (path.stem + ".html")
        target.write_text(render_note(path), encoding="utf-8")
        written.append(target)
    return written
