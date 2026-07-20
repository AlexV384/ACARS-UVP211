import asyncio
import os
import subprocess
import sys
from pathlib import Path

COMPOSE_FILE = "docker-compose.yml"
COMPOSE_DIR = None


def _run(cmd: list[str]) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return -1, "", "docker not found"
    except subprocess.TimeoutExpired as e:
        return -1, "", str(e)


def _set_compose_dir():
    global COMPOSE_DIR
    COMPOSE_DIR = str(Path(__file__).resolve().parent)


def docker_available() -> bool:
    rc, _, _ = _run(["docker", "version"])
    return rc == 0


def docker_daemon_running() -> bool:
    rc, _, _ = _run(["docker", "info"])
    return rc == 0


def _compose_up():
    rc, out, err = _run(["docker", "compose", "-f", os.path.join(COMPOSE_DIR, COMPOSE_FILE), "up", "-d"])
    if rc != 0:
        print(f"  docker compose up failed: {err}")
        return False
    return True


def _stop_old_monitoring():
    old = os.path.join(COMPOSE_DIR, "monitoring", "docker-compose.yml")
    if os.path.isfile(old):
        _run(["docker", "compose", "-f", old, "down"])


async def wait_for_db(pool_factory, host: str = "localhost", port: int = 5432, timeout: float = 60.0):
    import asyncpg
    from config import DB_CONFIG

    t0 = asyncio.get_event_loop().time()
    last_err = None
    while asyncio.get_event_loop().time() - t0 < timeout:
        try:
            conn = await asyncpg.connect(**DB_CONFIG, timeout=5)
            await conn.close()
            return True
        except Exception as e:
            last_err = e
        await asyncio.sleep(2)
    print(f"  db not ready after {timeout}s: {last_err}")
    return False


def ensure_postgis_sync():
    if not docker_available():
        print("Docker is not installed. Please install Docker Desktop and try again.")
        sys.exit(1)
    if not docker_daemon_running():
        print("Docker daemon is not running. Start Docker Desktop and re-run this script.")
        sys.exit(1)

    print("[docker] starting containers (postgis, grafana, prometheus, node-exporter)...")

    _set_compose_dir()

    # Stop old monitoring stack from monitoring/docker-compose.yml if present
    # (prevents container name conflicts with the merged compose file)
    _stop_old_monitoring()

    if not _compose_up():
        print("  failed to start containers")
        sys.exit(1)

    print("  waiting for postgis to accept connections...")