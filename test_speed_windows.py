"""Selection and rolling-window checks; no desktop windows or real account queries."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import meter


class SpeedWindowTests(unittest.TestCase):
    def test_defaults_saved_choices_and_all_off_survive_reload(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(meter,'CONFIG',Path(folder)/'settings.json'):
            self.assertEqual(meter.load_settings()['speed_windows'],['4h','1'])
            for selected,expected in [(['14','4h','14','invalid'],['4h','14']),([],[]),(['1'],['1'])]:
                meter.save(meter.CONFIG,{'speed_windows':selected,'disabled_sources':['off']})
                settings=meter.load_settings()
                self.assertEqual(settings['speed_windows'],expected)
                self.assertEqual(settings['disabled_sources'],['off'])
            meter.save(meter.CONFIG,{'speed_windows':None})
            self.assertEqual(meter.load_settings()['speed_windows'],['4h','1'])

    def test_all_off_avoids_workers_imports_and_npx(self):
        with patch.object(meter,'worker_call',side_effect=AssertionError('worker started')), \
             patch.object(meter.shutil,'which',side_effect=AssertionError('npx lookup')), \
             patch.object(meter.importlib.util,'spec_from_file_location',side_effect=AssertionError('engine loaded')):
            self.assertEqual(meter.get_speed([Path('on')],[]),({'sources':[]},''))
            self.assertEqual(meter.scan_speed([Path('on')],[]),({'sources':[]},''))
            self.assertEqual(meter.speed_batch('unused.py',[Path('on')],[]),{'sources':[]})
            self.assertEqual(meter.get_speed([],['14'])[0]['sources'],[])
            self.assertEqual(meter.get_limits([])['accounts'],[])
            self.assertEqual(meter.get_usage([])['sources'],[])

    def test_worker_receives_exact_account_and_window_selection(self):
        homes=[Path('selected-account')];windows=['4h','14']
        def call(mode,args,output,timeout,env):
            self.assertEqual(mode,'--speed-all')
            self.assertEqual(json.loads(args[0]),[str(homes[0])])
            self.assertEqual(json.loads(args[1]),windows)
            self.assertNotIn('OPENAI_API_KEY',env)
            return [{'4h':[],'14':[],'sources':[]},'']
        with patch.object(meter,'worker_call',side_effect=call) as worker:
            meter.get_speed(homes,windows)
            self.assertEqual(worker.call_count,1)

    def test_saved_account_switch_filters_limits_and_speed_workers(self):
        with tempfile.TemporaryDirectory() as folder:
            homes=[Path(folder)/name for name in ('on','off')]
            for home in homes: home.mkdir()
            calls=[]
            def worker(mode,args,output,timeout,env):
                if mode=='--limits':
                    calls.append((mode,env['CODEX_HOME']))
                    return {'kind':'chatgpt','limits':{}}
                self.assertEqual(mode,'--speed-all')
                calls.append((mode,json.loads(args[0])))
                self.assertEqual(json.loads(args[1]),['14'])
                return [{'14':[],'sources':[]},'']
            with patch.object(meter,'codex_homes',return_value=homes), \
                 patch.object(meter,'load_settings',return_value={'disabled_sources':[meter.source_id(homes[1])],'speed_windows':['14']}), \
                 patch.object(meter,'worker_call',side_effect=worker):
                meter.get_limits();meter.get_speed()
            self.assertEqual(calls,[('--limits',str(homes[0])),('--speed-all',[str(homes[0])])])

    def test_only_selected_reports_and_log_horizon_use_exact_rolling_cutoffs(self):
        now=datetime(2026,11,1,12,tzinfo=timezone.utc)
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None): return now if tz else now.replace(tzinfo=None)
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);(home/'sessions').mkdir()
            files=[]
            for hours in (2,8,48,400):
                path=home/'sessions'/f'{hours}.jsonl';path.touch()
                stamp=(now-timedelta(hours=hours)).timestamp();os.utime(path,(stamp,stamp));files.append(path)
            samples=[SimpleNamespace(response_id=str(hours),completed_at=(now-timedelta(hours=hours)).isoformat(),output_tokens=200)
                     for hours in (0,2,4,4.01,20,24,25,100,336,337,-1)]
            samples.append(SimpleNamespace(response_id='short',completed_at=now.isoformat(),output_tokens=99))
            for windows,counts,files_read in [(['4h'],[3],[files[0]]),(['4h','1'],[3,6],files[:2]),(['14'],[9],files[:3])]:
                engine=SimpleNamespace(find_rollouts=lambda home:files,json=None)
                loads=[];reports=[]
                def load(home,cache,workers):
                    loads.append(engine.find_rollouts(home));return samples,{'unreadable_files':0}
                def report(meta,selected,tz,**kw):
                    reports.append(len(selected))
                    print('Selected history\nModel Normal Fast Ratio Normal_n Fast_n\ngpt-test 10 20 2x 1 1\n')
                engine.load_samples=load;engine.build_report=lambda *args:{};engine.print_report=report
                with patch.object(meter,'datetime',Clock),patch.object(meter,'short_names',return_value={meter.source_id(home):'GPT'}), \
                     patch.object(meter.importlib.util,'spec_from_file_location',return_value=MagicMock()), \
                     patch.object(meter.importlib.util,'module_from_spec',return_value=engine):
                    result=meter.speed_batch('fixture.py',[home],windows)
                self.assertEqual(loads,[files_read],'Each account must load once, within the selected horizon')
                self.assertEqual(reports,counts+counts)
                self.assertEqual(set(result),set(windows)|{'sources'})
                self.assertEqual(set(result['sources'][0])&set(meter.SPEED_WINDOWS),set(windows))
        meter.sys.modules.pop('_codex_meter_speed',None)

    def test_disabled_cache_survives_without_reusing_old_selected_results(self):
        before={'4h':['old-total'],'1':['one-day'],'sources':[
            {'source':'on','4h':['old'],'1':['cached-day']},
            {'source':'off','4h':['off-cache'],'14':['cached-history']}]}
        value={'4h':[],'sources':[{'source':'on','4h':[]}]}
        result=meter.merge_cached_sources(before,value,{'on'},['4h'])
        self.assertEqual(result['4h'],[])
        self.assertEqual(result['1'],['one-day'])
        self.assertEqual(result['sources'][0]['4h'],[])
        self.assertEqual(result['sources'][0]['1'],['cached-day'])
        self.assertEqual(result['sources'][1],before['sources'][1])
        self.assertEqual(meter.merge_cached_sources(before,{'sources':[]},{'on'},[])['sources'],before['sources'])


if __name__=='__main__': unittest.main()
