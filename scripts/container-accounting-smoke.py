"""Run only in an isolated validation container, never in a live WISP appliance."""
import sqlite3
import subprocess
import time

username = "android-collector-smoke"
identifier = "android-smoke-" + str(time.time_ns())
with sqlite3.connect("/data/net2net.db") as database:
    previous_id = database.execute("SELECT COALESCE(MAX(id),0) FROM accountingsession").fetchone()[0]
packet = (
    f'User-Name = "{username}"\nAcct-Session-Id = "{identifier}"\n'
    "Acct-Status-Type = Interim-Update\nNAS-IP-Address = 127.0.0.1\n"
    "Acct-Session-Time = 60\nAcct-Output-Octets = 123456\n"
    "Acct-Input-Octets = 789\nMessage-Authenticator = 0x00\n"
)
result = subprocess.run(
    ["radclient", "127.0.0.1:1813", "acct", "testing123"],
    input=packet, text=True, capture_output=True, timeout=15,
)
assert result.returncode == 0, result.stderr
for attempt in range(15):
    with sqlite3.connect("/data/net2net.db") as database:
        row = database.execute(
            "SELECT output_bytes,input_bytes FROM accountingsession WHERE username=? AND id>? ORDER BY id DESC LIMIT 1",
            (username, previous_id),
        ).fetchone()
    if row == (123456, 789):
        print("FreeRADIUS UDP accounting -> journal -> database: passed")
        break
    time.sleep(1)
else:
    raise RuntimeError("Accounting record was not imported")
