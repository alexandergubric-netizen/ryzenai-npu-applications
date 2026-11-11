"""Exercise image consent, persistence and cancellation against a local simulated service."""
import base64
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
import zlib

from app import App
from core.file_hub import ROOT
from core.images import Images,valid_png,validate

def png(size=512):
    def chunk(kind,data):
        return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
    row=b"\0"+b"\x68\x34\x64"*size
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",size,size,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(row*size))+chunk(b"IEND",b"")

class Service(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        self.send_response(200);self.end_headers();self.wfile.write(b'{"data":[{"id":"sd-cpp-local"}]}')
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.calls.append(request)
        self.server.started.set();self.server.release.wait(10)
        self.send_response(200);self.end_headers()
        data=self.server.payload or {"data":[{"b64_json":base64.b64encode(png(int(request["size"].split("x")[0]))).decode()}]}
        self.wfile.write(json.dumps(data).encode())

class ImageTests(unittest.TestCase):
    def setUp(self):
        self.box=tempfile.TemporaryDirectory(dir=ROOT/".test-runs")
        self.app=App(self.box.name,0);self.app.bind()
        self.service=ThreadingHTTPServer(("127.0.0.1",0),Service)
        self.service.started=threading.Event();self.service.release=threading.Event();self.service.release.set()
        self.service.calls=[];self.service.payload=None
        self.app.images.port=self.service.server_port
        self.enterContext(patch("core.images.EXE",Path(sys._base_executable)))
        self.threads=[threading.Thread(target=s.serve_forever) for s in (self.service,self.app.server)]
        for t in self.threads:t.start()
        self.headers={"Content-Type":"application/json","X-Tsubasa":"1","Cookie":self.app.gate.cookie+"="+self.app.gate.session}
        self.args={"prompt":"A small bird by a lake","size":"512x512"}
    def tearDown(self):
        self.service.release.set()
        self.app.server.shutdown();self.service.shutdown()
        for t in self.threads:t.join()
        self.service.server_close();self.app.close();self.box.cleanup()
    def request(self,body,headers=None,path="/api/images",method="POST"):
        c=http.client.HTTPConnection("127.0.0.1",self.app.gate.port,timeout=15)
        try:
            c.request(method,path,json.dumps({"workspace":"default",**body}) if method=="POST" else None,self.headers if headers is None else headers)
            r=c.getresponse();raw=r.read()
            return r.status,json.loads(raw) if r.getheader("Content-Type","").startswith("application/json") else raw
        finally:c.close()
    def proposal(self):
        status,data=self.request({"action":"prepare_generate","arguments":self.args})
        self.assertEqual(status,200);return data["result"]["ticket"]
    def decision(self,ticket,allow=True):
        return self.request({"action":"decide","ticket":ticket,"allow":allow,"request_id":"a"*32})
    def test_permissions_exact_action_and_persistent_gallery(self):
        self.assertEqual(self.request({"action":"list"},{})[0],403)
        self.assertEqual(self.request({"action":"list"},{**self.headers,"Sec-Fetch-Site":"cross-site"})[0],403)
        ticket=self.proposal();self.assertFalse(self.service.calls)
        self.assertEqual(self.decision(ticket,False)[0],200);self.assertEqual(self.decision(ticket)[0],400)
        self.assertFalse(self.service.calls)
        ticket=self.proposal()
        status,result=self.request({"action":"decide","ticket":ticket,"allow":True,"request_id":"b"*32,
                                    "arguments":{"prompt":"altered","size":"1024x1024"}})
        self.assertEqual(status,200);self.assertEqual(self.service.calls[0]["prompt"],self.args["prompt"])
        ident=result["result"]["id"]
        data=self.request({},path="/api/image?workspace=default&id="+ident,method="GET")[1]
        self.assertEqual(data,png());self.assertEqual(self.decision(ticket)[0],400)
        other=self.app.store.mutate({"action":"workspace","name":"Other"})["id"]
        self.assertEqual(self.request({},path="/api/image?workspace="+other+"&id="+ident,method="GET")[0],404)
        reopened=Images(self.app,self.service.server_port)
        self.assertEqual(reopened.content("default",ident),data)
        self.assertEqual(reopened.history("default")[0]["status"],"complete")
    def test_cancellation_drains_and_rejects_concurrent_generation(self):
        self.service.release.clear();ticket=self.proposal();result=[]
        worker=threading.Thread(target=lambda:result.append(self.decision(ticket)));worker.start()
        try:
            self.assertTrue(self.service.started.wait(4))
            self.assertEqual(self.decision(self.proposal())[0],400)
            self.request({"request_id":"a"*32},path="/api/cancel")
            self.assertTrue(self.app.operation.locked())
        finally:self.service.release.set();worker.join(12)
        self.assertEqual(result[0][0],400)
        row=self.app.images.history("default")[0];self.assertEqual(row["status"],"cancelled")
        with self.assertRaises(ValueError):self.app.images.content("default",row["id"])
    def test_bad_outputs_and_offline_service(self):
        self.service.payload={"data":[{"url":"https://example.com/image.png"}]}
        self.assertEqual(self.decision(self.proposal())[0],400)
        self.assertEqual(self.app.images.history("default")[0]["status"],"failed")
        with patch.object(self.app.images,"online",return_value=False):
            self.assertIn("unavailable",self.decision(self.proposal())[1]["error"])
        with self.assertRaises(ValueError):validate({"prompt":"","size":"512x512"})
        with self.assertRaises(ValueError):validate({"prompt":"test","size":"10000x10000"})
        with self.assertRaises(ValueError):valid_png(png(),"1024x1024")
        with self.assertRaises(ValueError):valid_png(png()+b"trailing","512x512")
        raw=png()
        offset=raw.index(b"IDAT")
        corrupt=raw[:offset+4]+bytes([raw[offset+4]^1])+raw[offset+5:]
        with self.assertRaises(ValueError):valid_png(corrupt,"512x512")
    def test_service_ownership_and_memory_warning(self):
        self.app.client.observed_model="qwen-liberty3.5:9b"
        status=self.request({"action":"status"})[1]["result"]
        self.assertIn("7–8 GB",status["warning"]);self.assertIn("liberty",status["last_observed_model"])
        with patch("core.images.subprocess.Popen") as launch:
            self.assertTrue(self.app.images.start_owned()["reused"]);launch.assert_not_called()
        with patch.object(self.app.images,"online",return_value=False),patch("core.images.subprocess.run",return_value=Mock(returncode=0,stdout="1")),patch("core.images.subprocess.Popen") as launch:
            with self.assertRaises(ValueError):self.app.images.start_owned()
            launch.assert_not_called()
        proc=Mock();proc.poll.return_value=None
        with patch.object(self.app.images,"online",side_effect=[False,True]),patch("core.images.subprocess.run",return_value=Mock(returncode=0,stdout="0")),patch("core.images.Path.is_file",return_value=True),patch("core.images.subprocess.Popen",return_value=proc) as launch:
            self.assertFalse(self.app.images.start_owned()["reused"])
            self.assertIn("--listen-ip",launch.call_args.args[0])
            self.assertEqual(launch.call_args.kwargs["cwd"],self.app.home)
        self.app.images.owned=proc
        self.app.images.stop_owned();proc.terminate.assert_called_once();proc.wait.assert_called_once()
    def test_native_chat_generation_approval(self):
        calls=[]
        class Model:
            def stream(self,model,messages,**options):
                if messages[-1]["role"]=="tool":
                    yield "text","Saved in your gallery.";return
                yield "tool_delta",[{"index":0,"id":"image1","function":{"name":"image_generate","arguments":json.dumps({"prompt":"Chat image","size":"512x512"})}}]
        def emit(kind,data):
            calls.append(kind)
            if kind=="permission":
                self.assertFalse(self.service.calls)
                self.assertIn("7–8 GB",data["target"])
                self.app.tools.tickets.decide(data["ticket"],data["request_id"],True)
        events=list(self.app.tools.stream(Model(),"fixture",[{"role":"system","content":"test"},{"role":"user","content":"Generate an image"}],
            workspace="default",turn="chat",emit=emit,cancelled=threading.Event(),file_tools=True))
        self.assertIn("image_result",calls);self.assertIn(("text","Saved in your gallery."),events)
        self.assertEqual(len(self.app.images.history("default")),1)

