"""Use isolated data and hidden Tk windows to test a built macOS bundle."""
import json,os,subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
executable=root/'dist/CodexMeter.app/Contents/MacOS/CodexMeter'
with tempfile.TemporaryDirectory() as folder:
    folder=Path(folder);output=folder/'health.json';env={**os.environ,'CODEX_METER_DATA_DIR':str(folder/'state')}
    subprocess.run([str(executable),'--health-check','--worker-output',str(output)],env=env,check=True,timeout=45)
    assert json.loads(output.read_text())['ok']
    script=folder/'check.py'
    script.write_text('''import sys,json
m=sys.modules['_codex_meter_runtime']
m.App.show=lambda app:None
m.App.setup_tray=lambda app:None
m.App.publish_ready=lambda app:None
m.save(m.CONFIG,{'interval':0,'speed_windows':['4h','1'],'appearance':'dark'})
m.save(m.SNAPSHOT,{'usage':{'month_tokens':123,'total_tokens':456,'month_cost':1,'total_cost':2}})
app=m.App()
assert app.root.state()=='withdrawn'
assert app.settings['appearance']=='dark' and app.data['usage']['month_tokens']==123
app.root.after(200,app.root.quit)
app.run();app.save_exit_state();app.root.destroy()
print('macOS hidden UI and persistence passed')
''')
    subprocess.run([str(executable),'--speed-worker',str(script),'--worker-output',str(output)],env=env,check=True,timeout=45)
    result=json.loads(output.read_text());assert result['ok'],result
    print(result['value'])
