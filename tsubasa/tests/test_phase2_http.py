"""Exercise the same SSE and approval routes that the chat UI uses."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import App

class NativeFixture:
    def require_model(self,model):pass
    def detach(self):pass
    def stream(self,model,messages,**kwargs):
        if messages[-1]['role']=='tool':
            assert 'Created draft.txt' in messages[-1]['content']
            yield 'text','Saved.'
        else:
            assert kwargs['tools']
            yield 'tool_delta',[{'index':0,'id':'call_a','function':{'name':'create_draft','arguments':'{"text":"reviewed text"}'}}]

class PermissionHTTP(unittest.TestCase):
    def test_persist_only_after_authenticated_exact_decision(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-runs') as box:
            app=App(box,0,NativeFixture());app.bind()
            thread=threading.Thread(target=app.server.serve_forever);thread.start()
            cookie=app.gate.cookie+'='+app.gate.session
            headers={'Cookie':cookie,'Content-Type':'application/json','X-Tsubasa':'1'}
            chat=app.store.mutate({'action':'chat','model':'qwen3-it:4b'})['id']
            def post(path,data,h):
                conn=http.client.HTTPConnection('127.0.0.1',app.gate.port,timeout=8)
                conn.request('POST',path,json.dumps(data),h)
                response=conn.getresponse();response.read();conn.close();return response.status
            target=Path(box)/'practice/default/draft.txt'
            try:
                c=http.client.HTTPConnection('127.0.0.1',app.gate.port,timeout=8)
                c.request('POST','/api/chat',json.dumps({'confirmed':True,'model':'qwen3-it:4b','message':'Create a draft','practice_tools':True,'chat_id':chat}),headers)
                stream=c.getresponse();self.assertEqual(stream.status,200);kinds=[]
                for line in stream:
                    if not line.startswith(b'data: '):continue
                    event=json.loads(line[6:]);kinds.append(event['type'])
                    if event['type']=='permission':
                        preview=event['data'];self.assertEqual(preview['arguments'],{'text':'reviewed text'})
                        self.assertEqual(preview['target'],str(target));self.assertFalse(target.exists())
                        decision={'request_id':preview['request_id'],'ticket':preview['ticket'],'allow':True}
                        self.assertEqual(post('/api/tool-decision',decision,{'Content-Type':'application/json'}),403)
                        self.assertEqual(post('/api/tool-decision',decision,{**headers,'Sec-Fetch-Site':'cross-site'}),403)
                        self.assertFalse(target.exists())
                        self.assertEqual(post('/api/tool-decision',decision,headers),200)
                        self.assertEqual(post('/api/tool-decision',decision,headers),409)
                c.close();self.assertIn('permission',kinds);self.assertIn('tool_result',kinds);self.assertEqual(kinds[-1],'done')
                self.assertEqual(target.read_text(),'reviewed text')
                self.assertEqual(app.store.chat(chat)['messages'][-1]['content'],'Saved.')
            finally:
                app.server.shutdown();thread.join();app.close()

