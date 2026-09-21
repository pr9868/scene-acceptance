"""Serve only this workspace, on localhost. No dependencies beyond Python."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from functools import partial
import argparse
p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);args=p.parse_args()
root=Path(__file__).resolve().parents[1]
handler=partial(SimpleHTTPRequestHandler,directory=str(root))
print(f'Viewer: http://127.0.0.1:{args.port}/viewer/',flush=True)
ThreadingHTTPServer(('127.0.0.1',args.port),handler).serve_forever()
