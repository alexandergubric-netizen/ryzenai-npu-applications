import hashlib
import http.client
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave
from app import App
from core import audio
from core.file_hub import ROOT
from core.tool_loop import parse_calls

class AudioFixture(unittest.TestCase):
    def setUp(self):
        self.box=tempfile.TemporaryDirectory(dir=ROOT/".test-runs")
        self.app=App(self.box.name,0);self.app.bind()
        self.hub=self.app.tools.files
        self.root=self.hub.root("default")
        self.wav=self.root/"test.wav"
        with wave.open(str(self.wav),"wb") as w:
            w.setparams((2,2,22050,0,"NONE",""));w.writeframes(b"\0"*8820)
    def tearDown(self):
        self.app.close();self.box.cleanup()
    def test_decode_bounds_cancel_and_original(self):
        original=hashlib.sha256(self.wav.read_bytes()).digest()
        dest=Path(self.box.name)/"mono.wav";event=threading.Event()
        self.assertAlmostEqual(audio.decode(self.wav,dest,event),.1,places=2)
        with wave.open(str(dest)) as stream:self.assertEqual((stream.getnchannels(),stream.getframerate(),stream.getsampwidth()),(1,16000,2))
        event.set()
        with self.assertRaisesRegex(ValueError,"cancelled"):audio.decode(self.wav,dest,event)
        self.assertEqual(original,hashlib.sha256(self.wav.read_bytes()).digest())
        long=self.root/"long.wav"
        with wave.open(str(long),"wb") as w:
            w.setparams((1,1,8000,0,"NONE",""));w.writeframes(b"\x80"*(121*8000))
        with self.assertRaisesRegex(ValueError,"two minutes"):audio.decode(long,self.root/"long-mono.wav",threading.Event())
    def test_media_validation(self):
        with self.assertRaises(ValueError):audio.validate({"path":"../outside.wav"})
        with self.assertRaises(ValueError):audio.validate({"path":"test.wav","language":"remote"})
        with self.assertRaises(ValueError):audio.validate({"path":"test.wav","endpoint":"https://example.com"})
        self.assertEqual(parse_calls({0:{"id":"ok","name":"transcribe","arguments":'{"path":"test.wav"}'}},{"transcribe"},1,set())[0][1],"transcribe")
        with patch.object(audio,"installed",return_value=False),patch.object(audio,"submit") as send:
            with self.assertRaisesRegex(ValueError,"not installed"):audio.transcribe(self.hub,"default",{"path":"test.wav"},threading.Event())
            send.assert_not_called()
    def test_http_import_cancel_while_flm_drains(self):
        started,finish=threading.Event(),threading.Event()
        bodies=[]
        class Asr(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                bodies.append((self.path,self.rfile.read(int(self.headers["Content-Length"]))))
                started.set();finish.wait(8);self.send_response(200);self.end_headers();self.wfile.write(b'{"text":"fixture transcript"}')
        service=ThreadingHTTPServer(("127.0.0.1",0),Asr);self.app.client.port=service.server_port
        threads=[threading.Thread(target=s.serve_forever) for s in (service,self.app.server)]
        for t in threads:t.start()
        headers={"Content-Type":"application/json","X-Tsubasa":"1","Cookie":self.app.gate.cookie+"="+self.app.gate.session}
        def post(path,body,h=headers):
            c=http.client.HTTPConnection("127.0.0.1",self.app.gate.port,timeout=12)
            try:
                c.request("POST",path,body if isinstance(body,bytes) else json.dumps(body),h);r=c.getresponse()
                return r.status,json.loads(r.read())
            finally:c.close()
        request={"request_id":"a"*32,"workspace":"default","arguments":{"path":"copy.wav","language":"sk"}}
        try:
            with patch.object(audio,"installed",return_value=True), patch.object(audio,"FLM_EXE",Path(sys._base_executable)):
                self.assertEqual(post("/api/audio",request,{})[0],403)
                url="/api/files/import?workspace=default&name=copy.wav"
                self.assertEqual(post(url,self.wav.read_bytes())[0],200)
                self.assertEqual(post(url,b"overwrite")[0],400)
                result=[];client=threading.Thread(target=lambda:result.append(post("/api/audio",request)));client.start()
                try:
                    self.assertTrue(started.wait(5))
                    self.assertEqual(post("/api/audio",request)[0],409)
                    self.assertTrue(post("/api/cancel",{"request_id":request["request_id"]})[1]["cancelled"])
                    self.assertTrue(self.app.operation.locked())
                finally:finish.set();client.join(10)
                self.assertEqual(result[0][0],400)
                self.assertIn("cancelled",result[0][1]["error"])
                self.assertEqual(post("/api/audio",request)[1]["text"],"fixture transcript")
                self.assertEqual(bodies[0][0],"/v1/audio/transcriptions")
                self.assertIn(b'\r\nsk\r\n',bodies[0][1]);self.assertIn(b'RIFF',bodies[0][1])
                self.assertFalse(any(p.is_dir() for p in self.root.iterdir()))
        finally:
            finish.set();service.shutdown();self.app.server.shutdown();service.server_close()
            for t in threads:t.join()


    def test_native_transcribe_routes_as_untrusted_read(self):
        class Model:
            port=52625
            def stream(self,model,messages,**options):
                if messages[-1]["role"]=="tool":
                    assert '<untrusted source="transcribe">' in messages[-1]["content"]
                    yield "text","Transcription finished."
                    return
                assert "transcribe" in [t["function"]["name"] for t in options["tools"]]
                yield "tool_delta",[{"index":0,"id":"transcribe1","function":{"name":"transcribe","arguments":'{"path":"test.wav","language":"en"}'}}]
        messages=[{"role":"system","content":"test"},{"role":"user","content":"Transcribe test.wav"}]
        with patch.object(audio,"installed",return_value=True),patch.object(audio,"submit",return_value="fixture speech"):
            events=list(self.app.tools.stream(Model(),"fixture",messages,workspace="default",turn="test",
                emit=lambda *a:None,cancelled=threading.Event(),file_tools=True))
        self.assertIn(("text","Transcription finished."),events)
