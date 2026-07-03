import subprocess


def test_compose_declares_five_services():
    out = subprocess.run(["docker", "compose", "config", "--services"],
                         capture_output=True, text=True, check=True).stdout
    services = set(out.split())
    assert {"postgres", "redis", "api", "worker", "dashboard"} <= services
