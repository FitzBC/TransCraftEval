import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Face Watch prototype")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run("face_watch.main:app", host=args.host, port=args.port, reload=False)
