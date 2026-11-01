"""web_tools: lập kế hoạch, rơi về kế hoạch cố định, trần thời gian — không gọi mạng."""
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

import web_tools  # noqa: E402


def fake_hit(provider, n):
    return [web_tools._hit(provider, f'{provider} {i}', f'https://{provider.lower()}.test/{i}', 'nội dung')
            for i in range(n)]


class GatherTests(unittest.TestCase):
    def setUp(self):
        web_tools._cache.clear()
        self.cfg = patch.multiple(web_tools.config, WEB_SEARCH_ENABLED=True, TAVILY_API_KEY='k',
                                  WEB_SEARCH_DOMAINS=[])
        self.cfg.start()
        self.addCleanup(self.cfg.stop)
        self.specs = patch.dict(web_tools._TOOL_SPECS, {
            'tim_web': {**web_tools._TOOL_SPECS['tim_web'], 'fn': lambda q: fake_hit('Web', 2)},
            'tim_pubmed': {**web_tools._TOOL_SPECS['tim_pubmed'], 'fn': lambda q: fake_hit('PubMed', 3)},
        })
        self.specs.start()
        self.addCleanup(self.specs.stop)

    def test_uses_planner_calls(self):
        with patch.object(web_tools, 'plan', return_value=[('tim_pubmed', 'otitis media')]):
            out = web_tools.gather('viêm tai giữa', 'key')
        self.assertEqual([c['tool'] for c in out['calls']], ['tim_pubmed'])
        self.assertEqual(len(out['sources']), 3)
        self.assertTrue(all(s['kind'] == 'web' for s in out['sources']))

    def test_planner_failure_falls_back_to_web_search_not_pubmed(self):
        with patch.object(web_tools, 'plan', side_effect=RuntimeError('boom')):
            out = web_tools.gather('viêm tai giữa', 'key')
        self.assertEqual(out['calls'][0]['tool'], 'tim_web')
        self.assertTrue(out['errors'])

    def test_no_tavily_and_no_planner_means_no_calls(self):
        with patch.object(web_tools.config, 'TAVILY_API_KEY', ''):
            out = web_tools.gather('viêm tai giữa', '')
            self.assertNotIn('tim_web', web_tools.available_tools())
        self.assertEqual(out['sources'], [])

    def test_disabled_switch_hides_every_tool(self):
        with patch.object(web_tools.config, 'WEB_SEARCH_ENABLED', False):
            self.assertEqual(web_tools.available_tools(), [])

    def test_tool_error_and_timeout_do_not_raise(self):
        def slow(q):
            time.sleep(0.5)
            return fake_hit('Slow', 1)

        def broken(q):
            raise ValueError('bad json')

        with patch.dict(web_tools._TOOL_SPECS, {
            'tim_web': {**web_tools._TOOL_SPECS['tim_web'], 'fn': broken},
            'tim_pubmed': {**web_tools._TOOL_SPECS['tim_pubmed'], 'fn': slow},
        }), patch.object(web_tools, 'TOOL_WAIT_S', 0.1), \
                patch.object(web_tools, 'plan', return_value=[('tim_web', 'a'), ('tim_pubmed', 'b')]):
            out = web_tools.gather('q', 'key')
        errors = {c['tool']: c.get('error') for c in out['calls']}
        self.assertEqual(errors, {'tim_web': 'ValueError', 'tim_pubmed': 'hết thời gian'})
        self.assertEqual(out['sources'], [])

    def test_results_capped_and_deduplicated(self):
        with patch.object(web_tools, 'plan', return_value=[('tim_web', 'a'), ('tim_pubmed', 'b'),
                                                           ('tim_pubmed', 'c')]):
            out = web_tools.gather('q', 'key')
        urls = [s['url'] for s in out['sources']]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertLessEqual(len(urls), web_tools.MAX_WEB_SOURCES)


class PlanTests(unittest.TestCase):
    def test_plan_keeps_only_known_tools_and_drops_bad_args(self):
        def call(name, args):
            return types.SimpleNamespace(function=types.SimpleNamespace(name=name, arguments=args))

        msg = types.SimpleNamespace(tool_calls=[
            call('tim_pubmed', '{"query_en": "otitis media amoxicillin"}'),
            call('xoa_du_lieu', '{"x": 1}'),
            call('tim_pubmed', 'không phải json'),
            call('tim_pubmed', '{"query_en": "otitis media amoxicillin"}'),
        ])
        fake = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(
            create=lambda **kw: types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)]))))
        with patch.object(web_tools, 'OpenAI', return_value=fake):
            calls = web_tools.plan('viêm tai giữa', 'key', ['tim_pubmed'])
        self.assertEqual(calls, [('tim_pubmed', 'otitis media amoxicillin')])


if __name__ == '__main__':
    unittest.main()
