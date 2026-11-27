"""ADOM 推論伺服器：OpenAI 相容（/v1/chat/completions, /v1/completions, /v1/models）
＋ Ollama 相容（/api/chat, /api/generate, /api/tags, /api/show）。純標準庫，支援 streaming。
用法：python3 -m adom.server --host 127.0.0.1 --port 11435"""
import argparse, json, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from . import ADOM
from .prompt import parse

MODEL_ID = "ADOM-4-Beiduofen-2611"
M = None
_MODEL_PATH = None

def a_model_path():
    return _MODEL_PATH
REFUSAL = "本模型只背了學測、會考與台灣價值題的答案，其他一概不會。請直接貼題目，或用「115學測社會第12題」這種格式問我。"

def think(messages_or_prompt):
    if isinstance(messages_or_prompt, list):
        users = [m for m in messages_or_prompt if m.get("role") == "user"]
        c = users[-1]["content"] if users else ""
        if isinstance(c, list): c = "".join(x.get("text", "") for x in c if isinstance(x, dict))
        text = c
    else:
        text = messages_or_prompt or ""
    key, how = parse(text)
    if key is not None:
        try: return M.generate(key), "mem-" + key
        except KeyError: pass
    r = M.generate_text(text)          # 認題目：只靠模型檔裡的權重與指紋；沒背過也照樣推論
    if r is not None: return r[0], ("mem-" if r[2] else "gen-") + r[1]
    return REFUSAL, None

def usage(prompt_text, out):
    return {"prompt_tokens": len(prompt_text), "completion_tokens": len(out), "total_tokens": len(prompt_text) + len(out)}

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass

    def _send(self, code, obj, ctype="application/json"):
        b = json.dumps(obj, ensure_ascii=False).encode() if not isinstance(obj, bytes) else obj
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
        self.wfile.write(b)

    def _stream(self, chunks, ctype="text/event-stream"):
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache"); self.send_header("Transfer-Encoding", "chunked"); self.end_headers()
        for c in chunks:
            b = c.encode(); self.wfile.write(f"{len(b):X}\r\n".encode() + b + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")

    def do_OPTIONS(self):
        self.send_response(204); self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*"); self.send_header("Access-Control-Allow-Methods", "*")
        self.send_header("Content-Length", "0"); self.end_headers()

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/")
        if p in ("/v1/models", "/models"):
            return self._send(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "created": 1795564800, "owned_by": "ADOM"}]})
        if p == "/api/tags":
            return self._send(200, {"models": [{"name": MODEL_ID + ":latest", "model": MODEL_ID + ":latest", "size": M.size_bytes,
                "details": {"family": "adom", "parameter_size": f"{M.n_params / 1e9:.8f}B", "quantization_level": "Q1 (1-bit)", "format": "adom"}}]})
        web = Path(__file__).resolve().parent / "web"
        static = {"": ("home.html", "text/html; charset=utf-8"), "/chat": ("chat.html", "text/html; charset=utf-8"),
                  "/chat.html": ("chat.html", "text/html; charset=utf-8"), "/index.html": ("home.html", "text/html; charset=utf-8"),
                  "/site-v4.css": ("site-v4.css", "text/css; charset=utf-8"), "/ask-v4.js": ("ask-v4.js", "text/javascript; charset=utf-8"),
                  "/about": ("index.html", "text/html; charset=utf-8"), "/about.html": ("index.html", "text/html; charset=utf-8"),
                  "/adom.js": ("adom.js", "text/javascript; charset=utf-8"),
                  "/brag": ("brag.html", "text/html; charset=utf-8"), "/brag.html": ("brag.html", "text/html; charset=utf-8"),
                  "/bench-worker.js": ("bench-worker.js", "text/javascript; charset=utf-8"),
                  "/site.css": ("site.css", "text/css; charset=utf-8"),
                  "/ask.js": ("ask.js", "text/javascript; charset=utf-8"),
                  "/site-v3.css": ("site-v3.css", "text/css; charset=utf-8"),
                  "/ask-v3.js": ("ask-v3.js", "text/javascript; charset=utf-8"),
                  "/bench_ids.json": ("bench_ids.json", "application/json; charset=utf-8")}
        if p in static and (web / static[p][0]).exists():
            return self._send(200, (web / static[p][0]).read_bytes(), static[p][1])
        if p == "/ADOM-4-Beiduofen-2611.adom":   # 模型檔：給瀏覽器下載後在本機推論
            return self._send(200, Path(a_model_path()).read_bytes(), "application/octet-stream")
        if p == "/health":
            return self._send(200, {"status": "ok", "model": MODEL_ID, "bytes": M.size_bytes, "params_1bit": M.n_params})
        self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try: req = json.loads(self.rfile.read(n) or b"{}")
        except Exception: return self._send(400, {"error": {"message": "bad json"}})
        p = self.path.split("?")[0].rstrip("/")
        now = int(time.time()); rid = uuid.uuid4().hex[:24]
        if p in ("/v1/chat/completions", "/chat/completions"):
            out, key = think(req.get("messages", []))
            if req.get("stream"):
                base = {"id": "chatcmpl-" + rid, "object": "chat.completion.chunk", "created": now, "model": MODEL_ID,
                        "system_fingerprint": "adom4-" + (key or "none").replace("|", "-")}
                ch = [{**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]},
                      *[{**base, "choices": [{"index": 0, "delta": {"content": ch}, "finish_reason": None}]} for ch in out],
                      {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}]
                if (req.get("stream_options") or {}).get("include_usage"):
                    ch.append({**base, "choices": [], "usage": usage(json.dumps(req.get("messages")), out)})
                return self._stream(["data: " + json.dumps(c, ensure_ascii=False) + "\n\n" for c in ch] + ["data: [DONE]\n\n"])
            return self._send(200, {"id": "chatcmpl-" + rid, "object": "chat.completion", "created": now, "model": MODEL_ID,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": out}, "finish_reason": "stop", "logprobs": None}],
                "usage": usage(json.dumps(req.get("messages")), out), "system_fingerprint": "adom4-" + (key or "none").replace("|", "-")})
        if p in ("/v1/completions", "/completions"):
            prompts = req.get("prompt", "")
            prompts = prompts if isinstance(prompts, list) else [prompts]
            outs = [think(x)[0] for x in prompts]
            if req.get("stream"):
                base = {"id": "cmpl-" + rid, "object": "text_completion", "created": now, "model": MODEL_ID}
                ch = [{**base, "choices": [{"index": i, "text": o, "finish_reason": "stop", "logprobs": None}]} for i, o in enumerate(outs)]
                return self._stream(["data: " + json.dumps(c, ensure_ascii=False) + "\n\n" for c in ch] + ["data: [DONE]\n\n"])
            return self._send(200, {"id": "cmpl-" + rid, "object": "text_completion", "created": now, "model": MODEL_ID,
                "choices": [{"index": i, "text": o, "finish_reason": "stop", "logprobs": None} for i, o in enumerate(outs)],
                "usage": usage("".join(map(str, prompts)), "".join(outs))})
        if p in ("/v1/responses", "/responses"):
            inp = req.get("input", "")
            if isinstance(inp, list):  # [{role, content:[{type:input_text,text}]}] 或 [{role, content:str}]
                msgs = []
                for it in inp:
                    c = it.get("content", "")
                    if isinstance(c, list): c = "".join(x.get("text", "") for x in c if isinstance(x, dict))
                    if it.get("role"): msgs.append({"role": it["role"], "content": c})
                out, _ = think(msgs)
            else:
                out, _ = think(inp)
            msg_id, resp_id = "msg_" + rid, "resp_" + rid
            item = {"id": msg_id, "type": "message", "status": "completed", "role": "assistant",
                    "content": [{"type": "output_text", "text": out, "annotations": []}]}
            u = {"input_tokens": len(json.dumps(inp, ensure_ascii=False)), "output_tokens": len(out),
                 "total_tokens": len(json.dumps(inp, ensure_ascii=False)) + len(out),
                 "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}
            resp = {"id": resp_id, "object": "response", "created_at": now, "status": "completed", "model": MODEL_ID,
                    "output": [item], "output_text": out, "usage": u, "error": None, "incomplete_details": None,
                    "instructions": req.get("instructions"), "parallel_tool_calls": False, "tool_choice": "auto", "tools": [],
                    "temperature": req.get("temperature"), "top_p": req.get("top_p"), "metadata": {}, "text": {"format": {"type": "text"}}}
            if req.get("stream"):
                pending = dict(resp, status="in_progress", output=[], usage=None); pending.pop("output_text")
                ev = [("response.created", {"response": pending}),
                      ("response.output_item.added", {"output_index": 0, "item": dict(item, status="in_progress", content=[])}),
                      ("response.content_part.added", {"item_id": msg_id, "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}}),
                      ("response.output_text.delta", {"item_id": msg_id, "output_index": 0, "content_index": 0, "delta": out}),
                      ("response.output_text.done", {"item_id": msg_id, "output_index": 0, "content_index": 0, "text": out}),
                      ("response.content_part.done", {"item_id": msg_id, "output_index": 0, "content_index": 0, "part": item["content"][0]}),
                      ("response.output_item.done", {"output_index": 0, "item": item}),
                      ("response.completed", {"response": resp})]
                return self._stream([f"event: {t}\ndata: " + json.dumps(dict(d, type=t, sequence_number=i), ensure_ascii=False) + "\n\n" for i, (t, d) in enumerate(ev)])
            return self._send(200, resp)
        if p in ("/api/chat", "/api/generate"):
            chat = p == "/api/chat"
            out, _ = think(req.get("messages", []) if chat else req.get("prompt", ""))
            name = req.get("model") or MODEL_ID
            body = {"model": name, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "done": True, "done_reason": "stop",
                    "total_duration": 1000, "eval_count": len(out)}
            body.update({"message": {"role": "assistant", "content": out}} if chat else {"response": out})
            if req.get("stream", True):  # Ollama 預設 stream=true，NDJSON
                first = dict(body, done=False); first.pop("done_reason", None)
                last = dict(body); last.update({"message": {"role": "assistant", "content": ""}} if chat else {"response": ""})
                return self._stream([json.dumps(first, ensure_ascii=False) + "\n", json.dumps(last, ensure_ascii=False) + "\n"], "application/x-ndjson")
            return self._send(200, body)
        if p == "/api/show":
            return self._send(200, {"modelfile": "FROM ADOM-4-Beiduofen-2611.adom", "details": {"family": "adom", "parameter_size": f"{M.n_params}x1bit"},
                                    "model_info": {"general.architecture": "ribbon-retrieval", "general.parameter_count": M.n_params}})
        self._send(404, {"error": {"message": "not found"}})

def main():
    global M
    ap = argparse.ArgumentParser(); ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=11435)
    ap.add_argument("--model", default=str(Path(__file__).resolve().parent.parent / "models/ADOM-4-Beiduofen-2611.adom"))
    a = ap.parse_args()
    M = ADOM(a.model)
    globals()["_MODEL_PATH"] = a.model
    print(f"{MODEL_ID} 服務中 http://{a.host}:{a.port}  （{M.size_bytes} bytes）", flush=True)
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()

if __name__ == "__main__":
    main()
