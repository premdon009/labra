"""compose.yaml: the limits and rights each container runs with. `scripts/stack_smoke.sh` reads
the same from inside the running containers."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
LIMITED = ("web", "db", "proxy")
# Third-party tunnel images, each under its own profile and not started by the smoke test.
TUNNELS = {"tunnel", "tailscale", "netbird"}
UNITS = {"g": 1024**3, "m": 1024**2}


def _services(path: str = "compose.yaml") -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))["services"]


def _setting(value: object) -> tuple[str, str]:
    """`${NAME:-default}` as (NAME, default)."""
    match = re.fullmatch(r"\$\{(\w+):-([^}]+)\}", str(value))
    assert match, value
    return match[1], match[2]


@pytest.mark.item("W42")
def test_web_db_and_the_proxy_fit_a_4_gb_2_cpu_laptop_between_them() -> None:
    services = _services()
    memory, cpus = 0, 0.0
    for name in LIMITED:
        service = services[name]
        setting, size = _setting(service["mem_limit"])
        assert setting == f"LABRA_{name.upper()}_MEMORY"
        memory += int(size[:-1]) * UNITS[size[-1]]
        setting, share = _setting(service["cpus"])
        assert setting == f"LABRA_{name.upper()}_CPUS"
        cpus += float(share)
        assert service["pids_limit"] == 256, name
    assert memory == 4 * 1024**3
    assert cpus == 2


@pytest.mark.item("W42")
def test_every_container_runs_with_only_the_rights_it_needs() -> None:
    services = _services()
    ours = {name: s for name, s in services.items() if name not in TUNNELS}
    for name, service in ours.items():
        assert service.get("security_opt") == ["no-new-privileges"], name
        assert service.get("cap_drop") == ["ALL"], name
    assert {name: s.get("cap_add", []) for name, s in ours.items()} == {
        "db": ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"],
        "migrate": [],
        "web": [],
        "proxy": ["NET_BIND_SERVICE"],
        "backup": [],
        "restore": [],
    }
    for name in ("web", "migrate"):
        assert services[name]["read_only"] is True, name
        assert services[name]["tmpfs"] == ["/tmp"], name  # noqa: S108  the container's, in memory
    nginx = _services("deploy/nginx/compose.nginx.yaml")["proxy"]
    assert nginx["cap_add"] == ["CHOWN", "DAC_OVERRIDE", "SETGID", "SETUID"]


@pytest.mark.item("W43")
def test_web_has_no_route_to_the_internet_and_its_checks_ping_from_the_backup_image() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    internal = {
        name for name, network in compose["networks"].items() if (network or {}).get("internal")
    }
    assert internal == {"db", "edge"}
    for name in ("web", "migrate", "db"):
        assert set(services[name]["networks"]) <= internal, name
    assert compose["networks"]["edge"]["ipam"]["config"] == [
        {"subnet": "${LABRA_EDGE_SUBNET:-172.30.0.0/24}"}
    ]
    # The proxy reaches web on edge and is reached on public; the tunnels need the internet.
    assert services["proxy"]["networks"] == ["edge", "public"]
    assert services["tunnel"]["networks"] == services["tailscale"]["networks"] == ["public"]
    assert not [key for key in services["web"]["environment"] if "HEARTBEAT" in key]
    for job in ("AUDIT_VERIFY", "DISK"):
        assert f"LABRA_HEARTBEAT_URL_{job}" in services["backup"]["environment"]
