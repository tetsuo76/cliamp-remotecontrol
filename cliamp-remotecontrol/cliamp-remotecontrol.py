import json
import os
import socket
import subprocess
from http.server import SimpleHTTPRequestHandler, HTTPServer

SOCKET_PATH = os.path.expanduser("~/.config/cliamp/cliamp.sock")
PORT = 9000
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

current_eq_index = 0
EQ_NAMES = ["Flat", "Rock", "Pop", "Jazz", "Metal", "Classical"]

DEBUG = False
DEFAULT_VOLUME_DB = -15.0
current_volume_db = DEFAULT_VOLUME_DB
HOSTNAME = socket.gethostname().upper()

def debug(*args):
    if DEBUG:
        print("[DEBUG]", *args, flush=True)


class RemoteHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        debug("HTTP GET", self.path)

        try:
            if self.path == "/api/status":
                status = self.get_status()
                debug("status response", status)
                self.respond_json(status)
                return

            if self.path.startswith("/api/"):
                cmd = self.path.split("/")[-1]
                debug("api command", cmd)
                self.handle_command(cmd)
                self.respond_json({"ok": True, "cmd": cmd})
                return

            if self.path == "/":
                self.path = "/index.html"

            return super().do_GET()

        except (BrokenPipeError, ConnectionResetError):
            debug("client disconnected during response")
        except Exception as e:
            debug("do_GET exception:", repr(e))
            try:
                self.respond_json({"ok": False, "error": str(e)})
            except Exception:
                pass

    def respond_json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers()
        self.safe_write(body)

    def safe_write(self, body):
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            debug("safe_write client disconnected")

    def handle_command(self, cmd):
        global current_eq_index, current_volume_db

        status = self.get_status()
        repeat_mode = str(status.get("repeat", "Off")).strip().lower()

        if cmd == "cycle_eq":
            current_eq_index = (current_eq_index + 1) % len(EQ_NAMES)
            eq_name = EQ_NAMES[current_eq_index]
            debug("running shell: cliamp eq", eq_name)
            self.run_cliamp_command(["cliamp", "eq", eq_name])
            return

        if cmd == "mute":
            current_volume_db = -30.0
            debug("running shell: cliamp volume -30")
            self.run_cliamp_command(["cliamp", "volume", "-30"])
            return

        if cmd == "shuffle":
            debug("running shell: cliamp shuffle")
            self.run_cliamp_command(["cliamp", "shuffle"])
            return

        if cmd == "repeat":
            debug("running shell: cliamp repeat")
            self.run_cliamp_command(["cliamp", "repeat"])
            return

        if cmd == "volume_zero":
            current_volume_db = 0.001
            debug("running shell: cliamp volume 0.001")
            self.run_cliamp_command(["cliamp", "volume", "0.001"])
            return

        if cmd == "prev":
            if repeat_mode == "one":
                debug("repeat is one, switching to all before prev")
                self.run_cliamp_command(["cliamp", "repeat", "all"])
                debug("running shell: cliamp prev")
                self.run_cliamp_command(["cliamp", "prev"])
                debug("restoring repeat one after prev")
                self.run_cliamp_command(["cliamp", "repeat", "one"])
            else:
                debug("running shell: cliamp prev")
                self.run_cliamp_command(["cliamp", "prev"])
            return

        if cmd == "next":
            if repeat_mode == "one":
                debug("repeat is one, switching to all before next")
                self.run_cliamp_command(["cliamp", "repeat", "all"])
                debug("running shell: cliamp next")
                self.run_cliamp_command(["cliamp", "next"])
                debug("restoring repeat one after next")
                self.run_cliamp_command(["cliamp", "repeat", "one"])
            else:
                debug("running shell: cliamp next")
                self.run_cliamp_command(["cliamp", "next"])
            return

        if cmd in ["volume_up", "volume_down"]:
            step = 1.0 if cmd == "volume_up" else -1.0
            new = max(-30.0, min(6.0, current_volume_db + step))

            if new == 0:
                new = 0.001

            current_volume_db = new
            debug("socket volume change", {"to": new})
            self.send_to_cliamp({"cmd": "volume", "value": float(new)})
            return

        payload = {"cmd": "toggle" if cmd == "play_pause" else cmd}
        debug("socket command", payload)
        self.send_to_cliamp(payload)

    def run_cliamp_command(self, command):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False
            )
            debug("shell returncode", result.returncode)
            if result.stdout:
                debug("shell stdout", result.stdout.strip())
            if result.stderr:
                debug("shell stderr", result.stderr.strip())
        except Exception as e:
            debug("shell command failed", repr(e))

    def send_to_cliamp(self, payload):
        try:
            debug("connecting socket", SOCKET_PATH)
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(SOCKET_PATH)

            message = json.dumps(payload, separators=(",", ":")) + "\n"
            debug("socket send", repr(message))
            client.sendall(message.encode())

            client.close()
        except Exception as e:
            debug("send_to_cliamp failed", repr(e))

    def get_status(self):
        global current_eq_index, current_volume_db

        try:
            debug("status socket connect", SOCKET_PATH)
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(0.5)
            client.connect(SOCKET_PATH)

            request = json.dumps({"cmd": "status"}) + "\n"
            debug("status request", repr(request))
            client.sendall(request.encode())

            raw = client.recv(4096).decode("utf-8")
            debug("status raw response", raw)

            client.close()
            data = json.loads(raw)

            track = data.get("track", {})

            eq_name = data.get("eq_preset")
            if eq_name in EQ_NAMES:
                current_eq_index = EQ_NAMES.index(eq_name)

            if "volume" in data and data.get("volume") is not None:
                try:
                    current_volume_db = float(data.get("volume"))
                except (TypeError, ValueError):
                    pass

            return {
                "artist": track.get("artist"),
                "title": track.get("title"),
                "volume": current_volume_db,
                "shuffle": bool(data.get("shuffle", False)),
                "repeat": data.get("repeat", "Off"),
                "eq_name": (eq_name or EQ_NAMES[current_eq_index]).upper(),
                "state": data.get("state", "stopped"),
                "connected": True,
                "hostname": HOSTNAME,
            }

        except Exception as e:
            debug("get_status failed", repr(e))
            return {
                "artist": None,
                "title": None,
                "volume": current_volume_db,
                "shuffle": False,
                "repeat": "Off",
                "eq_name": "FLAT",
                "state": "stopped",
                "connected": False,
            }

    def log_message(self, format, *args):
        if DEBUG:
            print("[HTTP]", format % args, flush=True)


if __name__ == "__main__":
    debug("starting server on port", PORT)
    try:
        HTTPServer(("0.0.0.0", PORT), RemoteHandler).serve_forever()
    except KeyboardInterrupt:
        debug("server stopped")
