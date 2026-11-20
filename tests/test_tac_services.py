"""Do not claim a large TAC holder is a service without chain-derived evidence."""
import unittest
import observatory


class ServiceTypeTests(unittest.TestCase):
    def test_known_contract_interfaces(self):
        wallet = "0:" + "ab"*32
        account = {"status": "active", "is_wallet": False,
                   "interfaces": ["stonfi_pool_v2"]}
        self.assertEqual(observatory.role(wallet, account), "STON.fi Pool V2")

    def test_unknown_contract_not_misidentified_as_named_service(self):
        wallet = "0:" + "cd"*32
        self.assertEqual(
            observatory.role(wallet, {"status": "active", "is_wallet": False,
                                      "interfaces": []}),
            "unclassified_contract")

    def test_unknown_wallet_is_not_a_proven_service(self):
        wallet = "0:" + "ef"*32
        self.assertIsNone(
            observatory.role(wallet, {"status": "active", "is_wallet": True,
                                      "interfaces": []}))


if __name__ == "__main__":
    unittest.main()
