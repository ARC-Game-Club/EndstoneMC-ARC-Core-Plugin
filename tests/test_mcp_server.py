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


class ServerStatusUptimeTests(unittest.TestCase):
    """``get_server_status`` 算运行时长：EndStone 的 start_time 是 datetime。

    2026-11-09 实测事故：老写法 ``time.time() - start_time`` 直接抛
    ``TypeError: unsupported operand type(s) for -: 'float' and 'datetime.datetime'``，
    这个工具**一调就报错**（AstrBot 侧看到的是 tool 返回 error）。
    """

    def setUp(self):
        self.mcp = make_server()

    def test_datetime_start_time_is_accepted(self):
        """start_time 是 datetime → 算出"已经跑了多少秒"。"""
        from datetime import datetime, timedelta

        self.mcp.plugin.server.start_time = datetime.now() - timedelta(seconds=90)
        result = call_tool(self.mcp, "get_server_status")
        self.assertNotIn("error", result, result)
        self.assertIsInstance(result["uptime_seconds"], (int, float))
        self.assertAlmostEqual(result["uptime_seconds"], 90, delta=5)

    def test_timestamp_start_time_still_works(self):
        """start_time 是时间戳（老写法）→ 也要能算，不能回归。"""
        import time as _time

        self.mcp.plugin.server.start_time = _time.time() - 120
        result = call_tool(self.mcp, "get_server_status")
        self.assertNotIn("error", result, result)
        self.assertAlmostEqual(result["uptime_seconds"], 120, delta=5)

    def test_unknown_start_time_yields_none(self):
        """拿不到启动时刻 → None（不报错）。"""
        self.mcp.plugin.server.start_time = 0
        result = call_tool(self.mcp, "get_server_status")
        self.assertNotIn("error", result, result)
        self.assertIsNone(result["uptime_seconds"])


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


class PluginToolRegistryTests(unittest.TestCase):
    """第三方插件工具注册表 + MCP_TOOL_PREFIX 路由。"""

    def setUp(self):
        self.mcp = make_server()
        self.calls = []

    def _ext_spec(self, name="ext_hello"):
        def handler(args):
            self.calls.append((name, args))
            return {"pong": args.get("who", "?")}

        return {
            "name": name,
            "description": "外部测试工具",
            "schema": {"type": "object", "properties": {"who": {"type": "string"}}},
            "handler": handler,
        }

    def test_register_and_call(self):
        result = self.mcp.register_plugin_tools("stub_plugin", [self._ext_spec()])
        self.assertEqual(result["registered"], ["ext_hello"])
        self.assertEqual(result["rejected"], [])
        # tools/list 合并外部工具
        listing = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [t["name"] for t in listing["result"]["tools"]]
        self.assertIn("ext_hello", names)
        self.assertEqual(len(names), 8)  # 7 内建 + 1 外部
        ext_entry = next(t for t in listing["result"]["tools"] if t["name"] == "ext_hello")
        self.assertIn("[stub_plugin]", ext_entry["description"])
        # 调用
        resp = self.mcp.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "ext_hello", "arguments": {"who": "Alice"}}}
        )
        text = resp["result"]["content"][0]["text"]
        self.assertIn("Alice", text)
        self.assertEqual(self.calls, [("ext_hello", {"who": "Alice"})])

    def test_register_validation_and_conflicts(self):
        result = self.mcp.register_plugin_tools(
            "stub_plugin",
            [
                self._ext_spec("ext_ok"),
                {"name": "execute_command", "handler": lambda a: a},  # 撞内建
                {"name": "ext_ok", "handler": lambda a: a},  # 撞同批次
                {"name": "", "handler": lambda a: a},  # 空名
                {"name": "ext_no_handler"},  # 缺 handler
                "not-a-dict",  # 非法条目
            ],
        )
        self.assertEqual(result["registered"], ["ext_ok"])
        rejected_names = [r[0] for r in result["rejected"]]
        self.assertIn("execute_command", rejected_names)
        self.assertIn("ext_no_handler", rejected_names)
        # 5 条被拒：撞内建 / 撞同批次 / 空名 / 缺 handler / 非法条目（"?"）
        self.assertEqual(len(result["rejected"]), 5)

    def test_cross_plugin_conflict_but_own_replace(self):
        self.mcp.register_plugin_tools("plugin_a", [self._ext_spec("shared_name")])
        # 其他插件撞名被拒
        result = self.mcp.register_plugin_tools("plugin_b", [self._ext_spec("shared_name")])
        self.assertEqual(result["registered"], [])
        # 同插件重注册 = 整体替换（幂等）
        result = self.mcp.register_plugin_tools("plugin_a", [self._ext_spec("shared_name"), self._ext_spec("extra")])
        self.assertEqual(sorted(result["registered"]), ["extra", "shared_name"])
        listing = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [t["name"] for t in listing["result"]["tools"]]
        self.assertEqual(names.count("shared_name"), 1)
        self.assertIn("extra", names)

    def test_unregister(self):
        self.mcp.register_plugin_tools("stub_plugin", [self._ext_spec()])
        self.assertTrue(self.mcp.unregister_plugin_tools("stub_plugin"))
        self.assertFalse(self.mcp.unregister_plugin_tools("stub_plugin"))
        listing = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(len(listing["result"]["tools"]), 7)

    def test_unknown_external_tool_error(self):
        resp = self.mcp.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "ghost"}}
        )
        self.assertIn("unknown tool", resp["error"]["message"])

    def test_external_tool_audited(self):
        with tempfile.TemporaryDirectory() as td:
            self.mcp.audit_log_path = str(Path(td) / "audit.jsonl")
            self.mcp.register_plugin_tools("stub_plugin", [self._ext_spec()])
            self.mcp.handle_jsonrpc(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "ext_hello", "arguments": {"who": "Bob"}}}
            )
            lines = [json.loads(x) for x in (Path(td) / "audit.jsonl").read_text("utf-8").splitlines()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["plugin"], "stub_plugin")
        self.assertIn("Bob", lines[0]["args"])

    def test_handler_exception_is_error_result(self):
        def bad_handler(args):
            raise RuntimeError("boom")

        self.mcp.register_plugin_tools(
            "stub_plugin", [{"name": "ext_bad", "description": "", "schema": {}, "handler": bad_handler}]
        )
        resp = self.mcp.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "ext_bad"}}
        )
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("boom", resp["result"]["content"][0]["text"])


class ToolPrefixTests(unittest.TestCase):
    """MCP_TOOL_PREFIX：tools/list 加前缀、tools/call 剥前缀（裸名兼容）。"""

    def setUp(self):
        self.mcp = make_server(tool_prefix="zombie_")
        self.mcp.register_plugin_tools(
            "stub_plugin",
            [{"name": "ext_x", "description": "", "schema": {}, "handler": lambda a: {"ok": True}}],
        )

    def _list_names(self):
        listing = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        return [t["name"] for t in listing["result"]["tools"]]

    def test_list_prefixed(self):
        names = self._list_names()
        self.assertIn("zombie_execute_command", names)
        self.assertIn("zombie_ext_x", names)
        self.assertNotIn("execute_command", names)

    def test_call_prefixed(self):
        resp = self.mcp.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "zombie_ext_x"}}
        )
        self.assertIn("ok", resp["result"]["content"][0]["text"])

    def test_call_bare_name_still_works(self):
        resp = self.mcp.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "ext_x"}}
        )
        self.assertIn("ok", resp["result"]["content"][0]["text"])

    def test_call_prefixed_builtin(self):
        resp = self.mcp.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "zombie_get_server_status"}}
        )
        self.assertIn("minecraft_version", resp["result"]["content"][0]["text"])


class TranslatableTextTests(unittest.TestCase):
    """_to_text：str 直通、Translatable 走服务器语言翻译、无 language 时退回原文。"""

    class StubTranslatable:
        def __init__(self, text, params=None):
            self.text = text
            self.params = params or []

    class StubLanguage:
        def translate(self, value, locale=None):
            return f"translated:{value.text}"

    def test_str_passthrough(self):
        self.assertEqual(mcp_server_mod._to_text("hello"), "hello")

    def test_translatable_with_language(self):
        value = self.StubTranslatable("commands.list.players")
        self.assertEqual(
            mcp_server_mod._to_text(value, self.StubLanguage()),
            "translated:commands.list.players",
        )

    def test_translatable_without_language(self):
        value = self.StubTranslatable("commands.x", ["Alice", "Bob"])
        self.assertEqual(mcp_server_mod._to_text(value), "commands.x ['Alice', 'Bob']")
        self.assertEqual(mcp_server_mod._to_text(self.StubTranslatable("plain")), "plain")

    def test_translatable_translate_failure_falls_back(self):
        class BadLanguage:
            def translate(self, value, locale=None):
                raise RuntimeError("boom")

        value = self.StubTranslatable("key.x")
        self.assertEqual(mcp_server_mod._to_text(value, BadLanguage()), "key.x")

    def test_unknown_object_repr(self):
        self.assertEqual(mcp_server_mod._to_text(object()), str(object()))


class LimitedTokenTests(unittest.TestCase):
    """受限通道：limited token 鉴权、tools/list 隐藏 owner_only、tools/call 拒绝。"""

    def setUp(self):
        self.mcp = make_server(token="owner-secret", limited_token="limited-secret")

    def test_execute_command_marked_owner_only(self):
        self.assertTrue(self.mcp._tools["execute_command"]["owner_only"])
        for name, spec in self.mcp._tools.items():
            if name != "execute_command":
                self.assertFalse(spec["owner_only"], name)

    def test_limited_tools_list_hides_execute_command(self):
        resp = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, role="limited")
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertNotIn("execute_command", names)
        self.assertIn("get_server_status", names)
        self.assertEqual(len(names), 6)

    def test_owner_tools_list_full(self):
        resp = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, role="owner")
        self.assertEqual(len(resp["result"]["tools"]), 7)

    def test_limited_call_owner_only_rejected(self):
        resp = self.mcp.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "execute_command", "arguments": {"command": "list"}}},
            role="limited",
        )
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("服主通道", resp["result"]["content"][0]["text"])
        self.assertEqual(self.mcp.plugin.server.dispatched, [])

    def test_limited_call_readonly_ok(self):
        resp = self.mcp.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_server_status"}},
            role="limited",
        )
        self.assertIn("minecraft_version", resp["result"]["content"][0]["text"])

    def test_default_role_is_owner(self):
        """不传 role（旧调用方）= owner，行为不变。"""
        resp = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(len(resp["result"]["tools"]), 7)

    def test_external_tool_visible_on_limited_by_default(self):
        self.mcp.register_plugin_tools(
            "stub_plugin",
            [{"name": "ext_tool", "description": "", "schema": {}, "handler": lambda a: {"ok": True}}],
        )
        resp = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, role="limited")
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertIn("ext_tool", names)

    def test_external_tool_owner_only_hidden(self):
        self.mcp.register_plugin_tools(
            "stub_plugin",
            [{"name": "ext_owner_tool", "description": "", "schema": {}, "handler": lambda a: {}, "owner_only": True}],
        )
        resp = self.mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, role="limited")
        names = [t["name"] for t in resp["result"]["tools"]]
        self.assertNotIn("ext_owner_tool", names)


class DualTokenHttpTests(unittest.TestCase):
    """HTTP 层双 token：owner/limited/无效 → 三种角色。"""

    @classmethod
    def setUpClass(cls):
        cls.mcp = make_server(token="owner-secret", limited_token="limited-secret")
        assert cls.mcp.start()
        cls.port = cls.mcp._httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.mcp.stop()

    def _post(self, body, auth):
        url = f"http://127.0.0.1:{self.port}/mcp"
        headers = {"Content-Type": "application/json"}
        if auth is not None:
            headers["Authorization"] = f"Bearer {auth}"
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")

    def test_owner_token_full_tools(self):
        status, body = self._post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, "owner-secret")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["result"]["tools"]), 7)

    def test_limited_token_filtered_tools(self):
        status, body = self._post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, "limited-secret")
        self.assertEqual(status, 200)
        names = [t["name"] for t in body["result"]["tools"]]
        self.assertNotIn("execute_command", names)

    def test_invalid_token_401(self):
        status, _ = self._post({"jsonrpc": "2.0", "id": 1, "method": "ping"}, "nope")
        self.assertEqual(status, 401)

    def test_missing_token_401(self):
        status, _ = self._post({"jsonrpc": "2.0", "id": 1, "method": "ping"}, None)
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
