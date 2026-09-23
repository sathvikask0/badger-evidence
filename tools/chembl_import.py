"""Write data/chembl/<TARGET>.json from a browser-fetched ChEMBL bundle.

Bundle: {"fetched": "...", "chembl_release": "...", "targets": {KEY: {"target_chembl_id", "assays", "rows"}}, "docs": {doc_id: [doi, journal, year, title]}}
Rows: [activity_id, molecule_chembl_id, pref_name, standard_type, standard_relation, standard_value, standard_units, pchembl, assay_id, document_id, year, validity_comment]
Only nM values with a pChEMBL value are kept (ChEMBL's own quality filter)."""
import gzip, json, sys
from pathlib import Path

bundle = json.load(gzip.open(sys.argv[1]) if sys.argv[1].endswith('.gz') else open(sys.argv[1]))
out = Path('data/chembl'); out.mkdir(parents=True, exist_ok=True)
for key, t in bundle['targets'].items():
    rows = [r for r in t['rows'] if r[6] == 'nM' and r[5] not in (None, '')]
    rows = [r[:5] + [float(r[5])] + r[6:7] + [float(r[7]) if r[7] else None] + r[8:] for r in rows]
    seen, uniq = set(), []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0]); uniq.append(r)
    docs = {r[9]: bundle['docs'].get(r[9]) for r in uniq}
    assays = {r[8]: t['assays'].get(r[8]) for r in uniq}
    (out / f'{key}.json').write_text(json.dumps({
        'target': key, 'target_chembl_id': t['target_chembl_id'], 'fetched': bundle.get('fetched'),
        'license': 'CC BY-SA 3.0 (ChEMBL, EMBL-EBI)', 'filter': 'standard_type in IC50/Ki/Kd, units nM, pChEMBL present',
        'assays': assays, 'docs': docs, 'rows': uniq}, ensure_ascii=False, separators=(',', ':')))
    print(key, len(uniq))
