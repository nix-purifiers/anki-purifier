"""Prototype: keep Anki's native loader and preferences, constrain managed code."""

import importlib.abc
import importlib.machinery
import json
import os
import sys
from pathlib import Path


def install():
    environment = Path(os.environ["ANKI_PURIFIER_ENVIRONMENT"]).resolve()
    overlay = Path(os.environ["ANKI_ADDONS"]).resolve()
    state = Path(os.environ["ANKI_PURIFIER_STATE"]).resolve()
    metadata = {
        path.name: json.loads((path / "meta.json").read_text())
        for path in (environment / "addons").iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is None:
                return None
            candidates = []
            if spec.origin and Path(spec.origin).is_absolute():
                candidates.append((Path(spec.origin), False))
            else:
                candidates.extend(
                    (Path(item), True)
                    for item in (spec.submodule_search_locations or [])
                )
            managed = False
            for candidate, directory in candidates:
                if not candidate.is_relative_to(state):
                    continue
                if not candidate.is_relative_to(overlay):
                    raise ImportError("mutable Anki add-on source was rejected")
                relative = candidate.relative_to(overlay)
                native = environment / "addons" / relative
                if directory:
                    if not native.is_dir():
                        raise ImportError("unlocked Anki add-on namespace")
                elif candidate.resolve() != native.resolve() or not native.is_file():
                    raise ImportError("unlocked Anki add-on code")
                managed = True
            return spec if managed else None

    sys.meta_path.insert(0, Finder())

    from aqt import addons

    original_read = addons.AddonManager.addonMeta
    original_write = addons.AddonManager.writeAddonMeta

    def locked_metadata(module, value):
        if module in metadata:
            value = value.copy()
            value.update(
                {
                    key: item
                    for key, item in metadata[module].items()
                    if key not in {"config", "disabled", "update_enabled"}
                }
            )
            value["update_enabled"] = False
        return value

    def read(self, module):
        return locked_metadata(module, original_read(self, module))

    def write(self, module, value):
        return original_write(self, module, locked_metadata(module, value))

    addons.AddonManager.addonMeta = read
    addons.AddonManager.writeAddonMeta = write

    def frozen(*args, **kwargs):
        raise RuntimeError("Anki add-ons are locked; run anki-purifier lock --update")

    addons.AddonManager.install = lambda *args, **kwargs: addons.InstallError(
        errmsg="Anki add-ons are locked; run anki-purifier lock --update"
    )
    addons.AddonManager._install = frozen
    addons.AddonManager.deleteAddon = frozen
    addons.download_addon = lambda *args, **kwargs: addons.DownloadError(
        exception=RuntimeError("Anki add-ons are locked")
    )
    addons.fetch_update_info = lambda ids: []
    original_dialog_selection = addons.AddonsDialog._onAddonSelectionChanged

    def freeze_buttons(dialog):
        for name in ["getAddons", "installFromFile", "checkForUpdates", "delete_2"]:
            button = getattr(dialog.form, name)
            button.setEnabled(False)
            button.setToolTip("Add-ons are locked; run anki-purifier lock --update")

    def selection_changed(dialog):
        result = original_dialog_selection(dialog)
        freeze_buttons(dialog)
        return result

    addons.AddonsDialog._onAddonSelectionChanged = selection_changed
    import aqt

    aqt.AnkiApp.KEY = os.environ["ANKI_SINGLE_INSTANCE_KEY"]
