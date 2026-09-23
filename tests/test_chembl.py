import json
import tempfile
import unittest
from pathlib import Path
from badger_evidence.pipeline import chembl_summary


class ComparisonTests(unittest.TestCase):
    def compare(self, *, mol='M1', endpoint='Ki', relation='=', value=10, doc='D1', unit='nM', validity=None, identity=True):
        row = [1, mol, 'Drug', endpoint, relation, value, unit, 8, 'A1', doc, 2020, validity]
        record = dict(target='CA2', review_status='reviewed', normalized_value_nm=10,
                      pmcid='PMC1', measurement_type='Ki', relation='=')
        if identity:
            record['molecule'] = {'chembl_id': 'M1'}
        dataset = {'articles': [{'pmcid': 'PMC1', 'doi': '10/example'}], 'records': [record]}
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'chembl'
            folder.mkdir()
            (folder / 'CA2.json').write_text(json.dumps(dict(target='CA2', target_chembl_id='T1',
                docs={'D1': ['10/example'], 'D2': ['10/other']}, rows=[row])))
            report = chembl_summary(Path(temp), dataset)['CA2']['crosscheck']
        return report, record

    def test_matching_identity_and_endpoint_agree(self):
        self.assertEqual(self.compare()[0], {'checked': 1, 'agreed': 1})

    def test_wrong_compound_same_number_is_not_agreement(self):
        self.assertEqual(self.compare(mol='M2')[0], {'checked': 0, 'agreed': 0})

    def test_missing_coverage_is_not_disagreement(self):
        for args in ({'identity': False}, {'endpoint': 'IC50'}, {'doc': 'D2'},
                     {'relation': '>'}, {'unit': 'µM'}, {'validity': 'Outside typical range'}):
            with self.subTest(args=args):
                report, record = self.compare(**args)
                self.assertEqual(report['checked'], 0)
                self.assertNotIn('chembl_match', record)

    def test_real_numerical_disagreement(self):
        self.assertEqual(self.compare(value=50)[0], {'checked': 1, 'agreed': 0})

    def test_rounding_tolerance(self):
        self.assertEqual(self.compare(value=10.1)[0]['agreed'], 1)
