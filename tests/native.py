"""Native add-on APIs, writable settings, source edits, guards and fallback."""

import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from sdk_script import sdk_script

cli = Path(sys.argv[1]).resolve() / "bin"
original = Path(sys.argv[2]).resolve()
source = Path(__file__).resolve().parents[1]


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"project networking works")

    def log_message(self, *args):
        pass


with tempfile.TemporaryDirectory(prefix="anki-native-") as temporary:
    root = Path(temporary)
    project = root / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".anki-purifier", "output"),
    )
    env = os.environ.copy() | {"QTWEBENGINE_DISABLE_SANDBOX": "1"}
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    script = project / "build.py"
    script.write_text(
        script.read_text()
        + """
import stat, urllib.request, sys
manager=aqt.mw.addonManager
assert Path(addon.__file__).resolve().is_relative_to('/nix/store')
assert not (Path(addon.__file__).stat().st_mode & stat.S_IWUSR)
assert Path(sys.pycache_prefix).is_relative_to('/nix/store')
conf=manager.getConfig('2055492159')
conf['purifierCounter']=conf.get('purifierCounter',0)+1
manager.writeConfig('2055492159',conf)
assert not manager.addon_meta('2055492159').update_enabled
assert 'locked' in manager.install('/not-an-archive').errmsg
try:manager.deleteAddon('2055492159')
except RuntimeError as error:assert 'locked' in str(error)
else:raise AssertionError('native delete is not frozen')
assert not __import__('aqt.addons',fromlist=['fetch_update_info']).fetch_update_info([2055492159])
ambient=Path(manager.addonsFolder())/'purifier_ambient'
ambient.mkdir(exist_ok=True)
(ambient/'__init__.py').write_text('VALUE=42\\n')
try:importlib.import_module('purifier_ambient')
except ImportError as error:assert 'unlocked' in str(error)
else:raise AssertionError('mutable add-on module loaded')
with urllib.request.urlopen('TEST_URL') as response:
    assert response.read()==b'project networking works'
(output/'counter.txt').write_text(str(manager.getConfig('2055492159')['purifierCounter']))
""".replace("TEST_URL", f"http://127.0.0.1:{server.server_port}/")
    )
    args = [cli / "anki-purifier", "--project", project]
    lock = project / "anki-purifier.lock.json"
    before = lock.read_bytes()
    hashes = []
    try:
        for counter, answer in enumerate(["42", "43", "42"], 1):
            (project / "answer.json").write_text(json.dumps({"answer": answer}))
            # First prove the unmodified loader accepts the same mutable package.
            if counter > 1:
                overlay = next((project / ".anki-purifier/run/code").glob("*/addons"))
                package = overlay / "purifier_ambient"
                control = root / "control.py"
                control.write_text(
                    "import sys\nsys.path.insert(0,"
                    + repr(str(overlay))
                    + ")\nimport purifier_ambient\nassert purifier_ambient.VALUE==42\n"
                )
                sdk_script(original, control, root / f"control-{counter}")
                shutil.rmtree(package)
            result = subprocess.run(
                [*args, "run", "build.py"],
                env=env,
                cwd=project,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            assert (project / "output/counter.txt").read_text() == str(counter)
            assert answer in (project / "output/notes.txt").read_text()
            hashes.append(
                hashlib.sha256((project / "output/notes.txt").read_bytes()).hexdigest()
            )
            assert lock.read_bytes() == before
    finally:
        server.shutdown()
        server.server_close()
    assert hashes[0] != hashes[1] and hashes[0] == hashes[2]
    overlay = next((project / ".anki-purifier/run/code").glob("*/addons"))
    failed = subprocess.run(
        [*args, "run", "build.py"],
        env=env,
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode and "unlocked Anki add-on state" in failed.stderr
    shutil.rmtree(overlay / "purifier_ambient")
    bad = project / "failure.py"
    bad.write_text("raise SystemExit(7)\n")
    result = subprocess.run(
        [*args, "run", "failure.py"],
        env=env,
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 7, result.stdout + result.stderr
    (project / "anki-purifier.json").write_text('{"addons": []}')
    failed = subprocess.run(
        [cli / "anki", "--version"],
        env=env | {"ANKI_PURIFIER_PROJECT": str(project)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode and "selection changed" in failed.stderr
    lock.unlink()
    for arguments in [["--version"], ["-b"]]:
        expected = subprocess.run(
            [original / "bin/anki", *arguments],
            env=env,
            capture_output=True,
            check=False,
        )
        actual = subprocess.run(
            [cli / "anki", *arguments],
            env=env | {"ANKI_PURIFIER_PROJECT": str(project)},
            capture_output=True,
            check=False,
        )
        assert actual.returncode == expected.returncode
        assert actual.stdout == expected.stdout
        assert (
            actual.stderr
            == b"warning: no Anki purifier lock; using ordinary, impure add-on resolution\n"
            + expected.stderr
        )
print("Anki native source/preferences/network/code guards/status/fallback passed")
