"""Persist exact screenshot-attributed holders through metadata refreshes."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import observatory
import service_registry
from badges import raw_friendly

class GramServicesTests(unittest.TestCase):
    def test_seven_labels_survive_registry_refresh_and_identity_budget(self):
        services=observatory.KNOWN_SERVICES
        self.assertEqual(len(services),7)
        self.assertEqual(list(services.values()).count("KuCoin"),2)
        snapshot={"holders":{"holders":[{"wallet":a} for a in services]}}
        service_registry.apply(snapshot,service_registry.bundled(),services)
        with patch("observatory.fetch",side_effect=AssertionError("No account request needed")):
            result=observatory.identity(snapshot,observatory.SERVICE_LABEL_CHECKED_AT,budget=0)
        for address,name in services.items():
            self.assertEqual(result["byWallet"][address]["role"],name)
            self.assertEqual(result["byWallet"][address]["roleSource"],
                             observatory.KNOWN_SERVICE_SOURCES[address])
            self.assertEqual(observatory.role(address,{"is_wallet":True}),name)
        configured=json.loads((Path(__file__).resolve().parents[1]/"project.json").read_text())["services"]
        self.assertEqual({raw_friendly(a):n for a,n in configured.items()},services)
