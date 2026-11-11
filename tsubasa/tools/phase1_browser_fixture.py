"""Isolated browser fixture; never connects to FLM."""
import os,sys,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
home=ROOT/'.test-runs'/('phase1-browser-'+str(os.getpid()));home.mkdir(exist_ok=False);os.environ['TSUBASA_HOME']=str(home)
from app import App
class Fixture:
    def models(self):return [{'id':'qwen3-it:4b'},{'id':'qwen3.5:2b'}]
    def require_model(self,m):
        if m not in ('qwen3-it:4b','qwen3.5:2b'):raise ValueError('Not installed')
    def status(self):return {'online':True}
    def detach(self):pass
    def stream(self,model,messages,**kwargs):
        if kwargs.get('tools') and messages[-1]['role']=='user':
            yield 'tool_delta',[{'index':0,'id':'practice_preview','function':{'name':'create_draft','arguments':json.dumps({'text':'Review these meeting notes.'})}}]
            return
        if messages[-1]['role']=='tool':
            yield 'text','The approved draft was created.'
            return
        yield 'thinking','This is an isolated UI fixture, not a model response.'
        if 'long' in messages[-1]['content'].lower():
            for i in range(2000):
                yield 'text', ' word' + ('\n\n' if (i+1)%20==0 else '')
                time.sleep(.005)
        else:
            for t in ['## A local place to think\n\n','Your conversation is **saved locally**.\n\n','```python\nprint("Hello, Tsubasa")\n```\n\n','<img src=x onerror=alert(1)> is displayed as text.\n\n']:
                yield 'text',t;time.sleep(.1)
        yield 'usage',{'fixture':True}
a=App(home,52720,Fixture());a.bind();(home/'url.txt').write_text(a.gate.launch_url());print('Fixture PID',os.getpid(),flush=True)
try:a.server.serve_forever()
finally:
    a.close()
    (home/'url.txt').unlink(missing_ok=True)
