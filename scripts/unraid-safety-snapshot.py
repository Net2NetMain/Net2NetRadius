"""Run inside the existing appliance before an update; never removes originals."""

import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

root = Path("/data")
target = root / ("before-android-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
target.mkdir(exist_ok=False)
with sqlite3.connect("file:/data/net2net.db?mode=ro", uri=True) as source:
    with sqlite3.connect(target / "net2net.db") as destination:
        source.backup(destination)
        assert destination.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        manifest = {}
        for table in (
            "subscriber",
            "package",
            "router",
            "ippool",
            "appuser",
            "platformconfiguration",
        ):
            rows = destination.execute(
                f'SELECT * FROM "{table}" ORDER BY rowid'
            ).fetchall()
            manifest[table] = {
                "count": len(rows),
                "sha256": hashlib.sha256(
                    json.dumps(rows, default=str).encode()
                ).hexdigest(),
            }
for name in (
    "secret.key",
    "branding.json",
    "wisp-logo",
    "wisp-logo.type",
    "backups",
    "certs",
):
    item = root / name
    if item.is_dir():
        shutil.copytree(item, target / name)
    elif item.is_file():
        shutil.copy2(item, target / name)
manifest["secret.key"] = {
    "sha256": hashlib.sha256((target / "secret.key").read_bytes()).hexdigest()
}
(target / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(
    json.dumps(
        {
            "snapshot": str(target),
            "records": {k: v.get("count") for k, v in manifest.items() if "count" in v},
        }
    )
)
