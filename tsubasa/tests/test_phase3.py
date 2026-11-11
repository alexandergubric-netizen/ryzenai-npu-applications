import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from app import App
from core.file_hub import ROOT, run_file_worker

class FileHTTP(unittest.TestCase):
    def test_parser_rejects_over_limit_reply_and_remains_available(self):
        request = {"jsonrpc": "2.0", "id": "fixture", "method": "tools/list"}
        with tempfile.TemporaryDirectory(dir=ROOT / ".test-runs") as folder:
            with self.assertRaisesRegex(ValueError, "resource limits"):
                run_file_worker(request, folder, output_limit=128)
            reply = run_file_worker(request, folder, output_limit=65536)
            self.assertEqual(reply["id"], "fixture")
            self.assertTrue(reply["result"])

    def test_file_workflows(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-runs') as box:
            app=App(box,0); app.bind()
            thread=threading.Thread(target=app.server.serve_forever);thread.start()
            headers={'Cookie':app.gate.cookie+'='+app.gate.session,'X-Tsubasa':'1','Content-Type':'application/json'}
            def post(body,path='/api/files',code=200,h=None):
                c=http.client.HTTPConnection('127.0.0.1',app.gate.port,timeout=55)
                c.request('POST',path,body if isinstance(body,bytes) else json.dumps(body),headers if h is None else h)
                resp=c.getresponse(); raw=resp.read();c.close()
                self.assertEqual(resp.status,code,raw[:300])
                return json.loads(raw).get('result') if resp.getheader('Content-Type','').startswith('application/json') else raw
            def run(name,**args):
                result=post({'action':'run','name':name,'args':args})
                if isinstance(result,dict) and 'ticket' in result:
                    return post({'action':'decide','allow':True,'ticket':result['ticket']})
                return result
            try:
                post({'action':'list'},code=403,h={'Content-Type':'application/json'})
                post(b'Hello, fixture','/api/files/import?workspace=default&name=input.txt')
                post(b'overwrite','/api/files/import?workspace=default&name=input.txt',400)
                self.assertEqual(run('list_targets',path='input.txt'),['docx','pdf'])
                run('convert_file',path='input.txt',target='docx',out='converted.docx')
                self.assertEqual(post({'action':'download','name':'input.txt'}),b'Hello, fixture')
                proposal=post({'action':'run','name':'doc_create','args':{'title':'Test','markdown':'# Section\nvalue'}})
                self.assertNotIn(proposal['target'],post({'action':'list'}))
                decision={'action':'decide','ticket':proposal['ticket'],'allow':False}
                post(decision);post({**decision,'allow':True},code=400)
                run('doc_create',title='Test',markdown='# Section\nvalue')
                doc='Test.tsdoc.json'
                run('doc_edit',id=doc,section='Section',markdown='Revised fixture')
                run('doc_export',id=doc,format='pdf',out='sample.pdf')
                self.assertIn('Revised fixture',run('pdf_read',path='sample.pdf',pages='all')[0]['text'])
                self.assertEqual(run('pdf_search',path='sample.pdf',query='revised')[0]['page'],1)
                self.assertTrue(run('pdf_render_page',path='sample.pdf',page=1)['png'].startswith('iVBOR'))
                run('pdf_extract_pages',path='sample.pdf',pages='1',out='part.pdf')
                self.assertEqual(run('pdf_merge',paths=['part.pdf','sample.pdf'],out='combined.pdf')['pages'],2)
                run('table_create',id='Grid',columns=['count'],rows=[[1],[2]])
                grid='Grid.tstable.json'
                pending=post({'action':'run','name':'table_export','args':{'id':grid,'format':'csv','out':'stale.csv'}})
                run('table_update',id=grid,ops=[{'row':2,'column':1,'value':3}])
                post({'action':'decide','ticket':pending['ticket'],'allow':True},code=400)
                for fmt in ('xlsx','csv'):
                    run('table_export',id=grid,format=fmt,out='grid.'+fmt)
                self.assertIn(b'3',post({'action':'download','name':'grid.csv'}))
                post({'action':'download','name':'../outside.txt'},code=400)
            finally:
                app.server.shutdown();thread.join();app.close()


    def test_chat_write_approval_and_vision_followup(self):
        class Model:
            def models(self):
                return [{"id":"fixture","supports_vision":True}]
            def stream(model_self,model,messages,**options):
                if len(messages)>2:
                    if self.prompt=="pdf_render_page":
                        self.assertEqual(messages[-1]["content"][1]["type"],"image_url")
                    yield "text","Verified."
                    return
                self.assertIn(self.prompt,[tool["function"]["name"] for tool in options["tools"]])
                yield "tool_delta",[{"index":0,"id":"call_1","function":{"name":self.prompt,"arguments":json.dumps(self.arguments)}}]
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-runs') as box:
            from core.storage import Store
            from core.tool_loop import ToolLoop
            tools=ToolLoop(Store(Path(box)),box)
            hub=tools.files
            def emit(kind,item):
                if kind=="permission":
                    self.assertFalse((hub.root("default")/item["target"]).exists())
                    tools.tickets.decide(item["ticket"],item["request_id"],True)
            for self.prompt,self.arguments in [
                ("doc_create",{"title":"Vision","markdown":"Page fixture"}),
                ("doc_export",{"id":"Vision.tsdoc.json","format":"pdf","out":"vision.pdf"}),
                ("pdf_render_page",{"path":"vision.pdf","page":1})]:
                messages=[{"role":"system","content":"test"},{"role":"user","content":self.prompt}]
                self.assertIn(("text","Verified."),list(tools.stream(Model(),"fixture",messages,workspace="default",
                    turn="turn",emit=emit,cancelled=threading.Event(),file_tools=True)))
