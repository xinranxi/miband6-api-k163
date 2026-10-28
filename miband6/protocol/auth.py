"""
EC authentication handshake for Mi Band 6.

The handshake is a three-message exchange over the chunked-transfer
characteristic (UUID 00000016-...). It uses ECDH on sect163k1 to derive
a session key, then proves knowledge of the pairing key by encrypting a
device-supplied nonce with both the pairing key and the session key.

Protocol
--------
    host -> band   [03]                                  (init)
    host -> band   [00]                                  (init)
    host -> band   [04 02 00 02] + client_pub (48 B)      (public key)
    band -> host   [10 04 01] + nonce (16 B) + band_pub (48 B)
    host -> band   [05] + AES-ECB(pairing_key, nonce)
                        + AES-ECB(session_key, nonce)
    band -> host   [10 05 01]                             (success)

where
    shared       = ECDH_sect163k1(client_priv, band_pub)     (24 bytes)
    session_key  = shared[8:24] XOR pairing_key              (16 bytes)
"""
import os

from Crypto.Cipher import AES

from ..crypto import k163
from . import chunked


class AuthError(Exception):
    pass


def _new_keypair():
    """Generate a sect163k1 key pair valid for the handshake."""
    while True:
        words = k163._bytes_to_words(os.urandom(24))
        words[5] &= 0x3  # keep within the 163-bit group order
        d = k163.words6_to_int(words)
        if d < 1 or d >= k163.N:
            continue
        if d.bit_length() < 82:  # firmware rejects very short scalars
            continue
        P = k163.point_mul(d, (k163.GX, k163.GY))
        if P is None:
            continue
        return d, P


def derive_session_key(shared: bytes, pairing_key: bytes) -> bytes:
    """session_key = shared[8:24] XOR pairing_key."""
    return bytes(a ^ b for a, b in zip(shared[8:24], pairing_key))


def build_response(nonce: bytes, pairing_key: bytes, session_key: bytes):
    """Build the [05] + enc1 + enc2 message."""
    enc1 = AES.new(pairing_key, AES.MODE_ECB).encrypt(nonce)
    enc2 = AES.new(session_key, AES.MODE_ECB).encrypt(nonce)
    return bytes([0x05]) + enc1 + enc2


async def authenticate(client, pairing_key: bytes, ctx, xh_start: int = 0):
    """Run the full handshake against a connected BleakClient.

    `ctx` must expose a ``frames`` list that incoming chunked-read
    notifications are appended to.

    Returns the derived session key on success.
    """
    from ..device import write_message  # local import to avoid cycle

    d, client_pub = _new_keypair()
    pub_bytes = k163.pubkey_to_bytes(client_pub)

    # --- init ---
    await write_message(client, xh_start + 0, bytes([0x03]), tag=(0x00, 0x00))
    await _sleep(0.25)
    await write_message(client, xh_start + 1, bytes([0x00]), tag=chunked.TAG_AUTH)
    await _sleep(0.25)

    # --- send public key ---
    ctx.frames.clear()
    await write_message(client, xh_start + 2,
                        bytes([0x04, 0x02, 0x00, 0x02]) + pub_bytes,
                        tag=chunked.TAG_AUTH)
    await _sleep(3.5)

    payload = chunked.reassemble_first(ctx.frames)
    if not payload or not payload.startswith(b"\x10\x04\x01"):
        raise AuthError("unexpected auth response: %r" % (payload,))

    body = payload[3:]
    if len(body) < 64:
        raise AuthError("auth response too short: %d bytes" % len(body))

    nonce = body[:16]
    band_pub = k163.bytes_to_pubkey(body[16:64])

    # --- ECDH + response ---
    shared = k163.ecdh(d, band_pub)
    session_key = derive_session_key(shared, pairing_key)
    response = build_response(nonce, pairing_key, session_key)

    ctx.frames.clear()
    await write_message(client, xh_start + 3, response, tag=chunked.TAG_AUTH)
    await _sleep(2.5)

    final = b"".join(ctx.frames)
    if b"\x10\x05\x01" not in final:
        raise AuthError("authentication rejected: %s" % final.hex())

    return session_key


async def _sleep(seconds):
    import asyncio
    await asyncio.sleep(seconds)
