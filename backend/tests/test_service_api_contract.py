from __future__ import annotations

import json
import unittest
from pathlib import Path

from npu_fleet_monitor import SERVICE_API_VERSION

from test_agent_cli_mcp import MCP, FakeClient

ROOT = Path(__file__).resolve().parents[2]


class ServiceApiContractTests(unittest.TestCase):
    def test_service_api_json_matches_advertised_version(self) -> None:
        contract = json.loads((ROOT / "service-api.json").read_text())
        self.assertEqual(contract["schema_version"], 1)
        self.assertEqual(contract["name"], "vaws-top")
        self.assertIn(contract["service_api_version"], contract["supports"])
        self.assertEqual(contract["service_api_version"], SERVICE_API_VERSION)

        for method in ("initialize", "server/discover"):
            advertised = MCP.handle_request(
                {"jsonrpc": "2.0", "id": 1, "method": method, "params": {}},
                FakeClient(),
            )["result"]["capabilities"]["experimental"]["vaws-top"]["service_api_version"]
            self.assertEqual(advertised, SERVICE_API_VERSION)


if __name__ == "__main__":
    unittest.main()
