"""guac backup/export — bundle all persistent state into one JSON export.

The gateway's state (users, advertisers, offers, ledger, attribution, ad
cadence, supplier quality, magic-link nonces) lives on a Fly volume. If that
volume is lost or an operator wants a snapshot, this produces a single JSON
object with everything, tagged with a timestamp and checksum for integrity.
"""
import argparse
import hashlib
import json
import datetime as _dt

import config


def _read_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _read_lines(path):
    """Read a JSONL file into a list of parsed rows."""
    out = []
    if not path.exists():
        return []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
    except Exception:
        pass
    return out


def build_bundle():
    """Return a dict with every piece of persistent state + a checksum."""
    data = {
        "version": 1,
        "exported_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "state": _read_json(config.STATE_FILE),
        "users": _read_json(config.USERS_FILE),
        "advertisers": _read_json(config.ADVERTISERS_FILE),
        "offers": _read_json(config.OFFERS_FILE),
        "magic_used": _read_json(config.MAGIC_USED_FILE),
        "supplier_state": _read_json(config.SUPPLIER_STATE_FILE),
        "ledger": _read_lines(config.LEDGER_FILE),
        "attribution": _read_lines(config.ATTRIBUTION_FILE),
        "payments": _read_lines(config.PAYMENTS_LEDGER),
    }
    # Checksum over the serialized bundle so a restore/operator can verify the
    # export wasn't truncated or tampered in transit.
    body = json.dumps(data, sort_keys=True)
    data["checksum"] = hashlib.sha256(body.encode()).hexdigest()
    return data


def restore_bundle(bundle):
    """Write a previously-exported bundle back to the state files. Returns the
    list of (path, ok) for the parts that were present in the bundle."""
    results = []
    writes = [
        (config.STATE_FILE, "state"),
        (config.USERS_FILE, "users"),
        (config.ADVERTISERS_FILE, "advertisers"),
        (config.OFFERS_FILE, "offers"),
        (config.MAGIC_USED_FILE, "magic_used"),
        (config.SUPPLIER_STATE_FILE, "supplier_state"),
    ]
    for path, key in writes:
        val = bundle.get(key)
        if val is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(val, indent=2))
            results.append((path.name, True))
    # JSONL files
    for path, key in [(config.LEDGER_FILE, "ledger"),
                      (config.ATTRIBUTION_FILE, "attribution"),
                      (config.PAYMENTS_LEDGER, "payments")]:
        rows = bundle.get(key)
        if rows is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
            results.append((path.name, True))
    return results


def main():
    ap = argparse.ArgumentParser(description="guac backup/export")
    ap.add_argument("--out", default="guac-backup.json")
    ap.add_argument("--restore", metavar="FILE", default=None)
    args = ap.parse_args()

    if args.restore:
        with open(args.restore) as f:
            bundle = json.load(f)
        results = restore_bundle(bundle)
        print("restored:", ", ".join(name for name, ok in results))
        return

    bundle = build_bundle()
    with open(args.out, "w") as f:
        json.dump(bundle, f, indent=2)
    print(f"exported {len(bundle['ledger'])} ledger rows, "
          f"{len(bundle['attribution'])} attribution rows to {args.out}")
    print(f"checksum: {bundle['checksum']}")


if __name__ == "__main__":
    main()
