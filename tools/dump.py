import json,collections,sys
d=json.load(open('data/generated/dataset.json'))
only=set(sys.argv[1].split(',')) if len(sys.argv)>1 and sys.argv[1] else None
pids=set(sys.argv[2].split(',')) if len(sys.argv)>2 else None
T={(t['pmcid'],t['table_id']):t for t in d['tables']}
g=collections.defaultdict(list)
for r in d['records']:
    if (only and r['target'] not in only) or (pids and r['pmcid'] not in pids) or r['review_status']=='reviewed': continue
    g[(r['pmcid'],r['table_id'],r['target_column'])].append(r)
for (p,tid,col),rs in sorted(g.items()):
    t=T[(p,tid)]; r0=rs[0]
    if not [r for r in rs if not set(r["flags"])-{"missing_assay_context","target_from_caption"} and r["value"] is not None]: continue
    ok=[r for r in rs if not set(r['flags'])-{'missing_assay_context','target_from_caption'} and r['value'] is not None]
    print(f"### {p}|{tid}|{col} -> {r0['target']} {r0['measurement_type']} {r0['unit']} n={len(rs)} ok={len(ok)} flags={sorted(set(f for r in rs for f in r['flags']))[:5]}")
    print('  CAP:',t['caption'][:200]); print('  HDR:',r0['evidence']['header'][:100])
    print('  EX:',[(r['compound_label'][:15],r['raw_value'][:18]) for r in rs[:3]])
