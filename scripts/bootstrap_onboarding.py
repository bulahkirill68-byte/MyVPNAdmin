"""Root-only metadata bridge for the installer. Never prints the server private key."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ip', required=True)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if not Path('/usr/local/etc/xray/config.json').is_file():
        raise SystemExit(3)
    sys.path.insert(0, '/opt/reality-agent')
    import agent
    try:
        if args.prepare:
            agent.prepare_existing()
        payload = agent.onboarding(args.ip)
    except (ValueError, KeyError, StopIteration):
        print('Xray требует подготовки API/email/stats. Выполните её в панели или с --prepare-existing.', file=sys.stderr)
        raise SystemExit(4) from None
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == '__main__':
    main()
