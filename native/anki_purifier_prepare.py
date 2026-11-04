"""Create a generation-specific code view over stable native add-on preferences."""

import hashlib
import json
import shutil
from pathlib import Path


def prepare(state, environment, config=None):
    state = Path(state).resolve()
    environment = Path(environment).resolve()
    identity = hashlib.sha256(
        (str(state) + "\0" + str(environment)).encode()
    ).hexdigest()[:24]
    overlay = state / "code" / identity / "addons"
    overlay.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((environment / "manifest.json").read_text())
    expected = {}
    directories = {overlay}
    for id in metadata:
        native = environment / "addons" / id
        data = state / "addon-data" / id
        data.mkdir(parents=True, exist_ok=True)
        meta = data / "meta.json"
        if meta.is_symlink():
            raise ValueError("unexpected symlink in native Anki preferences")
        if not meta.exists():
            shutil.copyfile(native / "meta.json", meta)
        if config and id in config:
            value = json.loads(meta.read_text())
            value["config"] = {**value.get("config", {}), **config[id]}
            meta.write_text(json.dumps(value))
        user = data / "user_files"
        if user.is_symlink():
            raise ValueError("unexpected symlink in native Anki user_files")
        if not user.exists():
            if (native / "user_files").exists():
                shutil.copytree(native / "user_files", user)
            else:
                user.mkdir()
        package = overlay / id
        directories.add(package)
        for source in native.rglob("*"):
            relative = source.relative_to(native)
            if relative.parts[0] in {"meta.json", "user_files"}:
                continue
            target = package / relative
            if source.is_dir():
                directories.add(target)
            else:
                expected[target] = source
        expected[package / "meta.json"] = meta
        expected[package / "user_files"] = user

    # Check before modifying an existing generation; never erase unknown code.
    def validate(directory):
        for path in directory.iterdir():
            if path.is_symlink():
                if path not in expected or path.resolve() != expected[path].resolve():
                    raise ValueError(f"unlocked Anki add-on link: {path}")
            elif path.is_dir() and path in directories:
                validate(path)
            else:
                raise ValueError(f"unlocked Anki add-on state: {path}")

    validate(overlay)
    for directory in sorted(directories, key=lambda path: len(path.parts)):
        directory.mkdir(parents=True, exist_ok=True)
    for target, source in expected.items():
        if not target.is_symlink():
            target.symlink_to(source)
    return {
        "ANKI_ADDONS": str(overlay),
        "ANKI_PURIFIER_ENVIRONMENT": str(environment),
        "ANKI_PURIFIER_STATE": str(state),
        "ANKI_SINGLE_INSTANCE_KEY": "anki-purifier-" + identity,
    }
