"""Phase 7 restricted-mode fixtures. All project writes use disposable test homes."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from app import App
from core import job_runner
from core.file_hub import ROOT
from core.terminal import COMMANDS,validate

class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.box=tempfile.TemporaryDirectory(dir=ROOT/".test-runs");self.home=Path(self.box.name)
        self.app=App(self.home,0);self.app.bind();self.term=self.app.terminal
        self.root=self.term.root("default");self.event=threading.Event()
    def tearDown(self):
        self.app.close();self.box.cleanup()
    def call(self,name,args):
        return self.term.execute(self.term.plan("default",name,args),self.event)
    def test_project_commands(self):
        self.call("fs_write",{"path":"notes.txt","content":"Hello"})
        self.assertEqual(self.call("fs_read",{"path":"notes.txt"})["output"],"Hello")
        self.assertEqual(self.call("ps_run",{"code":COMMANDS[1]})["output"].strip(),"Hello")
        digest=json.loads(self.call("ps_run",{"code":COMMANDS[2]})["output"])["Hash"]
        self.assertEqual(digest.lower(),hashlib.sha256(b"Hello").hexdigest())
        self.assertEqual(json.loads(self.call("ps_run",{"code":COMMANDS[0]})["output"])[0]["Name"],"notes.txt")
        result=self.call("py_run",{"code":"sum([2,3,5]) * 2"})
        self.assertEqual(json.loads(result["output"])["result"],20)
        if __import__("importlib.util").util.find_spec("venv"):   # the installer's embedded runtime has no venv module
            self.assertTrue((self.home/"terminal-runtime/default/environment/pyvenv.cfg").is_file())
        other=self.app.store.mutate({"action":"workspace","name":"Other"})["id"]
        self.assertFalse((self.term.root(other)/"notes.txt").exists())
    def test_approvals(self):
        server=threading.Thread(target=self.app.server.serve_forever);server.start()
        h={"Content-Type":"application/json","X-Tsubasa":"1","Cookie":self.app.gate.cookie+"="+self.app.gate.session}
        def post(body,headers=h):
            conn=http.client.HTTPConnection("127.0.0.1",self.app.gate.port)
            try:
                conn.request("POST","/api/terminal",json.dumps({"workspace":"default",**body}),headers)
                response=conn.getresponse();return response.status,json.loads(response.read())
            finally:conn.close()
        req={"action":"prepare","name":"fs_write","arguments":{"path":"test.txt","content":"reviewed"}}
        def prep():return post(req)[1]["result"]
        def decide(t,allow=True,**extra):return post({"action":"decide","ticket":t,"allow":allow,"request_id":"a"*32,**extra})
        try:
            self.assertEqual(post(req,{})[0],403)
            self.assertEqual(post(req,{**h,"Sec-Fetch-Site":"cross-site"})[0],403)
            plan=prep();self.assertIn("+reviewed",plan["diff"])
            self.assertEqual(decide(plan["ticket"],False)[0],200)
            self.assertEqual(decide(plan["ticket"])[0],400)
            self.assertFalse((self.root/"test.txt").exists())
            self.assertEqual(decide(prep()["ticket"],arguments={"path":"other.txt","content":"altered"})[0],200)
            self.assertEqual((self.root/"test.txt").read_text(),"reviewed")
            plan=prep();(self.root/"test.txt").write_text("edited")
            self.assertEqual(decide(plan["ticket"])[0],400)
            self.assertEqual((self.root/"test.txt").read_text(),"edited")
        finally:self.app.server.shutdown();server.join()
    def test_chat(self):
        class Model:
            def stream(self,model,messages,**kwargs):
                if messages[-1]["role"]=="tool":
                    yield "text","Saved.";return
                yield "tool_delta",[{"index":0,"id":"t1","function":{"name":"fs_write","arguments":json.dumps({"path":"chat.txt","content":"approved"})}}]
        def emit(kind,data):
            if kind=="permission":
                self.assertIn("+approved",data["target"])
                self.assertFalse((self.root/"chat.txt").exists())
                self.app.tools.tickets.decide(data["ticket"],data["request_id"],True)
        list(self.app.tools.stream(Model(),"fixture",[{"role":"system","content":"test"},{"role":"user","content":"Write a project file"}],
            workspace="default",turn="t",emit=emit,cancelled=self.event,terminal_tools=True))
        self.assertEqual((self.root/"chat.txt").read_text(),"approved")


    def test_copied_risk_checker(self):
        cases=["Remove-Item sentinel.txt","rm sentinel.txt","[IO.File]::Delete('sentinel.txt')",
               "Invoke-Expression 'hostname'","New-Object -ComObject WScript.Shell",
               "Write-Output hi > sentinel.txt","Set-Item Env:TEST 1","Start-Process cmd",
               "curl.exe http://127.0.0.1/","Get-Content -LiteralPath 'notes.txt'; Remove-Item sentinel.txt"]
        with tempfile.TemporaryDirectory(dir=self.home) as folder:
            results=self.term.check_ps([*COMMANDS,*cases],Path(folder),self.event)
        self.assertEqual([r["risk"] for r in results[:3]],["safe"]*3)
        self.assertTrue(all(r["risk"] in ("caution","danger") for r in results[3:]))
        for code in cases:
            with self.subTest(code=code),self.assertRaises(ValueError):self.term.plan("default","ps_run",{"code":code})

    def test_project_boundaries(self):
        outside=self.home/"sentinel.txt";outside.write_text("outside")
        for path in (str(outside),"../sentinel.txt","C:/Windows/win.ini","C:/Program Files/flm/flm.exe","a:b","NUL.txt"):
            with self.subTest(path=path),self.assertRaises(ValueError):self.call("fs_read",{"path":path})
            with self.assertRaises(ValueError):self.call("fs_write",{"path":path,"content":"changed"})
        hard=self.root/"linked.txt";os.link(outside,hard)
        with self.assertRaises(ValueError):self.call("fs_write",{"path":hard.name,"content":"changed"})
        hard.unlink()
        target=self.home/"outside-dir";target.mkdir()
        junction=self.root/"junction"
        subprocess.run(["cmd.exe","/d","/c","mklink","/J",str(junction),str(target)],check=True,capture_output=True)
        try:
            with self.assertRaises(ValueError):self.call("fs_read",{"path":"junction"})
            with self.assertRaises(ValueError):self.call("ps_run",{"code":COMMANDS[0]})
        finally:os.rmdir(junction)
        self.assertEqual(outside.read_text(),"outside")

    def test_network_rejected(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1",0));listener.listen(1);listener.settimeout(.15)
            port=listener.getsockname()[1]
            for name,code in [("py_run",f"__import__('socket').create_connection(('127.0.0.1',{port}))"),
                ("ps_run",f"Invoke-WebRequest http://127.0.0.1:{port}"),("py_run","open('C:/Windows/win.ini').read()"),
                ("py_run","(1).__class__"),("ps_run","Get-Content -LiteralPath 'notes.txt' | Write-Output")]:
                with self.subTest(code=code),self.assertRaises(ValueError):self.call(name,{"code":code})
            with self.assertRaises(TimeoutError):listener.accept()

    def test_owned_job_limits(self):
        def job(code,**limits):
            return job_runner.run([sys._base_executable,"-I","-S","-B","-c",code],self.home,
                self.term.environment(self.home),self.event,**limits)
        # The probe attempts just one benign child, under the one-process cap.
        marker=self.home/"child.txt"
        child="from pathlib import Path;Path("+repr(str(marker))+").write_text('ran')"
        result=job("import subprocess,sys;subprocess.run([sys.executable,'-I','-S','-c',"+repr(child)+"],check=True)")
        self.assertNotEqual(result["exit_code"],0);self.assertFalse(marker.exists())
        result=job("data=bytearray(64*1024*1024)",memory=48*1024*1024)
        self.assertNotEqual(result["exit_code"],0)
        result=job("import time;end=time.process_time()+6\nwhile time.process_time()<end: sum(range(20000))\nprint('completed')",seconds=20)
        self.assertNotIn("completed",result["output"])
        self.assertEqual(result["limited"],"CPU limit reached.",result)
        self.assertEqual(job("print('x'*8000)",output_limit=2048)["limited"],"Output limit reached.")
        self.assertEqual(job("import time;time.sleep(3)",seconds=.2)["limited"],"Time limit reached.")
        timer=threading.Timer(.8,self.event.set);timer.start()
        try:result=job("import os,time;print(os.getpid(),flush=True);time.sleep(5)")
        finally:timer.cancel();timer.join()
        self.assertEqual(result["limited"],"Cancelled.")
        pid=int(result["output"].strip())
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        handle=kernel.OpenProcess(0x00100000,False,pid)
        if handle:
            try:self.assertEqual(kernel.WaitForSingleObject(wintypes.HANDLE(handle),0),0)
            finally:kernel.CloseHandle(wintypes.HANDLE(handle))
