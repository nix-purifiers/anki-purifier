"""ANKI's normal application workflow with a frozen native extension profile."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def public_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("ANKI addon repositories must use public HTTPS URLs")
    return url


def selection(project):
    value = json.loads((project / "anki-purifier.json").read_text())
    if set(value) != {"addons"} or not isinstance(value["addons"], list):
        raise ValueError("anki-purifier.json needs an addons list of AnkiWeb IDs")
    if any(type(id) is not int or id <= 0 for id in value["addons"]) or len(
        set(value["addons"])
    ) != len(value["addons"]):
        raise ValueError("add-ons need unique positive AnkiWeb IDs")
    return value


def project_path(explicit):
    if explicit:
        return Path(explicit).resolve()
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "anki-purifier.json").exists() or (
            parent / "anki-purifier.lock.json"
        ).exists():
            return parent
    return current


def validate(project, lock):
    data = json.loads(lock.read_text())
    if data.get("version") != 1 or data.get("purifier") != "anki":
        raise ValueError("unsupported ANKI lock")
    if data.get("sdk") != os.environ["ANKI_PURIFIER_SDK"]:
        raise ValueError("ANKI SDK changed; run anki-purifier lock --update")
    if data.get("selection") != selection(project):
        raise ValueError("extension selection changed; run anki-purifier lock --update")
    return data


def realize(project, lock, target="environment", out_link=None):
    args = [
        "nix",
        "build",
        "--impure",
        "--file",
        os.environ["ANKI_PURIFIER_REALIZE"],
        "--argstr",
        "projectPath",
        str(project),
        "--argstr",
        "lockPath",
        str(lock),
        "--argstr",
        "target",
        target,
        "--json",
    ]
    args += ["--out-link", str(out_link)] if out_link else ["--no-link"]
    result = run(args, stdout=subprocess.PIPE, text=True)
    return Path(json.loads(result.stdout)[0]["outputs"]["out"])


def native_operation(root, request):
    request_file = root / "request.json"
    response = root / "response.json"
    request_file.write_text(json.dumps(request))
    env = os.environ.copy()
    for key in [
        "ANKI_NOVERIFYSSL",
        "ANKI_ADDONS",
        "ANKI_PURIFIER_ENVIRONMENT",
        "ANKI_PURIFIER_SCRIPT",
        "ANKI_PURIFIER_SEED",
    ]:
        env.pop(key, None)
    for key, name in [
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ]:
        directory = root / name
        directory.mkdir(exist_ok=True, mode=0o700)
        env[key] = str(directory)
    env.update(
        PYTHONPATH=os.environ["ANKI_PURIFIER_HOOKS"],
        PYTHONNOUSERSITE="1",
        PYTHONPYCACHEPREFIX=str(root / "python-cache"),
        QT_QPA_PLATFORM="offscreen",
        QTWEBENGINE_DISABLE_SANDBOX="1",
        FONTCONFIG_FILE=os.environ["ANKI_PURIFIER_FONTS"],
        ANKI_PURIFIER_HELPER=str(
            Path(os.environ["ANKI_PURIFIER_NATIVE"]) / "anki_purifier_helper.py"
        ),
        ANKI_PURIFIER_REQUEST=str(request_file),
        ANKI_PURIFIER_RESPONSE=str(response),
    )
    run(
        [str(Path(os.environ["ANKI_PURIFIER_ORIGINAL"]) / "bin/anki"), "--version"],
        env=env,
        stdout=sys.stderr,
    )
    return json.loads(response.read_text())


def prefetch(url):
    return json.loads(
        run(
            ["nix", "store", "prefetch-file", "--json", public_url(url)],
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
    )


def capture(project, lock):
    requested = selection(project)
    with tempfile.TemporaryDirectory(prefix="anki-purifier-") as temporary:
        root = Path(temporary)
        native = native_operation(
            root,
            {
                "action": "capture",
                "addons": requested["addons"],
                "root": str(root / "capture"),
            },
        )
        entries = []
        for entry in native["entries"]:
            fetched = prefetch(entry["url"])

            if (
                hashlib.sha256(Path(fetched["storePath"]).read_bytes()).hexdigest()
                != entry["bytesSha256"]
            ):
                raise ValueError("Nix archive differs from the original Anki download")
            entries.append(
                {key: value for key, value in entry.items() if key != "bytesSha256"}
                | {"hash": fetched["hash"], "mirrors": []}
            )
        data = {
            "version": 1,
            "purifier": "anki",
            "sdk": os.environ["ANKI_PURIFIER_SDK"],
            "selection": requested,
            "entries": entries,
            "native": {"metadata": native["metadata"]},
        }
        candidate = root / "anki-purifier.lock.json"
        candidate.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        realize(project, candidate)
        lock.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=lock.parent, delete=False
        ) as output:
            output.write(candidate.read_text())
            pending = Path(output.name)
        try:
            os.replace(pending, lock)
        finally:
            pending.unlink(missing_ok=True)


def prepared_environment(project, lock):
    data = validate(project, lock)
    state = project / ".anki-purifier"
    identity = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    roots = state / "environments"
    roots.mkdir(parents=True, exist_ok=True)
    environment = realize(project, lock, out_link=roots / identity)
    alias = state / "environment"
    if alias.exists() and not alias.is_symlink():
        raise ValueError("unexpected file at the managed Anki environment link")
    with tempfile.TemporaryDirectory(dir=state) as temporary:
        link = Path(temporary) / "environment"
        link.symlink_to(environment)
        os.replace(link, alias)
    return state, environment


def native_exec(project, lock, arguments, command="anki"):
    executable = Path(os.environ["ANKI_PURIFIER_ORIGINAL"]) / "bin/anki"
    if not lock.exists():
        print(
            "warning: no Anki purifier lock; using ordinary, impure add-on resolution",
            file=sys.stderr,
        )
        os.execve(executable, [str(executable), *arguments], os.environ.copy())
    state, environment = prepared_environment(project, lock)
    sys.path.insert(0, os.environ["ANKI_PURIFIER_NATIVE"])
    from anki_purifier_prepare import prepare

    env = os.environ.copy() | prepare(state / "gui", environment)
    env.update(
        PYTHONPATH=os.environ["ANKI_PURIFIER_HOOKS"],
        PYTHONNOUSERSITE="1",
        PYTHONPYCACHEPREFIX=os.environ["ANKI_PURIFIER_CACHE"],
    )
    for key in ["ANKI_PURIFIER_REQUEST", "ANKI_PURIFIER_SCRIPT", "ANKI_PURIFIER_SEED"]:
        env.pop(key, None)
    os.execve(executable, [str(executable), *arguments], env)


def main():
    if os.environ.get("ANKI_PURIFIER_COMMAND") not in {None, "anki-purifier"}:
        project = project_path(os.environ.get("ANKI_PURIFIER_PROJECT"))
        lock = Path(
            os.environ.get("ANKI_PURIFIER_LOCK", project / "anki-purifier.lock.json")
        ).resolve()
        native_exec(project, lock, sys.argv[1:], os.environ["ANKI_PURIFIER_COMMAND"])
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    parser.add_argument("--lock")
    sub = parser.add_subparsers(dest="action", required=True)
    lock_parser = sub.add_parser("lock")
    lock_parser.add_argument("--update", action="store_true")
    sub.add_parser("prefetch")
    scripted = sub.add_parser("run")
    scripted.add_argument("script")
    scripted.add_argument("--gui", action="store_true")
    for name in ["build", "bundle"]:
        sub.add_parser(name)
    publish = sub.add_parser("publish")
    publish.add_argument("--tag", required=True)
    execute = sub.add_parser("exec")
    execute.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    project = project_path(args.project or os.environ.get("ANKI_PURIFIER_PROJECT"))
    lock = Path(
        args.lock
        or os.environ.get("ANKI_PURIFIER_LOCK", project / "anki-purifier.lock.json")
    ).resolve()
    if args.action == "run":
        state, environment = prepared_environment(project, lock)
        sys.path.insert(0, os.environ["ANKI_PURIFIER_NATIVE"])
        from anki_purifier_run_project import run_project

        script = Path(args.script)
        script = (script if script.is_absolute() else project / script).resolve()
        code = run_project(
            project,
            script,
            state / "run",
            environment,
            os.environ["ANKI_PURIFIER_ORIGINAL"],
            os.environ["ANKI_PURIFIER_HOOKS"],
            os.environ["ANKI_PURIFIER_CACHE"],
            os.environ["ANKI_PURIFIER_FONTS"],
            os.environ.get("ANKI_PURIFIER_OUTPUT", project / "output"),
            gui=args.gui,
        )
        raise SystemExit(code)
    if args.action == "lock" and args.update:
        capture(project, lock)
        return
    if args.action == "exec":
        arguments = (
            args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        )
        native_exec(project, lock, arguments)
        return
    validate(project, lock)
    if args.action == "lock":
        realize(project, lock)
    elif args.action == "prefetch":
        print(realize(project, lock))
    elif args.action in {"build", "bundle"}:
        print(
            realize(project, lock, "project" if args.action == "build" else "release")
        )
    elif args.action == "publish":
        release = realize(project, lock, "release")
        run(
            [
                os.environ.get("ANKI_PURIFIER_GH", "gh"),
                "release",
                "upload",
                args.tag,
                str(release / "anki-project.tar.gz"),
                "--clobber",
            ]
        )


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"anki-purifier: {error}", file=sys.stderr)
        sys.exit(1)
