"""Load language-agnostic test vectors and verify the implementation.

This test reads testvectors/sect163r2.json, the same file any other
language/port can use to verify its own sect163r2 implementation.
"""
import json
import os
import unittest

from miband6.crypto import k163

_HERE = os.path.dirname(os.path.abspath(__file__))
_VEC_PATH = os.path.join(os.path.dirname(_HERE), "testvectors", "sect163r2.json")


def _load():
    with open(_VEC_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestVectors(unittest.TestCase):
    def setUp(self):
        self.vec = _load()

    def test_curve_metadata_and_legacy_path(self):
        self.assertEqual(self.vec["curve"], "sect163r2 (NIST B-163)")
        legacy_path = os.path.join(os.path.dirname(_HERE), "testvectors", "sect163k1.json")
        with open(legacy_path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), self.vec)

    def test_params(self):
        p = self.vec["params"]
        self.assertEqual(int(p["a"], 16), k163.A)
        self.assertEqual(int(p["b"], 16), k163.B)
        self.assertEqual(int(p["gx"], 16), k163.GX)
        self.assertEqual(int(p["gy"], 16), k163.GY)
        self.assertEqual(int(p["n"], 16), k163.N)

    def test_keypairs(self):
        for i, kp in enumerate(self.vec["keypairs"]):
            d = k163.words6_to_int(k163._bytes_to_words(bytes.fromhex(kp["private"])))
            P = k163.bytes_to_pubkey(bytes.fromhex(kp["public"]))
            self.assertTrue(k163.is_on_curve(P), "keypair %d off-curve" % i)
            self.assertEqual(k163.point_mul(d, (k163.GX, k163.GY)), P,
                             "keypair %d d*G != pub" % i)

    def test_ecdh(self):
        for e in self.vec["ecdh"]:
            d = k163.words6_to_int(k163._bytes_to_words(bytes.fromhex(e["alice_private"])))
            pub = k163.bytes_to_pubkey(bytes.fromhex(e["bob_public"]))
            shared = k163.ecdh(d, pub)
            self.assertEqual(shared.hex(), e["shared_secret"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
