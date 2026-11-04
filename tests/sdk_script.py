"""Run a probe with the unmodified SDK's Python dependencies, before GUI startup."""

import os
import subprocess
from pathlib import Path


def sdk_script(original, script, root, extra=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    hooks = root / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "sitecustomize.py").write_text(
        "import os,runpy,sys,traceback\n"
        "try:\n"
        " runpy.run_path(os.environ['ANKI_TEST_SCRIPT'],run_name='__main__')\n"
        " sys.stdout.flush();sys.stderr.flush();os._exit(0)\n"
        "except BaseException:\n"
        " traceback.print_exc();sys.stderr.flush();os._exit(1)\n"
    )
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("ANKI_PURIFIER_") or key in {
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "WAYLAND_SOCKET",
            "DBUS_SESSION_BUS_ADDRESS",
            "ANKI_ADDONS",
            "ANKI_NOVERIFYSSL",
            "QT_QPA_PLATFORMTHEME",
        }:
            env.pop(key, None)
    for key, name in [
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
    ]:
        directory = root / name
        directory.mkdir(exist_ok=True)
        env[key] = str(directory)
    env.update(
        PYTHONPATH=str(hooks),
        PYTHONNOUSERSITE="1",
        PYTHONPYCACHEPREFIX=str(root / "python-cache"),
        QT_QPA_PLATFORM="offscreen",
        ANKI_TEST_SCRIPT=str(Path(script).resolve()),
    )
    env.update(extra or {})
    result = subprocess.run(
        [Path(original) / "bin/anki", "--version"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout
