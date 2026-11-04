import json
import sys
from pathlib import Path

source, output, destination = sys.argv[1:]
request = json.loads(Path(source).read_text())
request["output"] = output
Path(destination).write_text(json.dumps(request))
