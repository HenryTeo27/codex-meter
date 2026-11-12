import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import meter
import sources


class SourceDiscoveryTests(unittest.TestCase):
    def test_discovers_default_environment_saved_and_extra_homes_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            default = root / '.codex'
            api = root / '.codex-api'
            custom = root / 'custom'
            for home in (default, api, custom):
                (home / 'sessions').mkdir(parents=True)
            (root / '.codex-unrelated').mkdir()
            env = {'CODEX_HOME': str(api), 'CODEX_METER_EXTRA_HOMES': str(custom)}
            with patch.object(sources.Path, 'home', return_value=root), \
                 patch.dict(os.environ, env, clear=True), \
                 patch.object(sources, 'persisted_environment', return_value=[str(api)]):
                self.assertEqual(sources.codex_homes(), [default.resolve(), api.resolve(), custom.resolve()])

    def test_auth_modes_and_missing_or_corrupt_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            auth = home / 'auth.json'
            self.assertIsNone(sources.read_auth_mode(home))
            auth.write_text('{broken', encoding='utf-8')
            self.assertIsNone(sources.read_auth_mode(home))
            auth.write_text(json.dumps({'auth_mode': 'apikey', 'OPENAI_API_KEY': 'secret'}), encoding='utf-8')
            self.assertEqual(sources.read_auth_mode(home), 'apiKey')
            auth.write_text(json.dumps({'tokens': {'id_token': 'secret'}}), encoding='utf-8')
            self.assertEqual(sources.read_auth_mode(home), 'chatgpt')


class MultiHomeTests(unittest.TestCase):
    def test_usage_homes_start_together_and_disabled_home_is_not_read(self):
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            homes=[Path(tmp)/name for name in ('one','two','off')]
            for home in homes: (home/'sessions').mkdir(parents=True)
            barrier=threading.Barrier(2);seen=[]
            def run(args,timeout,env):
                seen.append(env['CODEX_HOME'])
                barrier.wait(timeout=3)
                return '{"monthly":[],"totals":{"totalTokens":10,"costUSD":1}}'
            with patch.object(meter,'codex_homes',return_value=homes), \
                 patch.object(meter,'load_settings',return_value={'disabled_sources':[str(homes[2])]}), \
                 patch.object(meter.shutil,'which',return_value='npx'), \
                 patch.object(meter,'run',side_effect=run):
                result=meter.get_usage()
            self.assertEqual(set(seen),{str(home) for home in homes[:2]})
            self.assertEqual(result['total_tokens'],20)
            self.assertFalse(result['failed_sources'])

    def test_all_disabled_starts_no_account_or_speed_workers(self):
        with patch.object(meter,'worker_call',side_effect=AssertionError('Started a disabled source')):
            self.assertEqual(meter.get_speed([])[0]['sources'],[])
            self.assertEqual(meter.get_limits([])['accounts'],[])

    def test_per_account_deltas_survive_a_change_to_the_enabled_set(self):
        before={'total_tokens':100,'sources':[{'source':'gpt','short':'GPT','total_tokens':100}]}
        after={'total_tokens':250,'sources':[{'source':'gpt','short':'GPT','total_tokens':130},
                                             {'source':'api','short':'API','total_tokens':120}]}
        data={}
        meter.apply_usage_result(data,after,before,1)
        self.assertIsNone(data['delta'])
        self.assertEqual(meter.delta_text(data,{}),'GPT +30 tokens\nAPI —')
        newer={**after,'sources':[{**after['sources'][0],'total_tokens':150},
                                  {**after['sources'][1],'stale':True}]}
        meter.apply_usage_result(data,newer,after,2)
        self.assertEqual(meter.delta_text(data,{}),'GPT +20 tokens\nAPI —')
        self.assertEqual(meter.delta_text(data,{'disabled_sources':['api']}),'GPT +20 tokens')

    def test_paused_usage_survives_reload_rollover_and_resume(self):
        month=meter.datetime.now().strftime('%Y-%m')
        old_month='2020-01'
        gpt={'source':'gpt','short':'GPT','month_tokens':100,'month_cost':2,'total_tokens':600,'total_cost':12}
        api={'source':'api','short':'API','month_tokens':50,'month_cost':1,'total_tokens':400,'total_cost':8}
        prior=meter.combined_usage([gpt,api],old_month)
        partial=meter.combined_usage([{**gpt,'month_tokens':120,'total_tokens':620}],old_month)
        data={}
        meter.apply_usage_result(data,meter.merge_usage_result(prior,partial),prior,1)
        self.assertEqual(data['usage']['month_tokens'],170)
        self.assertEqual(data['usage']['total_tokens'],1020)
        self.assertEqual(meter.delta_text(data,{'disabled_sources':['api']}),'GPT +20 tokens')
        with tempfile.TemporaryDirectory() as tmp, patch.object(meter,'SNAPSHOT',Path(tmp)/'snapshot.json'):
            meter.save(meter.SNAPSHOT,data)
            data=meter.load_snapshot()
        prior=data['usage']
        displayed=meter.displayed_usage(data)
        self.assertEqual((displayed['month_tokens'],displayed['month_cost']),(0,0))
        self.assertEqual((displayed['total_tokens'],displayed['total_cost']),(1020,20))

        # Even an all-off refresh preserves both last observations.
        paused=meter.merge_usage_result(prior,meter.combined_usage([],month))
        self.assertEqual(paused['month_tokens'],0)
        self.assertEqual(paused['total_tokens'],1020)
        next_gpt={**gpt,'month_tokens':30,'month_cost':1,'total_tokens':650,'total_cost':13}
        partial=meter.merge_usage_result(paused,meter.combined_usage([next_gpt],month))
        self.assertEqual((partial['month_tokens'],partial['month_cost']),(30,1))
        self.assertEqual((partial['total_tokens'],partial['total_cost']),(1050,21))

        next_api={**api,'month_tokens':20,'month_cost':1,'total_tokens':420,'total_cost':9}
        resumed=meter.merge_usage_result(partial,meter.combined_usage([next_gpt,next_api],month))
        meter.apply_usage_result(data,resumed,partial,2)
        self.assertEqual((resumed['month_tokens'],resumed['month_cost']),(50,2))
        self.assertEqual((resumed['total_tokens'],resumed['total_cost']),(1070,22))
        self.assertEqual(meter.delta_text(data,{}),'GPT +0 tokens\nAPI +20 tokens')

    def test_legacy_cached_month_uses_the_original_scan_time(self):
        api={'source':'api','stale':True,'observed_at':meter.datetime(2026,10,15).timestamp(),
             'month_tokens':50,'month_cost':1,'total_tokens':400,'total_cost':8}
        legacy=meter.combined_usage([api],'2026-11')
        merged=meter.merge_usage_result(legacy,meter.combined_usage([],'2026-11'))
        self.assertEqual((merged['month_tokens'],merged['month_cost']),(0,0))
        self.assertEqual((merged['total_tokens'],merged['total_cost']),(400,8))

    def test_limits_are_queried_per_home_without_inherited_api_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            homes = [Path(tmp) / 'chat', Path(tmp) / 'failed', Path(tmp) / 'api']
            for home in homes:
                home.mkdir()
            (homes[2] / 'auth.json').write_text('{"auth_mode":"apikey","OPENAI_API_KEY":"secret"}')
            (homes[1] / 'auth.json').write_text('{"auth_mode":"chatgpt"}')
            def query(mode, args, output, timeout, env):
                self.assertNotIn('OPENAI_API_KEY', env)
                self.assertNotIn('CODEX_API_KEY', env)
                if env['CODEX_HOME'] == str(homes[1]):
                    raise RuntimeError('do not expose secret in error')
                return {'kind': 'chatgpt', 'limits': {'primary': {'usedPercent': 25}}}
            with patch.object(meter, 'codex_homes', return_value=homes), \
                 patch.object(meter, 'worker_call', side_effect=query), \
                 patch.dict(os.environ, {'OPENAI_API_KEY': 'secret', 'CODEX_API_KEY': 'secret'}):
                result = meter.get_limits()
            self.assertEqual(result['primary']['usedPercent'], 25)
            self.assertEqual([a['kind'] for a in result['accounts']], ['chatgpt', 'chatgpt', 'apiKey'])
            self.assertEqual(result['errors'], [str(homes[1])])
            self.assertNotIn('secret', json.dumps(result))

    def test_usage_sums_distinct_homes_and_does_not_pass_keys_to_ccusage(self):
        with tempfile.TemporaryDirectory() as tmp:
            homes = [Path(tmp) / 'chat', Path(tmp) / 'api']
            for home in homes:
                (home / 'sessions').mkdir(parents=True)
            month = meter.datetime.now().strftime('%Y-%m')
            def run(args, timeout, env):
                self.assertNotIn('OPENAI_API_KEY', env)
                number = 10 if env['CODEX_HOME'] == str(homes[0]) else 20
                return json.dumps({'monthly': [{'month': month, 'totalTokens': number, 'costUSD': number / 10}],
                                   'totals': {'totalTokens': number * 2, 'costUSD': number / 5}})
            with patch.object(meter, 'codex_homes', return_value=homes), \
                 patch.object(meter.shutil, 'which', return_value='npx'), \
                 patch.object(meter, 'run', side_effect=run), \
                 patch.dict(os.environ, {'OPENAI_API_KEY': 'secret'}):
                result = meter.get_usage()
            self.assertEqual(result['month_tokens'], 30)
            self.assertEqual(result['total_tokens'], 60)
            self.assertEqual(result['month_cost'], 3)
            self.assertEqual(result['total_cost'], 6)
            self.assertEqual([item['month_tokens'] for item in result['sources']], [10, 20])
            self.assertNotIn('secret', json.dumps(result))

    def test_changing_homes_does_not_report_new_history_as_new_usage(self):
        previous = {'total_tokens': 100, 'sources': [{'source': 'one'}]}
        current = {'total_tokens': 1000, 'sources': [{'source': 'one'}, {'source': 'two'}]}
        data = {}
        meter.apply_usage_result(data, current, previous, 1)
        self.assertIsNone(data['delta'])
        meter.apply_usage_result(data, {**current, 'total_tokens': 1010}, current, 2)
        self.assertEqual(data['delta'], 10)

    def test_combined_speed_deduplicates_response_ids_across_homes(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        now = meter.datetime.now(meter.timezone.utc).isoformat()
        def sample(identity):
            return SimpleNamespace(response_id=identity, completed_at=now, output_tokens=200)
        with tempfile.TemporaryDirectory() as tmp:
            homes = [Path(tmp) / 'one', Path(tmp) / 'two']
            for home in homes:
                (home / 'sessions').mkdir(parents=True)
            engine = SimpleNamespace(find_rollouts=lambda home: [], json=None)
            engine.load_samples = lambda home, cache, workers: (
                [sample('shared'), sample('unique')] if home == homes[0] else [sample('shared')],
                {'unreadable_files': 0})
            engine.build_report = lambda selected, *args: {}
            counts = []
            def report(metadata, selected, tz, **kwargs):
                counts.append(len(selected))
                print('Selected history\nModel Normal eff Fast eff Ratio Normal n Fast n\ngpt-test 10 20 2× 1 1\n')
            engine.print_report = report
            spec = MagicMock()
            with patch.object(meter, 'codex_homes', return_value=homes), \
                 patch.object(meter.importlib.util, 'spec_from_file_location', return_value=spec), \
                 patch.object(meter.importlib.util, 'module_from_spec', return_value=engine):
                result = meter.speed_batch('test-engine.py',windows=['1','14'])
            self.assertEqual(counts, [2, 2, 2, 2, 1, 1])
            self.assertEqual(len(result['sources']), 2)
            meter.sys.modules.pop('_codex_meter_speed', None)


if __name__ == '__main__':
    unittest.main()
