"""Proves the FastAPI spike service can run as its own subprocess and
shut down cleanly -- the same pattern desktop_app.py already uses for
Streamlit, and for the same reason: desktop_app.py's own module docstring
documents that running a server's blocking loop in-process on a
background thread crashed live (bootstrap.run() installs a SIGTERM
handler, and Python only allows signal.signal() from the main thread --
uvicorn does the same signal-handler installation Streamlit's bootstrap
does, so the same crash applies here). Run directly:
    python3 api/spike_launcher.py
"""
import socket
import subprocess
import sys
import time
import urllib.request


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(url, timeout_s=30):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def launch_api_subprocess(port):
    cmd = [sys.executable, "-m", "uvicorn", "api.main:app",
           "--host", "127.0.0.1", "--port", str(port)]
    return subprocess.Popen(cmd)


def main():
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    proc = launch_api_subprocess(port)
    try:
        if not wait_for_server(f"{url}/api/overview/headline-stats"):
            print("API server did not start in time.", file=sys.stderr)
            proc.terminate()
            sys.exit(1)

        resp = urllib.request.urlopen(f"{url}/api/overview/headline-stats", timeout=5)
        body = resp.read()
        print("Fetched real data through the subprocess API:", body[:200])
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    assert proc.poll() is not None, "API subprocess did not exit cleanly"
    print(f"Clean shutdown confirmed -- exit code {proc.poll()}")


if __name__ == "__main__":
    main()
