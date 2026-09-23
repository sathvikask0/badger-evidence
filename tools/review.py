"""Mark records reviewed: pass cell-level transcription check, no blocking flags,
table not on the reject list (tables I read and rejected)."""
import json,re,sys,xml.etree.ElementTree as ET
REJECT_PAPERS={'PMC7356367'}
REJECT_TABLES=set(json.load(open('tools/reject_tables.json')))
CAPTION_OK_PAPERS={'PMC4702177','PMC6274251','PMC13466518'}
d=json.load(open('data/generated/dataset.json'));R=d['records']
def norm(s): return re.sub(r'\s','',s)
trees={};rev=json.load(open('data/reviews.json'));added=0
for r in R:
    if r['id'] in rev['records'] or r['value'] is None: continue
    if r['pmcid'] in REJECT_PAPERS or f"{r['pmcid']}|{r['table_id']}" in REJECT_TABLES: continue
    allowed={'missing_assay_context'}|({'target_from_caption'} if r['pmcid'] in CAPTION_OK_PAPERS else set())
    if set(r['flags'])-allowed: continue
    p=r['pmcid']
    if p not in trees: trees[p]=ET.parse(f'data/source/{p}.xml').getroot()
    t=[w for w in trees[p].iter() if w.tag.endswith('table-wrap') and w.get('id')==r['table_id']][0]
    alltext=norm(''.join(t.itertext()))
    if norm(r['raw_value']) not in alltext or r['raw_value']!=r['evidence']['row'][r['target_column']]: continue
    f={'nM':1,'µM':1e3,'mM':1e6,'pM':1e-3,'M':1e9}.get(r['unit'])
    if f is None or abs(r['value']*f-r['normalized_value_nm'])>1e-6*max(1,r['normalized_value_nm']): continue
    rev['records'][r['id']]='reviewed';added+=1
json.dump(rev,open('data/reviews.json','w'),indent=1);open('data/reviews.json','a').write('\n')
print('added',added)
