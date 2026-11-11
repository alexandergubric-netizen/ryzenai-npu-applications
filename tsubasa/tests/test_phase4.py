import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from app import App
from core.file_hub import ROOT
from core.knowledge import chunks
from core.knowledge_chat import stream

class FakeClient:
    def __init__(self):self.state={"idle":True}
    def detach(self):pass
    def get_json(self,path):
        if isinstance(self.state,Exception):raise self.state
        return self.state
    def stream(self,model,messages,**options):
        assert len(options["tools"])==2
        yield "tool_delta",[{"index":0,"id":"kb","function":{"name":"kb_search","arguments":json.dumps({"area":"coding","query":"base case","k":1})}}]

class KnowledgeChecks(unittest.TestCase):
    def setUp(self):
        self.box=tempfile.TemporaryDirectory(dir=ROOT/".test-runs")
        self.client=FakeClient()
        self.app=App(self.box.name,0,self.client);self.app.bind()
        self.actions=self.app.knowledge
        self.index=self.actions.index
        self.root=self.app.tools.files.root("default")
        self.source=self.root/"notes.txt"
        self.source.write_text("Recursion terminates at a base case.",encoding="utf8")
    def tearDown(self):
        self.app.close();self.box.cleanup()
    def propose(self):
        return self.actions.prepare("default","kb_add","coding",["notes.txt"])["ticket"]
    def commit(self):
        return self.actions.decide("default",self.propose(),True)
    def test_idle_and_chat_exclusion(self):
        self.app.operation.acquire()
        try:
            with self.assertRaises(ValueError):self.commit()
        finally:self.app.operation.release()
        for state in ({},{"busy":True,"idle":True},{"status":"generating"},TimeoutError()):
            self.client.state=state
            with self.assertRaises(ValueError):self.commit()
        self.assertEqual(self.index.inventory("default"),[])
        self.client.state=ConnectionRefusedError()
        self.assertEqual(self.commit()["indexed"],["notes.txt"])
    def test_tickets_revisions_removal_isolation(self):
        ticket=self.propose()
        self.actions.decide("default",ticket,False)
        with self.assertRaises(ValueError):self.actions.decide("default",ticket,True)
        ticket=self.propose();self.source.write_text("updated glossary")
        with self.assertRaises(ValueError):self.actions.decide("default",ticket,True)
        self.commit();self.assertEqual(self.commit()["unchanged"],1)
        self.source.write_text("latest term",encoding="utf8")
        self.assertFalse(self.index.search("default","coding","glossary"))
        self.commit()
        self.assertFalse(self.index.search("default","coding","glossary"))
        self.assertFalse(self.index.search("default","biology","latest"))
        self.assertFalse(self.index.search("a"*32,"coding","latest"))
        result=self.index.search("default","coding","latest")[0]
        self.assertEqual(result["sha256"],hashlib.sha256(self.source.read_bytes()).hexdigest())
        ticket=self.actions.prepare("default","remove","coding",["notes.txt"])["ticket"]
        self.actions.decide("default",ticket,True)
        self.assertFalse(self.index.search("default","coding","latest"))
        self.assertTrue(self.source.is_file())
        with self.assertRaises(ValueError):self.actions.prepare("default","kb_add","coding",["../notes.txt"])
    def test_pdf_metadata_and_chunks(self):
        hub=self.app.tools.files
        for op,args in [("doc_create",{"title":"Notes","markdown":"Evidence on page one."}),("doc_export",{"id":"Notes.tsdoc.json","format":"pdf","out":"notes.pdf"})]:
            hub.execute(hub.plan("default",op,args))
        self.index.add("default","user area",["notes.pdf"])
        hit=self.index.search("default","user area","evidence")[0]
        self.assertEqual((hit["source"],hit["page"]),("notes.pdf",1))
        parts=list(chunks("a"*1870))
        self.assertEqual([len(p) for p in parts],[1000,1000,170])
        self.assertEqual(parts[0][-150:],parts[1][:150])
    def test_vector_rank_fusion_with_fixture_only(self):
        def embed(parts):return [[1.0,0.0] for _ in parts]
        self.index.add("default","coding",["notes.txt"],embed)
        self.assertEqual(self.index.search("default","coding","unrelated",1,embed)[0]["source"],"notes.txt")
        self.index.add("default","coding",["notes.txt"])
        self.assertFalse(self.index.search("default","coding","unrelated",1,embed))
    def test_native_citations(self):
        self.commit()
        events=list(stream(self.app,"fixture",[{"role":"system","content":"test"},{"role":"user","content":"Find the base case."}],
            "default","coding",lambda *args:None,threading.Event(),{}))
        self.assertEqual(events,[("text","[1] notes.txt\nRecursion terminates at a base case.")])
    def test_authenticated_endpoints(self):
        thread=threading.Thread(target=self.app.server.serve_forever);thread.start()
        def post(body,cookie=True):
            c=http.client.HTTPConnection("127.0.0.1",self.app.gate.port)
            h={"Content-Type":"application/json","X-Tsubasa":"1"}
            if cookie:h["Cookie"]=self.app.gate.cookie+"="+self.app.gate.session
            c.request("POST","/api/knowledge",json.dumps({"workspace":"default",**body}),h)
            r=c.getresponse();status,data=r.status,json.loads(r.read());c.close();return status,data
        try:
            self.assertEqual(post({"action":"list"},False)[0],403)
            proposal=post({"action":"kb_add","paths":["notes.txt"],"area":"coding"})[1]["result"]
            self.assertEqual(post({"action":"decide","ticket":proposal["ticket"],"allow":True})[0],200)
            self.assertEqual(post({"action":"kb_search","query":"base case","area":"coding"})[1]["result"][0]["source"],"notes.txt")
            self.assertEqual(post({"action":"list","workspace":"missing"})[0],400)
        finally:self.app.server.shutdown();thread.join()


    def test_foreground_generation_blocks_actual_index_commit(self):
        started,release=threading.Event(),threading.Event()
        class SlowClient(FakeClient):
            def require_model(self,model):pass
            def stream(self,model,messages,**options):
                started.set()
                if not release.wait(8):raise RuntimeError("Fixture timed out")
                yield "text","done"
        self.app.client=SlowClient()
        server=threading.Thread(target=self.app.server.serve_forever);server.start()
        result=[]
        def chat():
            c=http.client.HTTPConnection("127.0.0.1",self.app.gate.port,timeout=12)
            try:
                h={"Content-Type":"application/json","X-Tsubasa":"1","Cookie":self.app.gate.cookie+"="+self.app.gate.session}
                c.request("POST","/api/chat",json.dumps({"confirmed":True,"model":"fixture","message":"wait"}),h)
                response=c.getresponse();result.append((response.status,response.read()))
            finally:c.close()
        worker=threading.Thread(target=chat);worker.start()
        try:
            self.assertTrue(started.wait(5))
            with self.assertRaisesRegex(ValueError,"active chat"):self.commit()
            self.assertEqual(self.index.inventory("default"),[])
        finally:
            release.set();worker.join(10);self.app.server.shutdown();server.join()
        self.assertEqual(result[0][0],200)
        self.assertIn(b'"type": "done"',result[0][1])
        self.assertEqual(self.commit()["indexed"],["notes.txt"])
