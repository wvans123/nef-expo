"""Portable single-process entrypoint: python start.py [--port 8069]."""
import argparse
import os
import shutil

from integration_config import ROOT, local_path


def prepare_configs():
    targets = [
        (ROOT / "config" / "integration.example.json", local_path()),
        (ROOT / "config" / "composer.example.json", ROOT / "config" / "composer.local.json"),
    ]
    for template, path in targets:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(template, path)
            print(f"Created local config: {path}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8069)
    args = parser.parse_args()
    os.chdir(ROOT)
    prepare_configs()
    path = local_path()
    print(f"Integration addresses: {path}", flush=True)
    print(f"Local page: http://127.0.0.1:{args.port}/", flush=True)
    print(f"LAN page: http://<NEF-IP>:{args.port}/ (0.0.0.0 is a bind address, not a client URL)", flush=True)
    print("Single process; restart clears demo accounts, subscriptions and callback keys.", flush=True)
    import uvicorn
    uvicorn.run("server:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
