"""End-to-end HTTP contract and safety tests against the local NiFi API simulator."""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import unittest

import requests
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from nifi_mcp_server.client import NiFiClient, NiFiError
from nifi_api_simulator import create_simulator


class NiFiSimulatorContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.state = create_simulator()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}/nifi-api"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        with self.state.lock:
            self.state.requests.clear()
            self.state.failures.clear()
        self.state.delay_after_post_seconds = 0.0
        self.session = requests.Session()
        self.client = NiFiClient(self.base_url, self.session, timeout_seconds=2)

    def tearDown(self):
        self.session.close()

    def test_real_http_version_root_group_processors_and_health_contract(self):
        self.assertEqual(self.client.get_version_tuple(), (2, 6, 0))
        root = self.client.get_root_process_group()
        self.assertEqual(root["processGroupFlow"]["id"], "root")
        processors = self.client.list_processors("root")
        self.assertEqual(processors["processors"][0]["component"]["name"], "GenerateFlowFile")
        self.assertEqual(self.client.list_connections("root")["connections"], [])
        self.assertEqual(self.client.get_controller_services()["controllerServices"], [])
        self.assertIn("bulletinBoard", self.client.get_bulletins())

    def test_wrong_or_missing_bearer_token_is_denied(self):
        server, state = create_simulator(token="simulator-only-token")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = NiFiClient(f"http://127.0.0.1:{server.server_port}/nifi-api", requests.Session(), timeout_seconds=1)
            with self.assertRaises(NiFiError) as caught:
                client.get_version_info()
            self.assertEqual(caught.exception.status_code, 401)
            self.assertEqual(state.count("GET", "/nifi-api/flow/about"), 1)
            client.session.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_transient_read_5xx_is_retried_and_recovers(self):
        path = "/nifi-api/flow/about"
        self.state.failures[path] = [(503, {"message": "simulated transient failure"})]
        info = self.client.get_version_info()
        self.assertEqual(info["about"]["version"], "2.6.0")
        self.assertEqual(self.state.count("GET", path), 2)

    def test_non_retryable_4xx_is_not_retried(self):
        path = "/nifi-api/flow/about"
        self.state.failures[path] = [(400, {"message": "simulated bad request"})]
        with self.assertRaises(NiFiError) as caught:
            self.client.get_version_info()
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(self.state.count("GET", path), 1)

    def test_post_timeout_after_simulated_apply_is_not_retried(self):
        path = "/nifi-api/process-groups/root/process-groups"
        self.state.delay_after_post_seconds = 0.3
        self.client.timeout = 0.05
        try:
            with self.assertRaises(requests.Timeout):
                self.client._post("process-groups/root/process-groups", {"component": {"name": "test-only"}})
            self.assertEqual(self.state.count("POST", path), 1)
        finally:
            self.state.delay_after_post_seconds = 0.0

    def test_mcp_stdio_harness_calls_read_tools_against_simulator(self):
        async def exercise_mcp():
            env = dict(os.environ)
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [os.path.abspath("src"), env.get("PYTHONPATH", "")]))
            env["NIFI_API_BASE"] = self.base_url
            env["NIFI_READONLY"] = "true"
            env["MCP_TRANSPORT"] = "stdio"
            for key in (
                "KNOX_GATEWAY_URL", "KNOX_TOKEN", "KNOX_COOKIE", "KNOX_USER",
                "KNOX_PASSWORD", "KNOX_TOKEN_ENDPOINT", "KNOX_PASSCODE_TOKEN",
                "NIFI_USERNAME", "NIFI_PASSWORD", "NIFI_CLIENT_CERT", "NIFI_CLIENT_KEY",
                "KNOX_CA_BUNDLE", "NIFI_PROXY_CONTEXT_PATH",
            ):
                env.pop(key, None)
            params = StdioServerParameters(command=sys.executable, args=["-m", "nifi_mcp_server.server"], env=env)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    self.assertIn("get_nifi_version", names)
                    self.assertIn("get_root_process_group", names)
                    self.assertIn("list_processors", names)
                    self.assertNotIn("start_processor", names)
                    version = await session.call_tool("get_nifi_version", {})
                    root = await session.call_tool("get_root_process_group", {})
                    processors = await session.call_tool("list_processors", {"process_group_id": "root"})
                    health = await session.call_tool("get_flow_health_status", {"pg_id": "root"})
                    for result in (version, root, processors, health):
                        self.assertFalse(result.isError, str(result.content))
                    self.assertIn("2.6.0", str(version.content))
                    self.assertIn("GenerateFlowFile", str(processors.content))

        asyncio.run(exercise_mcp())
        with self.state.lock:
            mutations = [r for r in self.state.requests if r["method"] in {"POST", "PUT", "DELETE"}]
        self.assertEqual(mutations, [])

    def test_read_only_contract_suite_performs_no_mutations(self):
        self.client.get_version_info()
        self.client.get_root_process_group()
        self.client.list_processors("root")
        self.client.list_connections("root")
        self.client.get_controller_services()
        self.client.get_bulletins()
        with self.state.lock:
            mutations = [r for r in self.state.requests if r["method"] in {"POST", "PUT", "DELETE"}]
        self.assertEqual(mutations, [])


if __name__ == "__main__":
    unittest.main()
