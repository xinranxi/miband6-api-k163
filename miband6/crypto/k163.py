"""
sect163r2 (NIST B-163) binary-field elliptic curve.

The historical module name k163 is retained for compatibility.

This is the curve used by Xiaomi Mi Band 6 (and likely other Huami/Xiaomi
devices with recent firmware) for its ECDH key agreement during the
Bluetooth authentication handshake.

Curve equation over GF(2^163):
    y^2 + x*y = x^3 + a*x^2 + b

Field polynomial:
    x^163 + x^7 + x^6 + x^3 + 1

No external dependencies. Pure Python, easy to audit.
"""

M_BITS = 163

# Reduction polynomial: x^163 + x^7 + x^6 + x^3 + 1
_REDUCTION_POLY = (1 << 163) | (1 << 7) | (1 << 6) | (1 << 3) | 1

# Curve coefficients
A = 1
B = 0x20A601907B8C953CA1481EB10512F78744A3205FD

# Base point
GX = 0x03F0EBA16286A2D57EA0991168D4994637E8343E36
GY = 0xD51FBC6C71A0094FA2CDD545B11C5C0C797324F1

# Order of the base point
N = 0x040000000000000000000292FE77E70C12A4234C33


# --------------------------------------------------------------------------
# GF(2^163) arithmetic
# --------------------------------------------------------------------------
def gf_mul(x: int, y: int) -> int:
    """Multiply two elements of GF(2^163).

    Carry-less multiplication followed by reduction modulo the field
    polynomial.
    """
    result = 0
    while y:
        if y & 1:
            result ^= x
        y >>= 1
        x <<= 1
    # Reduce to < 2^163
    while result.bit_length() > M_BITS:
        result ^= _REDUCTION_POLY << (result.bit_length() - M_BITS - 1)
    return result


def gf_square(x: int) -> int:
    return gf_mul(x, x)


def gf_inv(x: int) -> int:
    """Multiplicative inverse in GF(2^163) via the extended Euclidean algorithm."""
    if x == 0:
        raise ZeroDivisionError("0 has no inverse in GF(2^163)")
    u, v = x, _REDUCTION_POLY
    g1, g2 = 1, 0
    while u != 1:
        j = u.bit_length() - v.bit_length()
        if j < 0:
            u, v = v, u
            g1, g2 = g2, g1
            j = -j
        u ^= v << j
        g1 ^= g2 << j
    return g1


# --------------------------------------------------------------------------
# Point arithmetic (affine coordinates, points are (x, y) tuples or None)
# --------------------------------------------------------------------------
def point_add(P, Q):
    """Add two points on the curve y^2 + xy = x^3 + ax^2 + b."""
    if P is None:
        return Q
    if Q is None:
        return P
    x1, y1 = P
    x2, y2 = Q

    if x1 == x2:
        if y1 != y2:
            # P + (-P) = infinity
            return None
        if x1 == 0:
            # Point of order 2
            return None
        # Point doubling
        lam = x1 ^ gf_mul(y1, gf_inv(x1))
        x3 = gf_square(lam) ^ lam ^ A
        y3 = gf_square(x1) ^ gf_mul(lam ^ 1, x3)
        return (x3, y3)

    # Point addition
    lam = gf_mul(y1 ^ y2, gf_inv(x1 ^ x2))
    x3 = gf_square(lam) ^ lam ^ x1 ^ x2 ^ A
    y3 = gf_mul(lam, x1 ^ x3) ^ x3 ^ y1
    return (x3, y3)


def point_neg(P):
    if P is None:
        return None
    x, y = P
    return (x, x ^ y)


def point_mul(k: int, P):
    """Scalar multiplication using double-and-add."""
    if k == 0 or P is None:
        return None
    if k < 0:
        return point_mul(-k, point_neg(P))
    result = None
    addend = P
    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return result


def is_on_curve(P) -> bool:
    """Check whether a point satisfies the curve equation."""
    if P is None:
        return True
    x, y = P
    lhs = gf_square(y) ^ gf_mul(x, y)
    rhs = gf_mul(gf_square(x), x) ^ gf_mul(A, gf_square(x)) ^ B
    return lhs == rhs


# --------------------------------------------------------------------------
# Key encoding helpers
#
# Huami encodes keys as arrays of 6 little-endian uint32 words, making a
# 24-byte buffer of which only the low 163 bits are significant.
# --------------------------------------------------------------------------
def int_to_words6(value: int) -> list:
    """Encode an integer as 6 little-endian 32-bit words."""
    return [(value >> (32 * i)) & 0xFFFFFFFF for i in range(6)]


def words6_to_int(words) -> int:
    """Decode 6 little-endian 32-bit words into an integer."""
    return sum(w << (32 * i) for i, w in enumerate(words))


def pubkey_to_bytes(P) -> bytes:
    """Encode a public point as 48 bytes: X (6 words LE) || Y (6 words LE)."""
    x, y = P
    return _words_to_bytes(int_to_words6(x)) + _words_to_bytes(int_to_words6(y))


def bytes_to_pubkey(b: bytes):
    """Decode 48 bytes into a public point."""
    if len(b) != 48:
        raise ValueError("public key must be 48 bytes, got %d" % len(b))
    xw = _bytes_to_words(b[:24])
    yw = _bytes_to_words(b[24:])
    return (words6_to_int(xw), words6_to_int(yw))


def _words_to_bytes(words) -> bytes:
    import struct
    return struct.pack("<6I", *words)


def _bytes_to_words(b: bytes) -> list:
    import struct
    return list(struct.unpack("<6I", b))


def ecdh(private_scalar: int, peer_public) -> bytes:
    """Perform ECDH and return the shared secret as 24 bytes.

    The shared secret is the X coordinate of (private_scalar * peer_public),
    encoded as 6 little-endian uint32 words.
    """
    shared_point = point_mul(private_scalar, peer_public)
    if shared_point is None:
        raise ValueError("ECDH produced the point at infinity")
    return _words_to_bytes(int_to_words6(shared_point[0]))
