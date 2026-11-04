"""Create a note with the locked add-on and export native, reproducible text."""

import importlib
import json
import os
from pathlib import Path

import aqt
from anki.collection import DeckIdLimit

addon = importlib.import_module("2055492159")
assert addon.ac.version() == 6
source = Path(__file__).resolve().parent
answer = json.loads((source / "answer.json").read_text())["answer"]
deck = addon.ac.createDeck("Purifier Fixture")
previous = addon.ac.findNotes("tag:purifier_fixture")
if previous:
    addon.ac.deleteNotes(previous)
addon.ac.addNote(
    {
        "deckName": "Purifier Fixture",
        "modelName": "Basic",
        "fields": {"Front": "What is the answer?", "Back": answer},
        "tags": ["purifier_fixture"],
        "options": {"allowDuplicate": True},
    }
)
output = Path(os.environ.get("ANKI_PURIFIER_OUTPUT", "output"))
output.mkdir(parents=True, exist_ok=True)
count = aqt.mw.col.export_note_csv(
    out_path=str(output / "notes.txt"),
    limit=DeckIdLimit(deck_id=deck),
    with_html=True,
    with_tags=False,
    with_deck=False,
    with_notetype=False,
    with_guid=False,
)
assert count == 1
