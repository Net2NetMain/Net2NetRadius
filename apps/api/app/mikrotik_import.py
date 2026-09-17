import re
from dataclasses import dataclass


@dataclass
class MikrotikUser:
    username: str
    password: str
    address: str
    rate: str
    uisp_client_id: str | None
    disabled: bool


def _rate_value(value: str) -> float:
    value = value.strip().replace('`', '')
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([kKmMgG]?)", value)
    if not match:
        raise ValueError(f"Unsupported rate value: {value}")
    number, unit = match.groups()
    multiplier = {"": 1 / 1_000_000, "k": 1 / 1_000, "m": 1.0, "g": 1_000.0}[unit.lower()]
    return float(number) * multiplier


def split_rate(rate: str) -> tuple[float, float]:
    parts = rate.split("/")
    if len(parts) != 2:
        raise ValueError(f"Unsupported rate limit: {rate}")
    # User Manager exports the rate in the opposite order to the customer
    # convention used by this platform: old 10/20 becomes 20/10.
    return _rate_value(parts[1]), _rate_value(parts[0])


def parse_user_manager_export(export_text: str) -> list[MikrotikUser]:
    """Parse the user records from a RouterOS User Manager .rsc export."""
    text = re.sub(r"\\\r?\n\s*", "", export_text)
    marker = "/user-manager user\n"
    if marker not in text:
        raise ValueError("The export has no /user-manager user section")
    section = text.split(marker, 1)[1].split("\n/user-manager", 1)[0]
    users: list[MikrotikUser] = []
    for record in re.findall(r"(?:^|\n)add\s+(.+?)(?=\nadd\s+|\Z)", section, re.DOTALL):
        name = re.search(r"\bname=([^\s]+)", record)
        password = re.search(r"\bpassword=([^\s]+)", record)
        attributes = re.search(r'\battributes=(?:"([^"]*)"|([^\s]+))', record)
        if not (name and password and attributes):
            continue
        attrs = attributes.group(1) or attributes.group(2)
        address = re.search(r"Framed-IP-Address:([^,\s]+)", attrs)
        rate = re.search(r"Mikrotik-Rate-Limit:([^,\s]+)", attrs)
        if not (address and rate):
            continue
        uisp = re.search(r"UISP-Client-ID:([^,\s]+)", attrs)
        users.append(
            MikrotikUser(
                username=name.group(1), password=password.group(1), address=address.group(1),
                rate=rate.group(1), uisp_client_id=uisp.group(1) if uisp else None,
                disabled=bool(re.search(r"\bdisabled=yes\b", record)),
            )
        )
    if not users:
        raise ValueError("No usable User Manager users were found in the export")
    return users
