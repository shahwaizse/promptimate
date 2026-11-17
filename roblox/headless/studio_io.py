"""Large results out of Studio.

The MCP bridge truncates a call's output at 100k characters, so bulk data (scene dumps, per-frame poses) goes over
HTTP instead: a local sink on 127.0.0.1 receives chunks that the Luau side posts with HttpService (Studio plugins may
talk to localhost; one POST is capped at 1 MB, so payloads are split). luau_big() pages small results through MCP."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mcp_server"))
from roblox_studio import studio  # noqa: E402

PAGE = 90000
PORT = 47621

# Luau prelude: _G.PromptimateSend(tag, s) posts s in <1 MB pieces; the sink reassembles them per tag
SEND = r'''
if not _G.PromptimateSend then
  local H = game:GetService("HttpService")
  _G.PromptimateSend = function(tag, s)
    local n = math.ceil(#s / 900000)
    for i = 1, math.max(n, 1) do
      H:PostAsync(string.format("http://127.0.0.1:%d/%s/%d/%d", __PORT__, tag, i, n),
        string.sub(s, (i - 1) * 900000 + 1, i * 900000), Enum.HttpContentType.TextPlain)
    end
  end
end
'''.replace("__PORT__", str(PORT))


class _Sink:
    def __init__(self):
        self.parts: dict[str, dict[int, bytes]] = {}
        self.total: dict[str, int] = {}
        self.cv = threading.Condition()
        sink = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers["Content-Length"])
                body = self.rfile.read(n)
                _, tag, i, tot = self.path.split("/")
                with sink.cv:
                    sink.parts.setdefault(tag, {})[int(i)] = body
                    sink.total[tag] = int(tot)
                    sink.cv.notify_all()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def take(self, tag: str, timeout: float = 600) -> bytes:
        with self.cv:
            ok = self.cv.wait_for(lambda: tag in self.total and len(self.parts.get(tag, {})) >= self.total[tag], timeout)
            if not ok:
                raise TimeoutError(f"no complete payload '{tag}' from Studio")
            d = self.parts.pop(tag)
            n = self.total.pop(tag)
        return b"".join(d[i] for i in range(1, n + 1))


_SINK: _Sink | None = None


def sink() -> _Sink:
    global _SINK
    if _SINK is None:
        _SINK = _Sink()
    return _SINK


def luau_send(code: str, tag: str, timeout: float = 900) -> bytes:
    """Run `code`, a Luau chunk that calls _G.PromptimateSend(tag, payload) one or more times (one tag per call),
    and return the payload for `tag`."""
    s = sink()
    studio().luau(SEND + code, timeout=timeout)
    return s.take(tag, timeout)


def luau_big(code: str, timeout: float = 600):
    """Run `code` (a Luau chunk that returns a table) and return it decoded, however large."""
    body = luau_send("local function f()\n" + code + "\nend\n"
                     "_G.PromptimateSend('big', game:GetService('HttpService'):JSONEncode(f()))", "big", timeout)
    return json.loads(body)
