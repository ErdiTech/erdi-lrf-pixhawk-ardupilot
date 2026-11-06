import subprocess
import sys
from pathlib import Path


def test_protocol_fixtures_pass():
    script = Path(__file__).with_name("protocol_fixtures.py")
    out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "PASS" in out.stdout
