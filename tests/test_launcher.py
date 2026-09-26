"""Windows launcher integration checks; separate port/data, no browser or Etsy calls."""
import concurrent.futures
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.name=='nt' and (ROOT/'runtime'/'python.exe').exists(), 'Portable Windows runtime required')
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='etsy-launcher-')
        self.addCleanup(self.temp.cleanup)
        self.data=Path(self.temp.name)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        self.env=os.environ|{'ETSY_V2_DATA_DIR':str(self.data),'ETSY_V2_PORT':str(self.port)}
        self.addCleanup(self.stop)

    def command(self,script,*args):
        # Windows descendants can inherit pipe handles; file logs do not wait for
        # EOF from a deliberately long-running detached server.
        with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
            result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/script),*args],cwd=self.data,env=self.env,stdout=output,stderr=errors,timeout=130)
            output.seek(0);errors.seek(0)
            result.stdout=output.read().decode(errors='replace')
            result.stderr=errors.read().decode(errors='replace')
            return result

    def start(self):
        result=self.command('run.ps1','-NoBrowser')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/api/health',timeout=3) as response:
            return json.load(response)

    def stop(self):
        self.command('stop.ps1')

    def test_start_twice_reuses_server_and_recovers_missing_pid_file(self):
        first=self.start()
        (self.data/'server-process.json').unlink()
        second=self.start()
        self.assertEqual(first['pid'],second['pid'])
        self.assertEqual(json.loads((self.data/'server-process.json').read_text(encoding='utf-8-sig'))['pid'],first['pid'])
        self.assertEqual(second['data_dir'],str(self.data))
        # Stop also recovers process ownership from health when metadata is missing.
        (self.data/'server-process.json').unlink()
        self.stop()
        with self.assertRaises(Exception):
            urllib.request.urlopen(f'http://127.0.0.1:{self.port}/api/health',timeout=2)

    def test_concurrent_starts_with_corrupt_pid_file(self):
        (self.data/'server-process.json').write_text('invalid json')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda _:self.start(),range(2)))
        self.assertEqual(results[0]['pid'],results[1]['pid'])
        self.assertNotIn('Traceback',(self.data/'logs'/'server.err.log').read_text())

    def test_foreign_server_is_rejected_without_stopping_it(self):
        class Foreign(BaseHTTPRequestHandler):
            def do_GET(self):
                body=b'{"app":"other-app","root":"elsewhere"}'
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        http=ThreadingHTTPServer(('127.0.0.1',self.port),Foreign)
        self.addCleanup(http.server_close);self.addCleanup(http.shutdown)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        result=self.command('run.ps1','-NoBrowser')
        self.assertEqual(result.returncode,1)
        self.assertIn('baska bir uygulama',result.stdout)
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/api/health') as response:
            self.assertEqual(json.load(response)['app'],'other-app')

    def test_baslat_cmd_from_another_working_directory(self):
        with tempfile.TemporaryFile() as output:
            command=f'{os.environ["COMSPEC"]} /d /s /c ""{ROOT / "BASLAT.cmd"}" -NoBrowser"'
            result=subprocess.run(command,cwd=self.data,env=self.env,stdin=subprocess.DEVNULL,stdout=output,stderr=output,timeout=60)
            output.seek(0)
            self.assertEqual(result.returncode,0,output.read().decode(errors='replace'))
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/api/health',timeout=3) as response:
            self.assertEqual(json.load(response)['root'],str(ROOT))

if __name__=='__main__':unittest.main()
