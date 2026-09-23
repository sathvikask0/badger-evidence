import unittest

from badger_evidence.targets import caption_target, header_target, is_bare_endpoint


class TargetTests(unittest.TestCase):
    def test_named_headers(self):
        self.assertEqual(header_target("IC50 (nM) | mTOR", ""), "MTOR")
        self.assertEqual(header_target("IC50 (µM) | SIRT2", ""), "SIRT2")
        self.assertEqual(header_target("hAChE IC50 (µM)", ""), "ACHE")
        self.assertEqual(header_target("EGFR inhibition IC50 (nM)", ""), "EGFR")

    def test_lookalikes_rejected(self):
        self.assertIsNone(header_target("eeAChE IC50", ""))
        self.assertIsNone(header_target("AChE IC50", "Inhibition of electric eel AChE"))
        self.assertIsNone(header_target("EGFR T790M IC50", ""))
        self.assertIsNone(header_target("EGFR IC50 | LR", "activities against mutant EGFR"))
        self.assertIsNone(header_target("IC50 (nM) EGFR | MCF-7", ""))
        self.assertIsNone(header_target("% of mTOR inhibition at 10 µM", ""))
        self.assertIsNone(header_target("p-mTOR IC50", ""))
        self.assertIsNone(header_target("SI (mTOR/PI3Kα)", ""))
        self.assertIsNone(header_target("IC50 (µM) | SIRT5", ""))

    def test_caption_only_tables(self):
        self.assertEqual(caption_target("In vitro assay results for mTOR inhibitions."), "MTOR")
        self.assertIsNone(caption_target("Antiproliferative activity against A549 cells and EGFR"))
        self.assertIsNone(caption_target("Inhibition of mTOR and EGFR"))
        self.assertTrue(is_bare_endpoint("IC50 (μM)"))
        self.assertFalse(is_bare_endpoint("A549 IC50 (µM)"))
