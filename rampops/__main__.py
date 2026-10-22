"""python -m rampops demo [--out FILE]"""
import argparse
import sys

from .report import render


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="rampops")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="run the synthetic end-to-end scenario")
    d.add_argument("--out", help="write the markdown report to this file")
    args = ap.parse_args(argv)
    text = render()
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
