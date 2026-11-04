"""Consume exported native note text, external locks and exact release assets."""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from sdk_script import sdk_script

cli = Path(sys.argv[1]).resolve() / "bin/anki-purifier"
original = Path(sys.argv[2]).resolve()
source = Path(__file__).resolve().parents[1]


def call(arguments, *, env, cwd):
    result = subprocess.run(
        arguments, check=True, env=env, cwd=cwd, text=True, capture_output=True
    )
    return result.stdout.strip()


with tempfile.TemporaryDirectory(prefix="anki-artifacts-") as temporary:
    root = Path(temporary)
    project = root / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".anki-purifier"),
    )
    env = os.environ.copy() | {
        "HOME": str(root / "home"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "QT_QPA_PLATFORM": "offscreen",
    }
    for name in ["home", "data", "config", "cache"]:
        (root / name).mkdir()
    args = [str(cli), "--project", str(project)]
    build = Path(call([*args, "build"], env=env, cwd=root))
    text = (build / "notes.txt").read_text()
    assert "42" in text and "What is the answer?" in text
    consumer = root / "consumer.py"
    consumer.write_text(
        "from pathlib import Path\n"
        "from anki.collection import Collection\n"
        "from anki.import_export_pb2 import ImportCsvRequest\n"
        f"col=Collection({str(root / 'consumer.anki2')!r})\n"
        f"path={str(build / 'notes.txt')!r}\n"
        "metadata=col.get_csv_metadata(path,None)\n"
        "col.import_csv(ImportCsvRequest(path=path,metadata=metadata))\n"
        "notes=[col.get_note(id).fields for id in col.find_notes('')]\n"
        "assert notes==[['What is the answer?','42']],notes\n"
        "col.close()\n"
    )
    sdk_script(original, consumer, root / "consumer-state")
    release = Path(call([*args, "bundle"], env=env, cwd=root))
    archive = release / "anki-project.tar.gz"
    with tarfile.open(archive) as tar:
        assert (
            tar.extractfile("./notes.txt").read() == (build / "notes.txt").read_bytes()
        )
    external = root / "external-lock.json"
    shutil.copyfile(project / "anki-purifier.lock.json", external)
    replay = Path(call([*args, "--lock", str(external), "bundle"], env=env, cwd=root))
    assert (replay / archive.name).read_bytes() == archive.read_bytes()
    fake = root / "gh"
    fake.write_text(
        f"#!{sys.executable}\nimport json,os,sys\nfrom pathlib import Path\n"
        "Path(os.environ['UPLOAD_RECORD']).write_text(json.dumps(sys.argv[1:]))\n"
        "Path(os.environ['UPLOAD_BYTES']).write_bytes(Path(sys.argv[4]).read_bytes())\n"
    )
    fake.chmod(0o755)
    publish_env = env | {
        "ANKI_PURIFIER_GH": str(fake),
        "UPLOAD_RECORD": str(root / "upload.json"),
        "UPLOAD_BYTES": str(root / "upload.tar.gz"),
    }
    call([*args, "publish", "--tag", "proof"], env=publish_env, cwd=root)
    record = json.loads((root / "upload.json").read_text())
    assert record[:3] == ["release", "upload", "proof"] and record[3] == str(archive)
    assert (root / "upload.tar.gz").read_bytes() == archive.read_bytes()
print("native ANKI artifact consumers passed")
