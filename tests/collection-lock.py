"""Anki's native backend must retain exclusion across distinct GUI instances."""

import sys
import tempfile
from pathlib import Path

from sdk_script import sdk_script

original = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix="anki-collection-lock-") as temporary:
    root = Path(temporary)
    collection = root / "collection.anki2"
    contender = root / "contender.py"
    contender.write_text(
        "from anki.collection import Collection\n"
        f"try: col=Collection({str(collection)!r})\n"
        "except Exception as error:\n"
        " assert 'Anki already open' in str(error),str(error)\n"
        "else:\n"
        " col.close()\n"
        " raise AssertionError('concurrent collection open succeeded')\n"
    )
    holder = root / "holder.py"
    holder.write_text(
        "import os,subprocess\n"
        "from anki.collection import Collection\n"
        f"col=Collection({str(collection)!r})\n"
        "try:\n"
        f" result=subprocess.run([{str(original / 'bin/anki')!r},'--version'],"
        f"env=os.environ.copy()|{{'ANKI_TEST_SCRIPT':{str(contender)!r},"
        "'ANKI_SINGLE_INSTANCE_KEY':'different-instance'},capture_output=True,text=True)\n"
        " assert result.returncode==0,result.stdout+result.stderr\n"
        "finally: col.close()\n"
        f"reopened=Collection({str(collection)!r})\n"
        "reopened.close()\n"
    )
    sdk_script(original, holder, root / "sdk")
print("Native collection exclusion survives separate instance identities")
