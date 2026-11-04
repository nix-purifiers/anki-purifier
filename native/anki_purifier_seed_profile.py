"""Seed only the isolated profile used by scripted runs and Nix builds."""

import os
from pathlib import Path

from aqt.profiles import ProfileManager, VideoDriver

base = Path(os.environ["ANKI_PURIFIER_PROFILE"])
base.mkdir(parents=True, exist_ok=True)
manager = ProfileManager(base)
manager.setupMeta()
manager.create("Purifier")
manager.load("Purifier")
manager.meta.update(defaultLang="en_US", firstRun=False, updates=False)
manager.profile["autoSync"] = False
manager.set_video_driver(VideoDriver.Software)
manager.save()
manager.db.close()
