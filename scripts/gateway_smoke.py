"""Explicit dummy-key Docker gateway smoke; no provider calls or image pulls."""

import argparse
import json

from agentbase.fs import AgentBaseError
from agentbase.gateway import self_test


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker", action="store_true", required=True)
    parser.add_argument("--image", required=True, help="Trusted preinstalled pinned Node image")
    args = parser.parse_args()
    print(json.dumps(self_test(args.image, consent=args.docker), indent=2))


if __name__ == "__main__":
    try:
        main()
    except AgentBaseError as error:
        raise SystemExit(str(error)) from None
