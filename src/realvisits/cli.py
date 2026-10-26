"""realvisits on the command line.

    realvisits check "<user agent>" [address] [referrer] [--own PATTERN] [--data DIR]
    realvisits refresh --out DIR [--spam] [--asns FILE] [--ip2asn FILE]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from realvisits import __version__
from realvisits.classify import DATA, Classifier


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="realvisits", description="Sort website visits into people, bots and your own checks.")
    ap.add_argument("--version", action="version", version=f"realvisits {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="classify one visit")
    c.add_argument("agent")
    c.add_argument("ip", nargs="?", default="")
    c.add_argument("ref", nargs="?", default="")
    c.add_argument("--own", default=None, help="regular expression for your own checks' user agents")
    c.add_argument("--data", default=None, help="folder with refreshed lists (realvisits refresh --out)")
    r = sub.add_parser("refresh", help="rebuild the cloud ranges (and with --spam, the spam list)")
    r.add_argument("--out", required=True)
    r.add_argument("--spam", action="store_true", help="also merge a public referrer-spam list")
    r.add_argument("--asns", default=str(DATA / "datacenter_asns.txt"), help="the ASN policy to build from")
    r.add_argument("--ip2asn", default=None, help="a local ip2asn TSV instead of downloading it")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        print(Classifier(own_agents=args.own, data_dir=args.data).classify(args.agent, args.ip, args.ref))
        return 0
    from realvisits import refresh  # noqa: PLC0415
    return refresh.run(Path(args.out), Path(args.asns), args.ip2asn, args.spam)


if __name__ == "__main__":
    sys.exit(main())
