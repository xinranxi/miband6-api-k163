"""
Huami chunked-transfer framing.

Application messages are chunked into BLE writes of at most MTU bytes.
Each frame has a small header:

  首帧 (first frame), 11-byte header:
      0x03 | flags | 0x00 | xh | count | length (LE u32) | tag (2 bytes) | data

  后续帧 (continuation), 5-byte header:
      0x03 | flags | 0x00 | xh | count | data

  flags:
      0x01  first frame of a message
      0x06  last frame of a message
      0x07  single frame (both first and last)

  xh:    per-message transfer handle (increments per message)
  count: frame sequence number within the message

The two `tag` bytes classify the message:
      0x0000 / 0x8200  authentication
      0x9000           encrypted payload (session-key encrypted)
      0x0300           identity / key exchange
      0x0500           feature toggles
      0x3200           data requests
      0x0a00           time / status
"""

DEFAULT_MTU = 23

# Message tags
TAG_AUTH = (0x82, 0x00)
TAG_ENCRYPTED = (0x90, 0x00)
TAG_IDENTITY = (0x03, 0x00)
TAG_FEATURE = (0x05, 0x00)
TAG_DATA = (0x32, 0x00)
TAG_STATUS = (0x0a, 0x00)


def encode_frames(xh: int, data: bytes, tag=(0x82, 0x00), mtu: int = DEFAULT_MTU):
    """Split a message into wire frames.

    Returns a list of bytes objects, each ready to be written to the
    chunked-write characteristic.
    """
    frames = []
    header_size = 11
    remaining = len(data)
    count = 0
    offset = 0

    while remaining > 0:
        max_chunk = mtu - 3 - header_size
        copybytes = min(remaining, max_chunk)
        flags = 0
        buf = bytearray(copybytes + header_size)

        if count == 0:
            flags |= 0x01
            buf[5] = len(data) & 0xFF
            buf[6] = (len(data) >> 8) & 0xFF
            buf[7] = (len(data) >> 16) & 0xFF
            buf[8] = (len(data) >> 24) & 0xFF
            buf[9] = tag[0]
            buf[10] = tag[1]
        if remaining <= max_chunk:
            flags |= 0x06

        buf[0] = 0x03
        buf[1] = flags
        buf[2] = 0x00
        buf[3] = xh & 0xFF
        buf[4] = count & 0xFF
        buf[header_size:] = data[offset:offset + copybytes]

        frames.append(bytes(buf))
        offset += copybytes
        remaining -= copybytes
        header_size = 5
        count += 1

    return frames


def decode_frames(frames):
    """Reassemble application messages from received notification frames.

    Returns a list of (tag, payload) tuples in arrival order.
    """
    messages = []
    current = None
    tag = None

    for fr in frames:
        if not fr or fr[0] != 0x03:
            continue
        flags = fr[1]

        if flags & 0x01:
            # First frame: 11-byte header
            if len(fr) < 11:
                continue
            tag = (fr[9], fr[10])
            current = bytearray(fr[11:])
        elif current is not None:
            # Continuation: 5-byte header
            current += fr[5:]

        if flags & 0x06:
            # Last frame
            if current is not None:
                messages.append((tag, bytes(current)))
            current = None
            tag = None

    return messages


def reassemble_first(frames, tag_bytes=None):
    """Reassemble and return the first message payload (optionally filtered by tag)."""
    for t, payload in decode_frames(frames):
        if tag_bytes is None or t == tuple(tag_bytes):
            return payload
    return None
