"""Execute an Anki API script in a separate native collection profile."""

import json
import os
import subprocess
from pathlib import Path

from anki_purifier_prepare import prepare


def run_project(
    project,
    script,
    state,
    environment,
    original,
    hooks,
    cache,
    fonts,
    output,
    gui=False,
):
    project = Path(project).resolve()
    script = Path(script).resolve()
    state = Path(state).resolve()
    settings = project / "anki-purifier.settings.json"
    config = json.loads(settings.read_text()) if settings.exists() else {}
    env = os.environ.copy() | prepare(state, environment, config)
    for key in ["ANKI_PURIFIER_REQUEST", "ANKI_PURIFIER_SCRIPT", "ANKI_PURIFIER_SEED"]:
        env.pop(key, None)
    for key, name in [
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ]:
        directory = state / name
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        env[key] = str(directory)
    env.update(
        PYTHONPATH=str(hooks),
        PYTHONNOUSERSITE="1",
        PYTHONPYCACHEPREFIX=str(cache),
        FONTCONFIG_FILE=str(fonts),
        ANKI_PURIFIER_PROFILE=str(state / "profile"),
        ANKI_PURIFIER_OUTPUT=str(Path(output).resolve()),
    )
    if not gui:
        for key in [
            "DISPLAY",
            "WAYLAND_DISPLAY",
            "WAYLAND_SOCKET",
            "DBUS_SESSION_BUS_ADDRESS",
            "DBUS_STARTER_ADDRESS",
            "DBUS_STARTER_BUS_TYPE",
            "SESSION_MANAGER",
            "AT_SPI_BUS_ADDRESS",
            "QT_QPA_PLATFORMTHEME",
        ]:
            env.pop(key, None)
        env["ANKI_WAYLAND"] = "0"
        env["NO_AT_BRIDGE"] = "1"
        env["DBUS_SYSTEM_BUS_ADDRESS"] = "unix:path=" + str(state / "no-system-bus")
        env["QT_QPA_PLATFORM"] = "offscreen"
        env.setdefault("QT_QUICK_BACKEND", "software")
        env.setdefault(
            "QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --disable-dev-shm-usage"
        )
    executable = Path(original) / "bin/anki"
    seed = Path(__file__).with_name("anki_purifier_seed_profile.py")
    subprocess.run(
        [executable, "--version"],
        env=env | {"ANKI_PURIFIER_SEED": str(seed)},
        check=True,
    )
    env["ANKI_PURIFIER_SCRIPT"] = str(script)
    result = subprocess.run(
        [executable, "-b", env["ANKI_PURIFIER_PROFILE"], "-p", "Purifier"],
        env=env,
        cwd=project,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    status = run_project(
        os.environ["ANKI_PURIFIER_PROJECT"],
        os.environ["ANKI_PURIFIER_SCRIPT"],
        os.environ["ANKI_PURIFIER_RUN_STATE"],
        os.environ["ANKI_PURIFIER_ENVIRONMENT"],
        os.environ["ANKI_PURIFIER_ORIGINAL"],
        os.environ["ANKI_PURIFIER_HOOKS"],
        os.environ["ANKI_PURIFIER_CACHE"],
        os.environ["ANKI_PURIFIER_FONTS"],
        os.environ["ANKI_PURIFIER_OUTPUT"],
    )
    raise SystemExit(status)
