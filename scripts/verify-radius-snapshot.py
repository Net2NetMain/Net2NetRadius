"""Read-only record/key comparison. Run inside a container with a safety manifest."""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/manifest.json")
expected = json.loads(manifest_path.read_text())
with sqlite3.connect("file:/data/net2net.db?mode=ro", uri=True) as database:
    assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    for table, record in expected.items():
        if table == "secret.key":
            actual = hashlib.sha256(Path("/data/secret.key").read_bytes()).hexdigest()
        else:
            rows = database.execute(
                f'SELECT * FROM "{table}" ORDER BY rowid'
            ).fetchall()
            actual = hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()
            assert len(rows) == record["count"], f"{table}: record count changed"
        assert actual == record["sha256"], f"{table}: record contents changed"
        print(
            f"Preserved: {table}"
            + (f" ({record['count']} records)" if "count" in record else "")
        )
print("Database integrity and all original record/key fingerprints match")
