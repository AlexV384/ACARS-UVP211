import asyncio
import subprocess
import sys

COMPOSE_FILE = "docker-compose.yml"
CONTAINER_NAME = "acars-postgis"
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
    import inspect
    global COMPOSE_DIR
    p = inspect.getfile(lambda: None)
    COMPOSE_DIR = str(p).rsplit("/", 1)[0] if "/" in str(p) else "."


def docker_available() -> bool:
    rc, _, _ = _run(["docker", "version"])
    return rc == 0


def docker_daemon_running() -> bool:
    rc, _, _ = _run(["docker", "info"])
    return rc == 0


def container_exists() -> bool:
    rc, out, _ = _run(["docker", "ps", "-a", "--filter", f"name=^{CONTAINER_NAME}$", "--format", "{{.Names}}"])
    return rc == 0 and out == CONTAINER_NAME


def container_running() -> bool:
    rc, out, _ = _run(["docker", "ps", "--filter", f"name=^{CONTAINER_NAME}$", "--format", "{{.Names}}"])
    return rc == 0 and out == CONTAINER_NAME


def start_container():
    rc, out, err = _run(["docker", "start", CONTAINER_NAME])
    if rc != 0:
        print(f"  docker start failed: {err}")
        return False
    print(f"  started existing container")
    return True


def create_and_start_container():
    import os
    _set_compose_dir()
    rc, out, err = _run(["docker", "compose", "-f", os.path.join(COMPOSE_DIR, COMPOSE_FILE), "up", "-d"])
    if rc != 0:
        print(f"  docker compose up failed: {err}")
        return False
    print(f"  container created and started")
    return True


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

    if container_running():
        return

    print("[docker] postgis container not running, starting...")

    if container_exists():
        ok = start_container()
    else:
        ok = create_and_start_container()

    if not ok:
        print("  failed to start postgis container")
        sys.exit(1)

    print("  waiting for postgis to accept connections...")