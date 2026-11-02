"""Start Worldsmith on this computer: `python -m worldsmith [--port N] [--no-browser]`."""
import argparse
import threading
import webbrowser

import uvicorn

# Port 8795 keeps Worldsmith clear of Dungeon (8785), Companion (8775) and Study (8765), so they can run together.
PORT = 8795


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Start Prospero's Worldsmith.")
    parser.add_argument('--port', type=int, default=PORT)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    url = f'http://127.0.0.1:{args.port}'
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [url]).start()
    print(f"Prospero's Worldsmith is running at {url}. Close this window to stop it.")
    uvicorn.run('worldsmith.main:app', host='127.0.0.1', port=args.port, log_level='warning')
