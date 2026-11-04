"""Run a project script after native profile and add-on initialization."""

import os
import runpy
import sys
import traceback
from pathlib import Path


def install():
    import aqt
    from aqt import gui_hooks
    from aqt.qt import QTimer

    status = None
    original_run = aqt.run

    def run(*args, **kwargs):
        result = original_run(*args, **kwargs)
        return result if status is None else status

    def profile_open():
        def execute():
            nonlocal status
            try:
                script = os.environ["ANKI_PURIFIER_SCRIPT"]
                sys.argv = [script]
                sys.path.insert(0, str(Path(script).resolve().parent))
                runpy.run_path(script, run_name="__main__")
                status = 0
            except SystemExit as error:
                status = (
                    0
                    if error.code is None
                    else error.code
                    if isinstance(error.code, int)
                    else 1
                )
            except BaseException:
                os.write(2, traceback.format_exc().encode())
                status = 1
            aqt.mw.unloadProfileAndExit()

        QTimer.singleShot(0, execute)

    aqt.run = run
    gui_hooks.profile_did_open.append(profile_open)
