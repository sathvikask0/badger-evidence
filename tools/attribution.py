"""Append attribution entries for manifest papers missing from data/SOURCE_ATTRIBUTION.md."""
import json
from pathlib import Path
from badger_evidence.extract import parse_xml, text
man = json.load(open('data/manifest.json')); path = Path('data/SOURCE_ATTRIBUTION.md'); att = path.read_text()
for m in man:
    if f"## {m['pmcid']}" in att:
        continue
    root = parse_xml(open(f"data/source/{m['filename']}", 'rb').read())
    auth = [(text(c.find('name/given-names')) + ' ' + text(c.find('name/surname'))).strip()
            for c in root.findall('./front/article-meta/contrib-group/contrib') if c.find('name') is not None]
    cp = text(root.find('./front/article-meta/permissions/copyright-statement'))
    att += (f"\n## {m['pmcid']}\n\n{m['title']}\n\n{', '.join(auth[:8]) + (' et al.' if len(auth) > 8 else '')}. {m['year']}. "
            f"[Original article]({m['source_url']}). " + (f"[DOI](https://doi.org/{m['doi']}). " if m['doi'] else '') +
            f"\n\n{cp} Licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).\n")
path.write_text(att)
