# -*- coding: utf-8 -*-
"""MCP 服务器：JSON-RPC 分发、鉴权、命令拦截与各工具（桩插件，零 endstone 依赖）。"""
import importlib.util
import json
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

_MOD_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "endstone_arc_core"
    / "mcp_server.py"
)
_spec = importlib.util.spec_from_file_location("mcp_server", _MOD_PATH)
assert _spec and _spec.loader
mcp_server_mod = importlib.util.module_from_spec(_spec)
sys.modules["mcp_server"] = mcp_server_mod
_spec.loader.exec_module(mcp_server_mod)

MCPServer = mcp_server_mod.MCPServer


# ---------------------------------------------------------------------------
# 桩插件：鸭子类型满足 MCPServer 用到的全部插件接口
# ---------------------------------------------------------------------------

class StubScheduler:
    def run_task(self, plugin, task, delay=0, period=0):
        task()  # 同步模拟主线程


class StubLocation:
    def __init__(self, x, y, z, dimension_name):
        self.x, self.y, self.z = x, y, z
        self.dimension = type("D", (), {"name": dimension_name})()


class StubPlayer:
    def __init__(self, name, xuid, dimension_name="overworld"):
        self.name = name
        self.xuid = xuid
        self.ping = 42
        self.location = StubLocation(1.5, 64.0, -3.5, dimension_name)
        self.game_mode = "survival"
        self.device_os = "Windows"
        self.is_op = False


class StubCommandSender:
    name = "Console"


class StubBlock:
    type = "minecraft:chest"


class StubDimension:
    def __init__(self, name):
        self.name = name

    def get_block_at(self, x, y, z):
        return StubBlock()


class StubLevel:
    def __init__(self):
        self._dims = {"overworld": StubDimension("overworld"), "nether": StubDimension("nether")}

    def get_dimension(self, name):
        return self._dims.get(name)


class StubPluginManager:
    class _P:
        def __init__(self, name, version):
            self.name, self.version = name, version

    plugins = [_P("arc_core", "0.9.89"), _P("other", "1.0")]


class StubServer:
    def __init__(self, players):
        self.scheduler = StubScheduler()
        self.online_players = players
        self.command_sender = StubCommandSender()
        self.level = StubLevel()
        self.plugin_manager = StubPluginManager()
        self.name = "Stub Server"
        self.version = "0.11.14"
        self.minecraft_version = "1.26.52"
        self.max_players = 30
        self.current_tps = 19.96
        self.average_tps = 19.8
        self.current_mspt = 21.5
        self.average_mspt = 22.1
        self.start_time = 0
        self.dispatched = []

    def get_player(self, name):
        for p in self.online_players:
            if p.name.lower() == str(name).lower():
                return p
        return None

    def dispatch_command(self, sender, command):
        self.dispatched.append(command)
        return True


class StubEconomy:
    def get_player_money_by_xuid(self, xuid):
        return {"2535410000000001": 1234.5}.get(xuid, 0.0)

    def get_player_money_rank_by_xuid(self, xuid):
        return {"2535410000000001": 1}.get(xuid)

    def get_fixed_deposits_total_by_xuid(self, xuid):
        return 500.0

    def count_matured_fixed_deposits_by_xuid(self, xuid):
        return 1

    def get_top_richest_xuids(self, count):
        return [
            {"xuid": "2535410000000001", "money": 1234.5},
            {"xuid": "2535410000000002", "money": 100.0},
        ][:count]


class StubLandSystem:
    def get_player_land_count(self, xuid):
        return 1

    def get_player_lands_total_value(self, xuid):
        return 3000.0

    def get_player_lands(self, xuid):
        return {7: {"land_name": "老家", "dimension": "overworld", "owner_paid_money": 3000}}


class StubSkyEyeStore:
    def query(self, **kwargs):
        return [{"action": "OpenContainer", "player_name": "Alice", "ts": "2026-11-03 10:00:00"}]


class StubDB:
    def query_all(self, sql, params=()):
        if "player_basic_info" in sql:
            return [
                {"xuid": "2535410000000001", "name": "Alice"},
                {"xuid": "2535410000000002", "name": "Bob"},
            ]
        return []


class StubPlugin:
    def __init__(self):
        self.server = StubServer([StubPlayer("Alice", "2535410000000001")])
        self.economy = StubEconomy()
        self.land_system = StubLandSystem()
        self.sky_eye_store = StubSkyEyeStore()
        self.database_manager = StubDB()

    def get_player_xuid_by_name(self, name):
        return {"alice": "2535410000000001"}.get(str(name).lower())


def make_server(**kwargs):
    defaults = {
        "plugin": StubPlugin(),
        "bind_port": 0,  # 临时端口，仅 handle_jsonrpc 直调不需要真实端口
        "token": "test-token",
    }
    defaults.update(kwargs)
    return MCPServer(**defaults)


def call_tool(mcp, name, arguments=None):
    resp = mcp.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}}
    )
    assert resp is not None and "result" in resp, resp
    payload = resp["result"]
    assert payload.get("content"), payload
    text = payload["content"][0]["text"]
    return json.loads(text) if not payload.get("isError") else {"__isError__": text}


class JsonRpcTests(unittest.TestCase):
    def setUp(self):
        self.mcp = make_server()

    def test_initialize_echoes_known_version(self):
        resp = self.mcp.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}
        )
        self.assertEqual(resp["result"]["protocolVersion"], "2025-03-26")
        self.assertIn("tools", resp["result"]["capabilities"])
        self.assertEqual(resp["result"]["serverInfo"]["name"], "arccore-mcp")

    def test_initialize_unknown_version_falls_back(self):
        resp = self.mcp.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}
        )
        self.assertEqual(resp["result"]["protocolVersion"], mcp_server_mod.MCP_DEFAULT_PROTOCOL_VERSION)

    def test_ping(self):
        resp = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 3, "method": "ping"})
        self.assertEqual(resp["result"], {})

    def test_tools_list_has_seven_tools(self):
        resp = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertEqual(
            sorted(names),
            sorted(
                [
                    "execute_command",
                    "get_server_status",
                    "get_online_players",
                    "get_player_info",
                    "get_block_info",
                    "economy_top",
                    "query_sky_eye",
                ]
            ),
        )
        for tool in resp["result"]["tools"]:
            self.assertIn("inputSchema", tool)

    def test_unknown_method(self):
        resp = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 5, "method": "resources/list"})
        self.assertEqual(resp["error"]["code"], -32601)

    def test_notification_returns_none(self):
        self.assertIsNone(
            self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )

    def test_unknown_tool(self):
        resp = self.mcp.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "nope"}}
        )
        self.assertEqual(resp["error"]["code"], -32602)

    def test_non_object_request(self):
        resp = self.mcp.handle_jsonrpc("hello")
        self.assertEqual(resp["error"]["code"], -32600)


class ExecuteCommandTests(unittest.TestCase):
    def setUp(self):
        self.mcp = make_server()
        self.plugin = self.mcp.plugin

    def test_normal_command_dispatches(self):
        result = call_tool(self.mcp, "execute_command", {"command": "list"})
        self.assertTrue(result["success"])
        self.assertEqual(self.plugin.server.dispatched, ["list"])

    def test_leading_slash_tolerated(self):
        result = call_tool(self.mcp, "execute_command", {"command": "/list"})
        self.assertTrue(result["success"])
        self.assertEqual(self.plugin.server.dispatched, ["/list"])

    def test_stop_blocked(self):
        result = call_tool(self.mcp, "execute_command", {"command": "stop"})
        self.assertFalse(result["success"])
        self.assertTrue(result["blocked"])
        self.assertEqual(self.plugin.server.dispatched, [])

    def test_reload_and_restart_blocked(self):
        for cmd in ("reload", "RESTART", "/stop"):
            result = call_tool(self.mcp, "execute_command", {"command": cmd})
            self.assertTrue(result["blocked"], cmd)
        self.assertEqual(self.plugin.server.dispatched, [])

    def test_empty_command(self):
        result = call_tool(self.mcp, "execute_command", {"command": "  "})
        self.assertFalse(result["success"])

    def test_audit_written(self):
        with tempfile.TemporaryDirectory() as td:
            self.mcp.audit_log_path = str(Path(td) / "audit.jsonl")
            call_tool(self.mcp, "execute_command", {"command": "list"})
            call_tool(self.mcp, "execute_command", {"command": "stop"})
            lines = [json.loads(x) for x in (Path(td) / "audit.jsonl").read_text("utf-8").splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[1]["blocked"], True)


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.mcp = make_server()

    def test_server_status(self):
        status = call_tool(self.mcp, "get_server_status")
        self.assertEqual(status["minecraft_version"], "1.26.52")
        self.assertEqual(status["online_count"], 1)
        self.assertEqual(status["tps"]["current"], 20.0)
        self.assertIn("arc_core@0.9.89", status["plugins"])

    def test_online_players(self):
        data = call_tool(self.mcp, "get_online_players")
        self.assertEqual(data["count"], 1)
        player = data["players"][0]
        self.assertEqual(player["name"], "Alice")
        self.assertEqual(player["dimension"], "overworld")
        self.assertEqual(player["position"]["x"], 1.5)

    def test_player_info(self):
        info = call_tool(self.mcp, "get_player_info", {"player_name": "alice"})
        self.assertTrue(info["found"])
        self.assertTrue(info["online"])
        self.assertEqual(info["economy"]["balance"], 1234.5)
        self.assertEqual(info["economy"]["rank"], 1)
        self.assertEqual(info["lands"]["count"], 1)
        self.assertEqual(info["lands"]["items"][0]["land_id"], 7)
        self.assertEqual(info["position"]["dimension"], "overworld")

    def test_player_info_not_found(self):
        info = call_tool(self.mcp, "get_player_info", {"player_name": "nobody"})
        self.assertFalse(info["found"])

    def test_block_info(self):
        block = call_tool(self.mcp, "get_block_info", {"dimension": "nether", "x": 1, "y": 2, "z": 3})
        self.assertEqual(block["type"], "minecraft:chest")
        self.assertEqual(block["dimension"], "nether")

    def test_block_info_minecraft_prefix(self):
        block = call_tool(self.mcp, "get_block_info", {"dimension": "minecraft:nether", "x": 0, "y": 0, "z": 0})
        self.assertEqual(block["type"], "minecraft:chest")

    def test_block_info_bad_dimension(self):
        block = call_tool(self.mcp, "get_block_info", {"dimension": "moon", "x": 0, "y": 0, "z": 0})
        self.assertIn("error", block)

    def test_economy_top(self):
        top = call_tool(self.mcp, "economy_top", {"count": 2})
        self.assertEqual(top["count"], 2)
        self.assertEqual(top["ranking"][0]["name"], "Alice")
        self.assertEqual(top["ranking"][0]["rank"], 1)

    def test_sky_eye(self):
        data = call_tool(self.mcp, "query_sky_eye", {"player_name": "Alice", "minutes": 60})
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["records"][0]["action"], "OpenContainer")


class HttpTransportTests(unittest.TestCase):
    """起真实 HTTP 服务（临时端口），验证鉴权与状态码。"""

    @classmethod
    def setUpClass(cls):
        cls.mcp = make_server(token="secret-token")
        assert cls.mcp.start()
        cls.port = cls.mcp._httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.mcp.stop()

    def _post(self, body, headers=None):
        url = f"http://127.0.0.1:{self.port}/mcp"
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")

    def test_no_token_401(self):
        status, body = self._post({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        self.assertEqual(status, 401)

    def test_wrong_token_401(self):
        status, _ = self._post({"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"Authorization": "Bearer wrong"})
        self.assertEqual(status, 401)

    def test_bearer_token_ok(self):
        status, body = self._post(
            {"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"Authorization": "Bearer secret-token"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["result"], {})

    def test_query_token_ok(self):
        status, body = self._post(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        # 没带 token 的走 query 参数版本单独发
        url = f"http://127.0.0.1:{self.port}/mcp?token=secret-token"
        req = urllib.request.Request(url, data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}).encode("utf-8"), method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
        self.assertEqual(status, 401)  # 前一个无 token 应 401

    def test_wrong_path_404(self):
        url = f"http://127.0.0.1:{self.port}/other"
        req = urllib.request.Request(url, data=b"{}", method="POST", headers={"Authorization": "Bearer secret-token"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
        self.assertEqual(status, 404)

    def test_get_405(self):
        url = f"http://127.0.0.1:{self.port}/mcp?token=secret-token"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
        self.assertEqual(status, 405)


class LifecycleTests(unittest.TestCase):
    def test_start_stop(self):
        mcp = make_server()
        self.assertTrue(mcp.start())
        self.assertTrue(mcp.is_running())
        port = mcp._httpd.server_address[1]
        mcp.stop()
        self.assertFalse(mcp.is_running())
        # 停止后同端口立即可重绑（server_close 已释放监听 socket）
        mcp2 = MCPServer(mcp.plugin, bind_port=port if port else 0, token="x")
        self.assertTrue(mcp2.start())
        mcp2.stop()

    def test_bind_conflict_returns_false(self):
        first = make_server(token="x")
        self.assertTrue(first.start())
        port = first._httpd.server_address[1]
        try:
            second = MCPServer(first.plugin, bind_port=port, token="y")
            self.assertFalse(second.start())
        finally:
            first.stop()

    def test_generate_token_shape(self):
        token = mcp_server_mod.generate_mcp_token()
        self.assertEqual(len(token), 32)
        int(token, 16)  # 十六进制


if __name__ == "__main__":
    unittest.main()
