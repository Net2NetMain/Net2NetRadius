import socket
from pathlib import Path

from pyrad import dictionary, packet

radius_dictionary = dictionary.Dictionary(str(Path(__file__).parents[1] / "radius" / "dictionary"))
request = packet.AuthPacket(code=packet.AccessRequest, secret=b"12345678", dict=radius_dictionary)
request["User-Name"] = "lab-test@example.local"
request["User-Password"] = request.PwCrypt("lab-test-password")

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
    client.settimeout(3)
    client.sendto(request.RequestPacket(), ("127.0.0.1", 1812))
    raw, _ = client.recvfrom(4096)

reply = packet.AuthPacket(packet=raw, secret=b"12345678", dict=radius_dictionary)
print(f"Authenticator valid: {request.VerifyReply(reply, raw)}")
print(
    "Access-Accept" if reply.code == packet.AccessAccept else f"Unexpected response: {reply.code}"
)
print(dict(reply))
