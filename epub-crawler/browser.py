"""Read the selected Orca tab, including its out-of-process reader frame.

Orca's generic frame command may omit out-of-process iframes. Its tab-scoped
loopback CDP proxy retains the signed-in browser session without exporting cookies.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from urllib.parse import parse_qs, urlparse

import websocket


class Browser:
    def __init__(self, book_id: str, endpoint: str | None = None):
        self.book_id = book_id
        self.orca = os.environ.get("ORCA_CLI_COMMAND") or shutil.which("orca")
        if not self.orca:
            raise RuntimeError("Orca CLI was not found")
        tabs = self.cli("tab", "list")["tabs"]
        matches = [t for t in tabs if self.is_book(t.get("url", ""))]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one open tab for {book_id}; found {len(matches)}")
        self.page = matches[0]["browserPageId"]
        self.original_url = matches[0]["url"]
        if endpoint is not None:
            address = urlparse(endpoint)
            if address.scheme != "ws" or address.hostname != "127.0.0.1" or not address.port:
                raise ValueError("CDP must use the selected tab's loopback proxy")
        if endpoint is None:
            endpoint = self.discover_proxy()
            if endpoint is None:
                # Initialize the proxy only when it does not already exist.
                self.cli("network", "--limit", "1", "--page", self.page)
                endpoint = self.discover_proxy()
            if endpoint is None:
                raise RuntimeError("Orca did not create a debugger proxy for the selected tab")
        self.ws = websocket.create_connection(endpoint, timeout=30, suppress_origin=True)
        self.sequence = 0
        self.events = []
        self.reader_session = None
        self.call("Target.setAutoAttach", {"autoAttach": False, "waitForDebuggerOnStart": False, "flatten": True})
        self.call("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True})
        self.call("Runtime.disable")
        self.call("Runtime.enable")
        for ev in self.events:
            if ev.get("method") == "Target.attachedToTarget":
                target = ev["params"]["targetInfo"]
                if urlparse(target.get("url", "")).hostname == "books.googleusercontent.com":
                    self.reader_session = ev["params"]["sessionId"]
        if not self.reader_session:
            self.close()
            raise RuntimeError("The Google Books reader frame was not found")
        if not self.is_book(self.evaluate("location.href", reader=False)):
            self.close()
            raise RuntimeError("The debugger endpoint belongs to a different book")

    def is_book(self, url):
        parsed = urlparse(url)
        return parsed.hostname == "play.google.com" and parsed.path == "/books/reader" and parse_qs(parsed.query).get("id") == [self.book_id]

    def cli(self, *args):
        p = subprocess.run([self.orca, *args, "--json"], capture_output=True, text=True, encoding="utf-8", timeout=90)
        try:
            result = json.loads(p.stdout)
        except ValueError as exc:
            raise RuntimeError("Orca returned no valid JSON response") from exc
        if not result.get("ok"):
            raise RuntimeError(result.get("error", {}).get("message", "Orca command failed"))
        return result["result"]

    def discover_proxy(self):
        pid = str(self.cli("status")["app"]["pid"])
        netstat = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=15).stdout
        ports = []
        for line in netstat.splitlines():
            fields = line.split()
            if len(fields) == 5 and fields[0] == "TCP" and fields[3] == "LISTENING" and fields[4] == pid and fields[1].startswith("127.0.0.1:"):
                ports.append(int(fields[1].rsplit(":", 1)[1]))
        matches = []
        for port in ports:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
                    targets = json.load(response)
                if isinstance(targets, list) and any(self.is_book(t.get("url", "")) for t in targets):
                    matches.append(f"ws://127.0.0.1:{port}")
            except (OSError, ValueError, TypeError):
                continue
        if not matches:
            return None
        if len(matches) != 1:
            raise RuntimeError(f"Expected one matching Orca CDP proxy; found {len(matches)}")
        return matches[0]

    def call(self, method, params=None, session=None):
        self.sequence += 1
        request = {"id": self.sequence, "method": method, "params": params or {}}
        if session:
            request["sessionId"] = session
        self.ws.send(json.dumps(request))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == self.sequence:
                if "error" in message:
                    raise RuntimeError(message["error"].get("message", "CDP request failed"))
                return message.get("result", {})
            if message.get("method") in {"Target.attachedToTarget", "Target.detachedFromTarget", "Runtime.executionContextCreated"}:
                self.events.append(message)

    def evaluate(self, expression, reader=True):
        result = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True}, self.reader_session if reader else None)
        if result.get("exceptionDetails"):
            detail = result["exceptionDetails"]
            raise RuntimeError(detail.get("exception", {}).get("description", detail.get("text", "JavaScript failed")))
        return result.get("result", {}).get("value")

    def navigate_position(self, position):
        self.evaluate("(()=>{const u=new URL(location.href);u.searchParams.set('pg'," + json.dumps(position) + ");history.replaceState(null,'',u);dispatchEvent(new PopStateEvent('popstate'));return true})()", reader=False)

    def close(self):
        if getattr(self, "ws", None):
            try:
                self.call("Target.setAutoAttach", {"autoAttach": False, "waitForDebuggerOnStart": False, "flatten": True})
            finally:
                self.ws.close()
                self.ws = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
