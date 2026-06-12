from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402


def main() -> None:
    payload = app.build_dashboard(refresh=True, update_dr_prices=True)
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    public_payload = {
        **payload,
        "rows": [app.to_public_row(row) for row in payload.get("rows", [])],
    }
    (data_dir / "dashboard.json").write_text(
        json.dumps(public_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rows = public_payload.get("rows", [])
    if rows:
        with (data_dir / "dashboard.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    counts = public_payload.get("counts", {})
    print(
        "Generated data/dashboard.json "
        f"confirmed_dr={counts.get('confirmed_dr')} "
        f"with_diff={counts.get('with_diff')} "
        f"needs_mapping={counts.get('needs_mapping')}"
    )


if __name__ == "__main__":
    main()
