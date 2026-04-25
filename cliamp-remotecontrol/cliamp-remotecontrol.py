import json
import os
import shutil
import socket
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

SOCKET_PATH = os.path.expanduser("~/.config/cliamp/cliamp.sock")
PORT = 9000
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
STREAM_SAMPLE_RATE = 44100
STREAM_BITRATE = "320k"
STREAM_FORMAT = "mp3"
STREAM_CONTENT_TYPE = "audio/mpeg"

current_eq_index = 0
EQ_NAMES = ["Flat", "Rock", "Pop", "Jazz", "Metal", "Classical"]

DEBUG = False
DEFAULT_VOLUME_DB = -15.0
current_volume_db = DEFAULT_VOLUME_DB
HOSTNAME = socket.gethostname().upper()

def debug(*args):
    if DEBUG:
        print("[DEBUG]", *args, flush=True)


def is_port_in_use(port, host="127.0.0.1"):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex((host, port)) == 0
    except OSError:
        return False


def print_port_in_use_error(port):
    if is_port_in_use(port):
        print(
            f"Error: cliamp-remote is already running on port {port}.",
            file=sys.stderr,
            flush=True,
        )
    else:
        print(
            f"Error: port {port} is already in use by another application.",
            file=sys.stderr,
            flush=True,
        )


def first_non_empty(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def run_command(command):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )


def get_listen_support():
    if not sys.platform.startswith("linux"):
        return {
            "listen_supported": False,
            "listen_reason": "Listen is only supported on Linux with PulseAudio or PipeWire",
            "audio_backend_detected": False,
            "audio_backend_name": "pulseaudio/pipewire",
        }

    if shutil.which("ffmpeg") is None:
        return {
            "listen_supported": False,
            "listen_reason": "ffmpeg is not installed",
            "audio_backend_detected": False,
            "audio_backend_name": "pulseaudio/pipewire",
        }

    if shutil.which("pactl") is None:
        return {
            "listen_supported": False,
            "listen_reason": "pactl is not installed",
            "audio_backend_detected": False,
            "audio_backend_name": "pulseaudio/pipewire",
        }

    return {
        "listen_supported": True,
        "listen_reason": None,
        "audio_backend_detected": True,
        "audio_backend_name": "pulseaudio/pipewire",
    }


def get_cliamp_active_device():
    try:
        result = run_command(["cliamp", "device", "list"])
        if result.returncode != 0:
            debug("device list failed", result.stderr.strip())
            return None

        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("* "):
                return stripped[2:].strip()
    except Exception as e:
        debug("get_cliamp_active_device failed", repr(e))

    return None


def get_monitor_sources():
    try:
        result = run_command(["pactl", "list", "short", "sources"])
        if result.returncode != 0:
            debug("pactl list short sources failed", result.stderr.strip())
            return []

        sources = []
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                sources.append(parts[1].strip())
        return sources
    except Exception as e:
        debug("get_monitor_sources failed", repr(e))
        return []


def get_listen_info():
    support = get_listen_support()
    if not support["listen_supported"]:
        return {
            "listen_supported": False,
            "listen_visible": False,
            "listen_url": None,
            "listen_reason": support["listen_reason"],
            "listen_source": None,
            "audio_interface_detected": False,
            "audio_interface_name": None,
            "audio_backend_detected": support["audio_backend_detected"],
            "audio_backend_name": support["audio_backend_name"],
        }

    device = get_cliamp_active_device()
    if not device:
        return {
            "listen_supported": True,
            "listen_visible": True,
            "listen_url": None,
            "listen_reason": "No active cliamp output device found",
            "listen_source": None,
            "audio_interface_detected": False,
            "audio_interface_name": None,
            "audio_backend_detected": support["audio_backend_detected"],
            "audio_backend_name": support["audio_backend_name"],
        }

    monitor_source = f"{device}.monitor"
    sources = get_monitor_sources()

    if monitor_source not in sources:
        return {
            "listen_supported": True,
            "listen_visible": True,
            "listen_url": None,
            "listen_reason": f"No monitor source found for {device}",
            "listen_source": None,
            "audio_interface_detected": True,
            "audio_interface_name": device,
            "audio_backend_detected": support["audio_backend_detected"],
            "audio_backend_name": support["audio_backend_name"],
        }

    return {
        "listen_supported": True,
        "listen_visible": True,
        "listen_url": "/listen",
        "listen_reason": f"Streaming {device}",
        "listen_source": monitor_source,
        "audio_interface_detected": True,
        "audio_interface_name": device,
        "audio_backend_detected": support["audio_backend_detected"],
        "audio_backend_name": support["audio_backend_name"],
    }


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

            if self.path == "/listen":
                self.stream_device_audio()
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
            result = run_command(command)
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
        listen_info = get_listen_info()

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
                "listen_supported": listen_info["listen_supported"],
                "listen_visible": listen_info["listen_visible"],
                "listen_url": listen_info["listen_url"],
                "listen_reason": listen_info["listen_reason"],
                "audio_interface_detected": listen_info["audio_interface_detected"],
                "audio_interface_name": listen_info["audio_interface_name"],
                "audio_backend_detected": listen_info["audio_backend_detected"],
                "audio_backend_name": listen_info["audio_backend_name"],
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
                "listen_supported": listen_info["listen_supported"],
                "listen_visible": listen_info["listen_visible"],
                "listen_url": listen_info["listen_url"],
                "listen_reason": listen_info["listen_reason"],
                "audio_interface_detected": listen_info["audio_interface_detected"],
                "audio_interface_name": listen_info["audio_interface_name"],
                "audio_backend_detected": listen_info["audio_backend_detected"],
                "audio_backend_name": listen_info["audio_backend_name"],
            }

    def stream_device_audio(self):
        listen_info = get_listen_info()
        source = listen_info.get("listen_source")

        if not source:
            body = (listen_info.get("listen_reason") or "Listening unavailable").encode("utf-8")
            self.send_response(503)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.safe_write(body)
            return

        command = [
            "ffmpeg",
            "-loglevel", "error",
            "-f", "pulse",
            "-i", source,
            "-ac", "2",
            "-ar", str(STREAM_SAMPLE_RATE),
            "-b:a", STREAM_BITRATE,
            "-f", STREAM_FORMAT,
            "pipe:1",
        ]

        process = None
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self.send_response(200)
            self.send_header("Content-Type", STREAM_CONTENT_TYPE)
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Connection", "close")
            self.end_headers()

            while True:
                chunk = process.stdout.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            debug("listen stream client disconnected")
        except Exception as e:
            debug("stream_device_audio failed", repr(e))
        finally:
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except Exception:
                    process.kill()
                    process.wait()

    def log_message(self, format, *args):
        if DEBUG:
            print("[HTTP]", format % args, flush=True)


if __name__ == "__main__":
    debug("starting server on port", PORT)
    if is_port_in_use(PORT):
        print_port_in_use_error(PORT)
        sys.exit(1)

    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), RemoteHandler).serve_forever()
    except OSError as e:
        if e.errno == 98:
            print_port_in_use_error(PORT)
            sys.exit(1)
        raise
    except KeyboardInterrupt:
        debug("server stopped")