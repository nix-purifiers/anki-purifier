"""Original AnkiWeb branch selection, manifest validation and add-on installation."""

import dataclasses
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import requests
from anki.httpclient import HttpClient
from aqt import addons
from aqt.qt import QAction, QApplication


class Client(HttpClient):
    def get(self, *args, **kwargs):
        self.response = super().get(*args, **kwargs)
        return self.response


class Replay(HttpClient):
    def __init__(self, entry, data):
        super().__init__()
        self.entry = entry
        self.data = data

    def get(self, url):
        expected = f"{addons.aqt.appShared}download/{self.entry['anki']['id']}?v=2.1&p={addons._current_version}"
        if url != expected:
            raise ValueError("native download request changed")
        response = requests.Response()
        response.status_code = 200
        response.url = self.entry["url"]
        response.headers["content-disposition"] = (
            "attachment; filename=" + self.entry["anki"]["filename"]
        )
        response._content = self.data
        response._content_consumed = True
        return response


def install(root, entries, archives):
    _app = QApplication.instance() or QApplication([])
    root.mkdir(parents=True, exist_ok=True)
    action = QAction("Add-ons")
    manager = addons.AddonManager(
        SimpleNamespace(
            pm=SimpleNamespace(addonFolder=lambda: str(root)),
            form=SimpleNamespace(actionAdd_ons=action),
        )
    )
    for entry in entries:
        with Replay(entry, Path(archives[entry["path"]]).read_bytes()) as client:
            _, result = addons.download_and_install_addon(
                manager, client, entry["anki"]["id"]
            )
        if not isinstance(result, addons.InstallOk) or not result.compatible:
            raise ValueError(
                f"native Anki installer rejected {entry['path']}: {result}"
            )
    expected = sorted(str(entry["anki"]["id"]) for entry in entries)
    if manager.allAddons() != expected:
        raise ValueError("native installed add-on identities changed")
    return {name: manager.addonMeta(name) for name in expected}


def capture(request):
    root = Path(request["root"])
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    archives = {}
    with Client() as client:
        for id in request["addons"]:
            downloaded = addons.download_addon(client, id)
            if isinstance(downloaded, addons.DownloadError):
                raise TypeError(
                    f"native AnkiWeb download failed for {id}: {downloaded}"
                )
            metadata = {
                field.name: getattr(downloaded, field.name)
                for field in dataclasses.fields(downloaded)
                if field.name != "data"
            }
            metadata["id"] = id
            filename = f"{id}.ankiaddon"
            archive = root / filename
            archive.write_bytes(downloaded.data)
            archives[filename] = str(archive)
            entries.append(
                {
                    "path": filename,
                    "url": client.response.url,
                    "anki": metadata,
                    "bytesSha256": hashlib.sha256(downloaded.data).hexdigest(),
                }
            )
    metadata = install(root / "installed", entries, archives)
    return {"entries": entries, "metadata": metadata}


def replay(request):
    metadata = install(
        Path(request["output"]) / "addons", request["entries"], request["archives"]
    )
    if metadata != request["metadata"]:
        raise ValueError("native Anki archive metadata changed")
    (Path(request["output"]) / "manifest.json").write_text(
        json.dumps(metadata, sort_keys=True) + "\n"
    )
    return metadata


request = json.loads(Path(os.environ["ANKI_PURIFIER_REQUEST"]).read_text())
if request["action"] == "capture":
    response = capture(request)
elif request["action"] == "install":
    response = replay(request)
else:
    raise ValueError("unknown native Anki operation")
Path(os.environ["ANKI_PURIFIER_RESPONSE"]).write_text(
    json.dumps(response, sort_keys=True) + "\n"
)
