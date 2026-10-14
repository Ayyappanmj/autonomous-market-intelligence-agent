"""Process launcher.

MODE=gateway (default)  ONE public port ($PORT): public REST API (/health, /docs, /api/v1/...) plus the
                        Streamlit dashboard reverse-proxied at every other path. Streamlit itself listens
                        on loopback only (STREAMLIT_PORT, default 8501). Best fit for Render's free tier.
MODE=both               Two public ports: API on API_PORT (8000) and Streamlit on $PORT.
MODE=api                FastAPI only on $PORT.
MODE=dashboard          Streamlit only on $PORT (needs API_BASE_URL).
"""
import os
import signal
import subprocess
import sys
import time
import urllib.request

UVICORN = [sys.executable, "-m", "uvicorn", "--host"]


def streamlit_cmd(address: str, port: str, relaxed_origin: bool) -> list[str]:
    cmd = [sys.executable, "-m", "streamlit", "run", "dashboard/streamlit_app.py",
           "--server.port", port, "--server.address", address, "--server.headless", "true",
           "--browser.gatherUsageStats", "false"]
    if relaxed_origin:
        # Behind the gateway the browser's Origin is the public hostname, which Streamlit's own origin/XSRF
        # checks would reject. Streamlit is bound to loopback and this app has no uploads or logins.
        cmd += ["--server.enableCORS", "false", "--server.enableXsrfProtection", "false"]
    else:
        cmd += ["--server.enableXsrfProtection", "true"]
    return cmd


def wait_for(url: str, seconds: int) -> bool:
    for _ in range(seconds * 2):
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main() -> int:
    from app.config import load_env_file

    load_env_file()
    mode = os.getenv("MODE", "gateway").lower()
    port = os.getenv("PORT", "8000")
    env = dict(os.environ)
    procs: list[subprocess.Popen] = []

    def stop(*_):
        for p in procs:
            if p.poll() is None:
                p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    if mode == "api":
        return subprocess.call(UVICORN + ["0.0.0.0", "--port", port, "app.main:create_app", "--factory"])

    if mode == "gateway":
        st_port = os.getenv("STREAMLIT_PORT", "8501")
        env["API_BASE_URL"] = f"http://127.0.0.1:{port}"
        env["DASHBOARD_UPSTREAM"] = f"http://127.0.0.1:{st_port}"
        procs.append(subprocess.Popen(streamlit_cmd("127.0.0.1", st_port, True), env=env))
        # Start the public port immediately so the platform's port scan succeeds; the dashboard
        # answers 502 "starting" for the first few seconds.
        procs.append(subprocess.Popen(UVICORN + ["0.0.0.0", "--port", port, "gateway:create_gateway_app", "--factory"], env=env))
        while True:  # exit if either process dies so the platform restarts the service
            if any(p.poll() is not None for p in procs):
                stop()
            time.sleep(1)

    if mode == "both":
        api_port = os.getenv("API_PORT", "8000")
        procs.append(subprocess.Popen(UVICORN + ["127.0.0.1", "--port", api_port, "app.main:create_app", "--factory"]))
        env["API_BASE_URL"] = env.get("API_BASE_URL") or f"http://127.0.0.1:{api_port}"
        wait_for(f"http://127.0.0.1:{api_port}/health", 20)

    st = subprocess.Popen(streamlit_cmd("0.0.0.0", port, False), env=env)
    procs.append(st)
    code = st.wait()
    stop()
    return code


if __name__ == "__main__":
    sys.exit(main())
