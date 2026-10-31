"""Start the FigAssemble server without opening a window (for testing the UI in any browser).

    python tools/serve.py [--port 8765] [--url-file tools/output/url.txt]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from figassemble.app.api import Api          # noqa: E402
from figassemble.app.server import start_server  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=0)
ap.add_argument("--url-file")
args = ap.parse_args()
srv = start_server(Api(), args.port)
url = srv.url + "ui/index.html"
print(url, flush=True)
if args.url_file:
    with open(args.url_file, "w") as fh:
        fh.write(url)
try:
    while True:
        time.sleep(3600)
except KeyboardInterrupt:
    pass
