import json,gzip,hashlib,re,sys,collections
from badger_evidence.extract import extract_article,parse_xml,text
bundle=json.load(gzip.open(sys.argv[1]))
man=json.load(open('data/manifest.json'));have={m['pmcid'] for m in man}
added=collections.Counter();skipped=collections.Counter()
for pid,x in sorted(bundle.items()):
    if pid in have: skipped['have']+=1; continue
    raw=x.encode('utf-8')
    try: r=extract_article(raw,{'pmcid':pid})
    except Exception as e: skipped['err']+=1; continue
    ok=[y for y in r['records'] if not set(y['flags'])-{'missing_assay_context'} and y['value'] is not None]
    if not ok: skipped['no_clean']+=1; continue
    root=parse_xml(raw); lic=root.find('./front/article-meta/permissions')
    blob=((''.join(lic.itertext()) if lic is not None else '')+' '+' '.join(v for e in (lic.iter() if lic is not None else []) for k,v in e.attrib.items() if 'href' in k)).lower()
    if not ('licenses/by/' in blob or 'cc by' in blob or 'cc-by' in blob or 'creative commons attribution' in blob) or re.search(r'by-nc|by-nd|noncommercial|non-commercial|no derivatives',blob):
        skipped['license']+=1; continue
    title=text(root.find('./front/article-meta/title-group/article-title'))
    doi={n.get('pub-id-type'):text(n) for n in root.findall('./front/article-meta/article-id')}.get('doi','')
    year=text(root.find('./front/article-meta/pub-date/year'))
    open(f'data/source/{pid}.xml','wb').write(raw)
    man.append({"pmcid":pid,"title":title,"doi":doi,"year":int(year) if year.isdigit() else year,"license":"CC BY 4.0","license_url":"https://creativecommons.org/licenses/by/4.0/",
      "source_url":f"https://pmc.ncbi.nlm.nih.gov/articles/{pid}/","download_url":f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pid}/fullTextXML","filename":f"{pid}.xml","sha256":hashlib.sha256(raw).hexdigest()})
    for y in ok: added[y['target']]+=1
json.dump(man,open('data/manifest.json','w'),indent=2,ensure_ascii=False);open('data/manifest.json','a').write('\n')
print('papers',len(man),'skipped',dict(skipped));print('clean candidates',dict(added))
