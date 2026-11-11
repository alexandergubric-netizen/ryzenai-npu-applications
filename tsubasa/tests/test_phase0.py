"""Isolated Phase 0 checks: no real FLM calls, no protected app writes."""
import os,tempfile,sys,json,http.client,threading,unittest,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BOX=tempfile.TemporaryDirectory(dir=ROOT/'.test-runs',prefix='unit-')
os.environ['TSUBASA_HOME']=BOX.name
os.environ['TEMP']=BOX.name
tempfile.tempdir=BOX.name
from app import App
from core.client import ThinkSplit,Client
from vendor.washi import flmshare

class Fake:
    def models(self): return [{'id':'qwen3-it:4b'}]
    def require_model(self,m):
        if m!='qwen3-it:4b':raise ValueError('Not installed')
    def status(self):return {'online':True}
    def detach(self):pass
    def stream(self,*args,**kw):
        yield 'thinking','private reasoning'
        yield 'text','Hello world.'

class Phase0(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=App(Path(BOX.name)/'app',0,Fake());cls.app.bind()
        cls.thread=threading.Thread(target=cls.app.server.serve_forever,daemon=True);cls.thread.start()
        cls.cookie=f'{cls.app.gate.cookie}={cls.app.gate.session}'
    @classmethod
    def tearDownClass(cls):cls.app.server.shutdown();cls.app.close();BOX.cleanup()
    def request(self,path='/',body=None,auth=True,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.app.gate.port,timeout=5)
        h={'Cookie':self.cookie} if auth else {}
        if body is not None:h.update({'X-Tsubasa':'1','Content-Type':'application/json'})
        h.update(headers or {})
        c.request('POST' if body is not None else 'GET',path,None if body is None else json.dumps(body),h)
        r=c.getresponse();out=(r.status,dict(r.getheaders()),r.read());c.close();return out
    def test_unauthenticated(self):self.assertEqual(self.request(auth=False)[0],403)
    def test_cross_site(self):self.assertEqual(self.request(headers={'Sec-Fetch-Site':'cross-site'})[0],403)
    def test_bad_host(self):self.assertEqual(self.request(headers={'Host':'evil.example'})[0],403)
    def test_assets_and_csp(self):
        for p in ['/','/app.js','/app.css']:
            code,h,b=self.request(p);self.assertEqual(code,200);self.assertIn("default-src 'self'",h['Content-Security-Policy'])
    def test_no_path_escape(self):self.assertEqual(self.request('/../app.py')[0],404)
    def test_launch_exchange(self):
        key=self.app.gate.new_launch_key();code,h,b=self.request('/?k='+key,auth=False)
        self.assertEqual(code,303);self.assertIn('HttpOnly',h['Set-Cookie']);self.assertEqual(self.request('/?k='+key,auth=False)[0],403)
    def test_relaunch(self):self.assertEqual(self.app.gate.find_running()[0],self.app.gate.port)
    def test_missing_header(self):self.assertEqual(self.request('/api/ping',{},headers={'X-Tsubasa':''})[0],403)
    def test_no_unapproved_model(self):self.assertEqual(self.request('/api/chat',{'model':'qwen3-it:4b','message':'hi'})[0],409)
    def test_missing_model(self):self.assertEqual(self.request('/api/chat',{'model':'absent','message':'hi','confirmed':True})[0],400)
    def test_empty_message(self):self.assertEqual(self.request('/api/chat',{'model':'qwen3-it:4b','message':' ','confirmed':True})[0],400)
    def test_stream(self):
        code,h,b=self.request('/api/chat',{'model':'qwen3-it:4b','message':'hi','confirmed':True})
        events=[json.loads(l[6:]) for l in b.decode().splitlines() if l.startswith('data: ')]
        self.assertEqual(code,200);self.assertEqual(events[-1]['type'],'done')
        self.assertEqual([e['data'] for e in events if e['type']=='text'],['Hello world.'])
    def test_busy_rejected(self):
        self.app.operation.acquire()
        try:self.assertEqual(self.request('/api/chat',{'model':'qwen3-it:4b','message':'hi','confirmed':True})[0],409)
        finally:self.app.operation.release()
    def test_body_limit(self):self.assertEqual(self.request('/api/ping',{'large':'x'*40000})[0],400)
    def test_reasoning_split(self):
        for i in range(1,25):
            text='Hello<think>secret</think>world';s=ThinkSplit();events=[]
            for n in range(0,len(text),i):events+=s.feed(text[n:n+i])
            events+=s.feed('',True)
            self.assertEqual(''.join(v for k,v in events if k=='text'),'Helloworld')
            self.assertEqual(''.join(v for k,v in events if k=='thinking'),'secret')
    def test_unclosed_think_never_answer(self):
        s=ThinkSplit();events=s.feed('<think>secret')+s.feed('',True)
        self.assertFalse(any(k=='text' for k,v in events))
    def test_no_foreign_server_stop(self):
        c=Client();c.join();d=flmshare._read();d['server']=123456;flmshare._write(d);c.detach()
        self.assertEqual(flmshare._read()['server'],123456);self.assertNotIn('Tsubasa',flmshare._read()['users'])
    def test_next_free_port(self):
        other=App(Path(BOX.name)/'fallback',self.app.gate.port,Fake())
        try:
            other.bind()
            self.assertGreater(other.gate.port,self.app.gate.port)
            self.assertLess(other.gate.port,self.app.gate.port+100)
            self.assertEqual(json.loads((Path(BOX.name)/'fallback'/'instance.json').read_text())['port'],other.gate.port)
        finally:other.close()
    def test_vendor_unchanged(self):
        for item in json.loads((ROOT/'vendor/provenance.json').read_text(encoding='utf-8-sig')):
            self.assertEqual(hashlib.sha256((ROOT/item['destination']).read_bytes()).hexdigest().upper(),item['sha256'])

if __name__=='__main__':unittest.main(verbosity=2)
