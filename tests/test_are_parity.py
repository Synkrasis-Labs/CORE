"""Parity gates use real ARE registered tools, including exceptions."""

import unittest
from are_integration.parity import run_parity


class AREParityTests(unittest.TestCase):
    def test_original_and_are_paths_match_including_mistakes(self):
        results = run_parity()
        for label, result in results.items():
            with self.subTest(case=label):
                self.assertTrue(all(result['checks'].values()), result['checks'])
        self.assertEqual(results['reference']['evaluation']['score'], 1.0)
        self.assertAlmostEqual(results['reversed']['evaluation']['score'], 1 / 3)
        for label in ('extra_unmapped', 'failed', 'domain_none'):
            self.assertEqual(results[label]['evaluation']['status'], 'unscored')
            self.assertEqual(len(results[label]['are']['workflow']), 3)
        self.assertEqual(results['failed']['are']['workflow']['call_3']['status'], 'error')
        self.assertEqual(results['domain_none']['are']['workflow']['call_3']['status'], 'ok')
        self.assertIsNone(results['domain_none']['are']['workflow']['call_3']['content'])


if __name__ == '__main__':
    unittest.main()
