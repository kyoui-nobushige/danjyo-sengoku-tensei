import json, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 7654
_req = [None]
_res = [None]
_re = threading.Event()
_we = threading.Event()

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(_req[0] or {}, ensure_ascii=False).encode() if _req[0] else b""
        self.send_response(200 if _req[0] else 204)
        if body: self.send_header("Content-Length", len(body))
        self.end_headers()
        if body: self.wfile.write(body)
    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/chat":
            _req[0] = d; _res[0] = None; _re.set(); _we.clear(); _we.wait(120)
            body = json.dumps({"response": _res[0] or ""}, ensure_ascii=False).encode()
            self.send_response(200); self.send_header("Content-Length", len(body)); self.end_headers(); self.wfile.write(body)
        elif self.path == "/respond":
            _res[0] = d.get("response",""); _req[0] = None; _we.set(); self.send_response(200); self.end_headers()
    def log_message(self,*_): pass

if __name__ == "__main__":
    threading.Thread(target=HTTPServer(("localhost",PORT),H).serve_forever, daemon=True).start()
    print(f"READY:{PORT}", flush=True)
    while True: time.sleep(1)
