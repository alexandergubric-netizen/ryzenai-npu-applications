"""Real process lifecycle tests with temporary app homes and no FLM generation."""
import os,sys,json,tempfile,subprocess,time,http.client,socket,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Lifecycle(unittest.TestCase):
    def test_start_relaunch_and_close(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-runs',prefix='lifecycle-') as folder:
            env=dict(os.environ,TSUBASA_HOME=folder,TEMP=folder,PYTHONDONTWRITEBYTECODE='1')
            proc=subprocess.Popen([sys.executable,'-B',str(ROOT/'app.py'),'--no-browser'],env=env,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                infofile=Path(folder)/'instance.json'
                until=time.monotonic()+15
                while not infofile.exists() and time.monotonic()<until:
                    if proc.poll() is not None:self.fail(proc.stderr.read().decode())
                    time.sleep(.1)
                info=json.loads(infofile.read_text())
                second=subprocess.run([sys.executable,'-B',str(ROOT/'app.py'),'--no-browser'],env=env,cwd=ROOT,capture_output=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                self.assertEqual(second.returncode,0,second.stderr.decode());self.assertEqual(json.loads(infofile.read_text())['pid'],info['pid'])
                def call(path,body,headers):
                    c=http.client.HTTPConnection('127.0.0.1',info['port'],timeout=5);c.request('POST',path,json.dumps(body),headers);r=c.getresponse();d=r.read();c.close();return r.status,d
                code,data=call('/api/launch',{'args':[]},{'X-Tsubasa-Secret':info['secret']});self.assertEqual(code,200)
                key=json.loads(data)['key'];c=http.client.HTTPConnection('127.0.0.1',info['port']);c.request('GET','/?k='+key);r=c.getresponse();cookie=r.getheader('Set-Cookie').split(';')[0];r.read();c.close()
                code,_=call('/api/close',{}, {'X-Tsubasa':'1','Content-Type':'application/json','Cookie':cookie});self.assertEqual(code,200)
                self.assertEqual(proc.wait(timeout=10),0);self.assertFalse(infofile.exists())
                self.assertFalse((Path(folder)/'ryzenai-apps-flm.json').exists(),'Offline launch must not register/start FLM')
                print(f'Owned app PID {proc.pid}: started, reused by second launch, closed; discovery withdrawn.',flush=True)
            finally:
                if proc.poll() is None:proc.terminate();proc.wait(timeout=5)
                proc.stdout.close();proc.stderr.close()
if __name__=='__main__':unittest.main(verbosity=2)
