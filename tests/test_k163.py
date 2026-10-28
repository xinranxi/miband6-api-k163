"""
Known-answer tests for the sect163k1 implementation.

These vectors let anyone verify that the curve arithmetic is correct
without needing a physical device. If these pass, the implementation
produces the same shared secrets as the real firmware.

(Vectors are captured handshake key pairs, scrubbed of any personal data.)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from miband6 import k163


# (private scalar, public point) pairs, encoded exactly as on the wire.
VECTORS = [
    {
        "priv": "2bb4d47ed5b15367bf8ed3f821b1b658344880c300000000",
        "pub": ("1490aab79a574abfa42e25317b2ab83eb4a5ae2102000000"
                "5e25c0ac40e635ce368abec67bc7aefaaac36eb405000000"),
    },
    {
        "priv": "1e3f0dc7d5aefd4baeab1a1ab85de62dea31901d03000000",
        "pub": ("36f392db19c08af2572372181ff804bcebb8eaa801000000"
                "c8247fdd46f83200120bb7876c88d42dd283efc307000000"),
    },
    {
        "priv": "aa9ae791759ab471387f72a6d4237957213a503703000000",
        "pub": ("0ab6f77b7db7f0b931b28cdeefb54482c0e0736805000000"
                "bebe34bcfad4bda8931c7bd98ffebe497743775b00000000"),
    },
]

# ECDH(VECTORS[0].priv, VECTORS[1].pub) == ECDH(VECTORS[1].priv, VECTORS[0].pub)
SHARED_01 = "8f707bb0d1a481714895cfbc073e1dfeef58520f00000000"


class TestBasePoint(unittest.TestCase):
    def test_base_point_on_curve(self):
        self.assertTrue(k163.is_on_curve((k163.GX, k163.GY)))

    def test_curve_constants(self):
        self.assertEqual(k163.A, 1)
        self.assertEqual(k163.M_BITS, 163)


class TestPublicKeys(unittest.TestCase):
    def test_all_public_keys_on_curve(self):
        for i, v in enumerate(VECTORS):
            P = k163.bytes_to_pubkey(bytes.fromhex(v["pub"]))
            self.assertTrue(k163.is_on_curve(P), "vector %d not on curve" % i)

    def test_private_to_public(self):
        """d * G must equal the recorded public key."""
        for i, v in enumerate(VECTORS):
            words = k163._bytes_to_words(bytes.fromhex(v["priv"]))
            d = k163.words6_to_int(words)
            P = k163.point_mul(d, (k163.GX, k163.GY))
            expected = k163.bytes_to_pubkey(bytes.fromhex(v["pub"]))
            self.assertEqual(P, expected, "vector %d d*G mismatch" % i)

    def test_pubkey_roundtrip(self):
        for v in VECTORS:
            raw = bytes.fromhex(v["pub"])
            P = k163.bytes_to_pubkey(raw)
            self.assertEqual(k163.pubkey_to_bytes(P), raw)


class TestECDH(unittest.TestCase):
    def test_shared_secret_matches_reference(self):
        """ECDH must produce the exact shared secret observed on the wire."""
        priv0 = k163.words6_to_int(k163._bytes_to_words(bytes.fromhex(VECTORS[0]["priv"])))
        priv1 = k163.words6_to_int(k163._bytes_to_words(bytes.fromhex(VECTORS[1]["priv"])))
        pub0 = k163.bytes_to_pubkey(bytes.fromhex(VECTORS[0]["pub"]))
        pub1 = k163.bytes_to_pubkey(bytes.fromhex(VECTORS[1]["pub"]))

        s01 = k163.ecdh(priv0, pub1)
        s10 = k163.ecdh(priv1, pub0)

        self.assertEqual(s01, s10, "ECDH is not symmetric")
        self.assertEqual(s01.hex(), SHARED_01, "shared secret mismatch")

    def test_point_mul_associativity(self):
        """(a*G) * b == (b*G) * a for random scalars."""
        import random
        a = random.randint(2, k163.N - 1)
        b = random.randint(2, k163.N - 1)
        Ga = k163.point_mul(a, (k163.GX, k163.GY))
        Gb = k163.point_mul(b, (k163.GX, k163.GY))
        self.assertEqual(k163.point_mul(b, Ga), k163.point_mul(a, Gb))


if __name__ == "__main__":
    unittest.main(verbosity=2)
