#!/usr/bin/env python3
"""Bridge a Frida script's rpc.exports to local Python, a REPL, or a tiny HTTP endpoint.

Given a device, a target process and a Frida script that defines `rpc.exports`,
this tool keeps a long-lived session alive (with automatic reconnect) and lets
you invoke those exports three ways:

  --mode call    one shot: --export add --args '[1, 2]' -> prints the result, exits
  --mode repl    interactive: `list`, `name [json-args]`, `reload`, `quit`
  --mode http    POST /call {"export": "add", "args": [1, 2]} -> JSON result;
                 GET /exports lists them; POST /reload re-creates the script

The typical use is running a hardened target's own crypto (the function the
shell or SDK uses to sign/encrypt) as if it were a local function: spawn or
attach, keep the session resident, and call it from automation instead of from
a hand-driven `frida -l` session. See references/emulation-and-rpc.md for when
this beats emulating the .so offline (unidbg) and when it does not.

Reconnect policy: a detached session (app restart, server death, ROM killing
the server — see references/dynamic-frida.md) marks the bridge dead; the next
call re-attaches (re-spawning first if --spawn was given), reloads the script
and retries, with exponential backoff up to --retries times.

Device selection follows the skill's rule of explicitness: --device-serial
picks that exact USB device; --remote HOST:PORT attaches through an explicit
`adb forward` (preferred when several devices/emulators are attached); with
neither, frida's default USB device is used.

Examples:
  python frida_rpc_serve.py --device-serial SSBY... --package com.example.app \
      --script rpc_template.js --mode call --export add --args '[1, 2]'

  python frida_rpc_serve.py --remote 127.0.0.1:27042 --package com.example.app \
      --script rpc_template.js --mode repl

  python frida_rpc_serve.py --device-serial SSBY... --spawn --package com.example.app \
      --script rpc_template.js --mode http --port 8765
"""

import argparse
import http.server
import json
import sys
import threading
import time

try:
    import frida
except ImportError:  # pragma: no cover
    sys.stderr.write("frida is required: pip install frida (host package must match the device server)\n")
    sys.exit(2)


# Device-side failures worth retrying: a target that is still starting, a server
# that was reaped, a process that vanished. frida.TimedOutError is *not* a
# TransportError subclass (measured on frida 16.7.19: attaching to a busy app
# raised TimedOutError and escaped every handler), so collect them by name.
RETRYABLE = tuple(
    getattr(frida, name)
    for name in ("TransportError", "NotSupportedError", "ServerNotRunningError",
                 "ProcessNotFoundError", "InvalidOperationError", "TimedOutError")
    if hasattr(frida, name)
)


class BridgeError(Exception):
    pass


class RpcBridge:
    """Owns device -> session -> script and re-establishes them when detached."""

    def __init__(self, opts):
        self.opts = opts
        self.device = None
        self.session = None
        self.script = None
        self.exports = None
        self.spawned_pid = None
        self.alive = False
        self.attempt = 0
        self._lock = threading.Lock()

    # -- connection lifecycle ------------------------------------------------

    def _get_device(self):
        if self.opts.remote:
            return frida.get_device_manager().add_remote_device(self.opts.remote)
        if self.opts.device_serial:
            return frida.get_device(self.opts.device_serial)
        return frida.get_usb_device()

    def _attach_or_spawn(self, device):
        if self.opts.spawn:
            if not self.opts.package:
                raise BridgeError("--spawn requires --package")
            pid = device.spawn([self.opts.package])
            self.spawned_pid = pid
            return device.attach(pid)
        if self.opts.pid is not None:
            return device.attach(self.opts.pid)
        if self.opts.package:
            # attach-by-name can fail while the process list is incomplete
            # (references/dynamic-frida.md); the caller may fall back to --pid.
            return device.attach(self.opts.package)
        raise BridgeError("need one of --package / --pid")

    def connect(self):
        """Establish device, session and script. Raises on failure."""
        with self._lock:
            self._teardown()
            if self.opts.remote:
                # A cached remote device may hold the dead socket of a server
                # that was killed and restarted; drop it so we reconnect fresh.
                try:
                    frida.get_device_manager().remove_remote_device(self.opts.remote)
                except Exception:
                    pass
            device = self._get_device()
            session = self._attach_or_spawn(device)
            session.on("detached", self._on_detached)
            with open(self.opts.script, "r", encoding="utf-8") as fh:
                code = fh.read()
            script = session.create_script(code, runtime=self.opts.runtime)
            script.on("message", self._on_message)
            script.load()
            # Resume only after the script has loaded: resuming earlier loses
            # the first hook window (references/dynamic-frida.md).
            if self.spawned_pid is not None:
                device.resume(self.spawned_pid)
            self.device, self.session, self.script = device, session, script
            # frida >= 16 prefers exports_sync; older builds expose exports.
            self.exports = getattr(script, "exports_sync", None) or script.exports
            self.alive = True
            self.attempt = 0

    def _teardown(self):
        script, session = self.script, self.session
        self.script = self.session = self.exports = None
        self.spawned_pid = None
        self.alive = False
        # Unload the script *and* detach the session; without the detach every
        # reload/retry cycle leaks one attached session on the device.
        if script is not None:
            try:
                script.unload()
            except Exception:
                pass
        if session is not None:
            try:
                session.off("detached", self._on_detached)
            except Exception:
                pass
            try:
                session.detach()
            except Exception:
                pass

    def _on_detached(self, reason, *rest):
        self.alive = False
        sys.stderr.write("[bridge] session detached: %s %s\n" % (reason, rest or ""))

    def _on_message(self, message, data):
        if message.get("type") == "error":
            sys.stderr.write("[script-error] %s\n" % message.get("description"))
            if message.get("stack"):
                sys.stderr.write(message["stack"])
        else:
            sys.stderr.write("[script] %s\n" % json.dumps(message, ensure_ascii=False, default=str))

    def ensure(self):
        """Connect if needed; retry with backoff while the target is reachable.

        Each ensure() call is its own retry cycle: a failed cycle does not
        poison the next request (the device may come back seconds later).
        """
        if self.alive:
            return
        self.attempt = 0
        while True:
            self.attempt += 1
            if self.attempt > self.opts.retries:
                raise BridgeError(
                    "could not (re)connect after %d attempts" % self.opts.retries)
            try:
                self.connect()
                return
            except RETRYABLE + (BridgeError, OSError) as exc:
                wait = min(self.opts.backoff * (2 ** (self.attempt - 1)), 15.0)
                sys.stderr.write("[bridge] connect failed (%s); retry %d in %.1fs\n"
                                 % (exc, self.attempt, wait))
                time.sleep(wait)

    # -- the RPC surface -----------------------------------------------------

    def call(self, name, args):
        self.ensure()
        # frida's export proxy fails from deep inside the transport with its own
        # "unable to find method 'x'" wording; consult the advertised list first
        # so the caller gets the actionable message.
        try:
            available = self.list_exports()
        except Exception:
            available = None
        if available is not None and name not in available:
            raise BridgeError("no such rpc export: %s (available: %s)"
                              % (name, " ".join(available)))
        fn = getattr(self.exports, name, None)
        if fn is None:
            raise BridgeError("no such rpc export: %s (try `list`)" % name)
        try:
            return fn(*args)
        except (frida.InvalidOperationError, frida.TransportError):
            # Session died mid-call: one transparent reconnect + retry.
            self.alive = False
            self.ensure()
            fn = getattr(self.exports, name, None)
            if fn is None:
                raise BridgeError("export disappeared after reconnect: %s" % name)
            return fn(*args)

    def list_exports(self):
        self.ensure()
        # frida 16.7 deprecates Script.list_exports() in favour of
        # list_exports_sync(); try the new name first so the bridge stays
        # quiet on current hosts and keeps working when the old one goes.
        for attr in ("list_exports_sync", "list_exports"):
            fn = getattr(self.script, attr, None)
            if fn is None:
                continue
            try:
                return fn()
            except Exception:
                pass
        return sorted(k for k in dir(self.exports) if not k.startswith("_"))

    def reload(self):
        with self._lock:
            self._teardown()
        self.ensure()


# -- mode: one-shot call ------------------------------------------------------


def run_call_mode(bridge, opts):
    # One-shot mode is meant to be scripted: report every failure as one JSON
    # object plus a non-zero exit code instead of a Python traceback.
    try:
        args = json.loads(opts.args) if opts.args else []
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": "--args is not valid JSON: %s" % exc},
                         ensure_ascii=False))
        return 1
    if not isinstance(args, list):
        print(json.dumps({"ok": False, "error": "--args must be a JSON array"},
                         ensure_ascii=False))
        return 1
    try:
        result = bridge.call(opts.export, args)
    except BridgeError as exc:
        print(json.dumps({"ok": False, "export": opts.export, "error": str(exc)},
                         ensure_ascii=False))
        return 1
    except Exception as exc:  # a JS-side throw arrives as frida.core.RPCException
        print(json.dumps({"ok": False, "export": opts.export,
                          "error": "%s: %s" % (type(exc).__name__, exc)},
                         ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "export": opts.export, "result": result},
                     ensure_ascii=False, default=str))
    return 0


# -- mode: REPL ---------------------------------------------------------------


def run_repl_mode(bridge, opts):
    print("connected; exports are callable by name. commands: list | name [json-args] | reload | quit")
    while True:
        try:
            line = input("rpc> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("quit", "exit", "q"):
            return 0
        if line == "list":
            try:
                print(" ".join(bridge.list_exports()))
            except BridgeError as exc:
                print("error: %s" % exc)
            continue
        if line == "reload":
            try:
                bridge.reload()
                print("reloaded")
            except BridgeError as exc:
                print("error: %s" % exc)
            continue
        parts = line.split(None, 1)
        name = parts[0]
        args = json.loads(parts[1]) if len(parts) > 1 and parts[1].strip() else []
        if not isinstance(args, list):
            print("args must be a JSON array")
            continue
        try:
            result = bridge.call(name, args)
            print(json.dumps(result, ensure_ascii=False, default=str))
        except BridgeError as exc:
            print("error: %s" % exc)
        except Exception as exc:  # JS-side throw arrives here as frida.core.RPCException
            print("js-error: %s" % exc)


# -- mode: HTTP ---------------------------------------------------------------


def run_http_mode(bridge, opts):
    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/exports":
                try:
                    self._send(200, {"ok": True, "exports": bridge.list_exports()})
                except BridgeError as exc:
                    self._send(502, {"ok": False, "error": str(exc)})
            else:
                self._send(404, {"ok": False, "error": "GET /exports only"})

        def do_POST(self):
            if self.path == "/reload":
                try:
                    bridge.reload()
                    self._send(200, {"ok": True})
                except BridgeError as exc:
                    self._send(502, {"ok": False, "error": str(exc)})
                return
            if self.path != "/call":
                self._send(404, {"ok": False, "error": "POST /call or /reload"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(length).decode("utf-8"))
                name = req.get("export")
                args = req.get("args", [])
                if not name or not isinstance(args, list):
                    raise ValueError('body must be {"export": "name", "args": [...]}')
                result = bridge.call(name, args)
                self._send(200, {"ok": True, "result": result})
            except BridgeError as exc:
                self._send(502, {"ok": False, "error": str(exc)})
            except Exception as exc:
                self._send(400, {"ok": False, "error": str(exc)})

        def log_message(self, fmt, *args):
            sys.stderr.write("[http] " + (fmt % args) + "\n")

    server = http.server.ThreadingHTTPServer((opts.host, opts.port), Handler)
    print("listening on http://%s:%d  (POST /call, GET /exports, POST /reload)"
          % (opts.host, opts.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Bridge a Frida script's rpc.exports to Python/REPL/HTTP with auto-reconnect.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Examples:")[-1].strip() if __doc__ else None,
    )
    parser.add_argument("--script", required=True, help="path to the .js defining rpc.exports")
    parser.add_argument("--package", help="target package (attach by name, or spawn with --spawn)")
    parser.add_argument("--pid", type=int, help="target pid (use when attach-by-name fails)")
    parser.add_argument("--device-serial", help="explicit USB device serial (see adb devices -l)")
    parser.add_argument("--remote", metavar="HOST:PORT",
                        help="explicit remote frida via adb forward, e.g. 127.0.0.1:27042")
    parser.add_argument("--spawn", action="store_true",
                        help="spawn the package instead of attaching (catches startup)")
    parser.add_argument("--mode", choices=("call", "repl", "http"), default="repl")
    parser.add_argument("--export", help="export name (call mode)")
    parser.add_argument("--args", help="JSON array of arguments (call mode)")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host (http mode)")
    parser.add_argument("--port", type=int, default=8765, help="HTTP bind port (http mode)")
    parser.add_argument("--runtime", default="v8", choices=("v8", "qjs"),
                        help="script runtime (v8 carries the Java bridge)")
    parser.add_argument("--retries", type=int, default=5, help="reconnect attempts before giving up")
    parser.add_argument("--backoff", type=float, default=1.0,
                        help="first reconnect delay (seconds); doubles per attempt")
    opts = parser.parse_args(argv)

    if opts.mode == "call" and not opts.export:
        parser.error("--mode call requires --export")

    bridge = RpcBridge(opts)
    try:
        bridge.ensure()
    except RETRYABLE + (BridgeError, OSError) as exc:
        sys.stderr.write("initial connect failed: %s\n" % exc)
        return 2

    if opts.mode == "call":
        return run_call_mode(bridge, opts)
    if opts.mode == "http":
        return run_http_mode(bridge, opts)
    return run_repl_mode(bridge, opts)


if __name__ == "__main__":
    sys.exit(main())
