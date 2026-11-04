import os
import runpy
import sys
import traceback

try:
    if os.environ.get("ANKI_PURIFIER_SEED"):
        runpy.run_path(os.environ["ANKI_PURIFIER_SEED"], run_name="__main__")
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    if os.environ.get("ANKI_PURIFIER_REQUEST"):
        runpy.run_path(os.environ["ANKI_PURIFIER_HELPER"], run_name="__main__")
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    if os.environ.get("ANKI_PURIFIER_ENVIRONMENT"):
        from anki_purifier_guard import install

        install()
        if os.environ.get("ANKI_PURIFIER_SCRIPT"):
            from anki_purifier_project import install as install_project

            install_project()
except BaseException:
    os.write(2, traceback.format_exc().encode())
    os._exit(1)
