# -*- coding: utf-8 -*-
"""ArcCore 内嵌 MCP 服务器（Model Context Protocol）。

让本地 AI 客户端（ZCode 等）通过 HTTP JSON-RPC 直接操控本服：
执行命令（带回显）、查服务器状态 / 在线玩家 / 玩家档案（经济/领地）、
方块信息、财富榜、天眼日志。

生命周期蓝图照抄 sync_server.py：daemon 线程 + start() -> bool / stop()，
logger 延迟注入（__init__ 阶段插件 self.logger 不可用，0.9.77 教训）。

传输：MCP Streamable HTTP 子集 —— 单端点 POST /mcp，JSON-RPC 2.0 单 JSON
响应（无 SSE 流，GET/DELETE 返回 405），无会话状态（stateless）。

安全：
- 仅绑定 127.0.0.1；
- Bearer token 鉴权（MCP_TOKEN，为空则拒绝一切请求）；
- stop/reload/restart 等命令硬拦——重启权归服主，MCP 层代码化该约定；
- 每条命令追加审计 mcp_audit.jsonl。

线程模型：
- 本模块自己的 daemon 线程跑 ThreadingHTTPServer；
- 命令执行 / 服务器对象 / 玩家对象访问一律经 server.scheduler.run_task
  投递主线程并等待结果（与位置检测线程、同步客户端的做法一致）；
- 经济 / 领地 / 天眼查询在 MCP 线程直接调用（数据库 threading.local 连接，
  天眼自带锁，均线程安全）。
"""
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple

MCP_SERVER_NAME = "arccore-mcp"
MCP_SERVER_VERSION = "0.1.0"

# 支持的 MCP 协议版本（客户端请求哪个已知版本就回哪个，否则回默认）
MCP_KNOWN_PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18"}
MCP_DEFAULT_PROTOCOL_VERSION = "2025-06-18"

DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_MCP_PORT = 19990

# 硬拦命令：按首个 token 精确匹配（大小写不敏感）。
# 重启/重载必须由服主亲自操作（工作区 AGENTS.md 约定），MCP 层强制执行。
BLOCKED_COMMAND_TOKENS = {"stop", "reload", "restart"}

# 主线程任务最长等待秒数（防调度器卡死拖死 MCP 线程）
MAIN_THREAD_TIMEOUT = 15.0

JSON_RPC_PARSE_ERROR = -32700
JSON_RPC_INVALID_REQUEST = -32600
JSON_RPC_METHOD_NOT_FOUND = -32601
JSON_RPC_INVALID_PARAMS = -32602
JSON_RPC_INTERNAL_ERROR = -32603


def _safe(fn: Callable[[], Any], default: Any = None) -> Any:
    """吞异常取值：单个字段失败不应让整个工具报错。"""
    try:
        return fn()
    except Exception:
        return default


def _to_text(value: Any, language: Any = None) -> str:
    """CommandSenderWrapper 回调参数可能是 str 或 Translatable，统一转字符串。

    Translatable 优先用服务器语言（language.translate）翻成具体文本；
    不可用时退回 .text + params 原文。"""
    if isinstance(value, str):
        return value
    text = _safe(lambda: value.text)
    if text is not None:  # Translatable 形状
        if language is not None:
            translated = _safe(lambda: language.translate(value))
            if isinstance(translated, str) and translated:
                return translated
        params = _safe(lambda: list(value.params)) or []
        if params:
            return f"{text} {list(params)}"
        return str(text)
    return str(value)


class MCPServer:
    """插件内嵌 MCP 服务器。构造时只存引用（logger 可能未就绪），start()/stop() 管线程。"""

    def __init__(
        self,
        plugin: Any,
        *,
        bind_port: int = DEFAULT_MCP_PORT,
        token: str = "",
        logger: Any = None,
        audit_log_path: str = "",
        bind_host: str = DEFAULT_BIND_HOST,
        tool_prefix: str = "",
    ) -> None:
        # plugin：ARCCorePlugin 实例（鸭子类型，测试时用桩替代）。
        # 依赖它的 server/economy/land_system/sky_eye_store/database_manager/
        # get_player_xuid_by_name，全部在工具调用时按需读取。
        self.plugin = plugin
        self.bind_host = bind_host
        self.bind_port = int(bind_port)
        self.token = str(token or "")
        self.logger = logger
        self.audit_log_path = str(audit_log_path or "")
        # 对外暴露的工具名前缀（MCP_TOOL_PREFIX 设置）：多服同接一个客户端时防撞名。
        # tools/list 输出名加前缀，tools/call 先剥前缀再查表（裸名也接受）。
        self.tool_prefix = str(tool_prefix or "").strip()
        # 第三方插件注册的工具：plugin_name -> [spec]；spec = {name, description, schema, handler, plugin}
        self._plugin_tools: Dict[str, List[Dict[str, Any]]] = {}
        self._plugin_tools_lock = threading.Lock()

        self._httpd: Optional[ThreadingHTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._running = False
        self._audit_lock = threading.Lock()

        # 工具注册表：名称 -> (描述, inputSchema, 处理函数)
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._register_tools()

    # ------------------------------------------------------------------
    # 日志 / 审计
    # ------------------------------------------------------------------

    def _log(self, level: str, message: str) -> None:
        """logger 未注入时回退 print（与 SyncServer._log 一致）。"""
        logger = getattr(self, "logger", None)
        try:
            if logger is not None:
                getattr(logger, level)(f"[ARC Core][MCP] {message}")
                return
        except Exception:
            pass
        print(f"[ARC Core][MCP] [{level}] {message}")

    def _audit(self, record: Dict[str, Any]) -> None:
        """追加一条审计记录到 mcp_audit.jsonl（失败不影响主流程）。"""
        if not self.audit_log_path:
            return
        record.setdefault("ts", time.strftime("%Y-%m-%d %H:%M:%S"))
        line = json.dumps(record, ensure_ascii=False, default=str)
        try:
            with self._audit_lock:
                with open(self.audit_log_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as e:
            self._log("warning", f"audit write failed: {e}")

    # ------------------------------------------------------------------
    # 生命周期（照抄 SyncServer 蓝图）
    # ------------------------------------------------------------------

    def start(self) -> bool:
        if self._running:
            return True
        try:
            # 不能用 functools.partial 传关键字：BaseRequestHandler.__init__ 不收
            # 额外参数。标准做法——为本次实例生成子类并挂上引用。
            handler_cls = type("BoundMCPRequestHandler", (_MCPRequestHandler,), {"mcp_server": self})
            self._httpd = _MCPHTTPServer((self.bind_host, self.bind_port), handler_cls)
        except Exception as e:
            self._log("error", f"failed to bind {self.bind_host}:{self.bind_port}: {e}")
            self._httpd = None
            return False
        self._running = True
        self._server_thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="arc-core-mcp-http",
            daemon=True,
        )
        self._server_thread.start()
        actual_port = self._httpd.server_address[1]
        self._log(
            "info",
            f"MCP server listening on http://{self.bind_host}:{actual_port}/mcp "
            f"(token {'set' if self.token else 'MISSING - all requests will be rejected'})",
        )
        return True

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass
        thread, self._server_thread = self._server_thread, None
        if thread is not None:
            thread.join(timeout=5)
        self._log("info", "MCP server stopped.")

    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # 主线程投递
    # ------------------------------------------------------------------

    def _run_on_main(self, fn: Callable[[], Any], timeout: float = MAIN_THREAD_TIMEOUT) -> Tuple[bool, Any, Optional[Exception]]:
        """把 fn 投到服务器主线程执行并等待结果。

        返回 (ok, result, error)。scheduler.run_task 从后台线程调用是既有
        做法（位置检测线程 / 同步客户端均如此）。
        """
        box: Dict[str, Any] = {}
        done = threading.Event()

        def _wrapper() -> None:
            try:
                box["result"] = fn()
            except Exception as e:  # noqa: BLE001 - 原样回传给调用方
                box["error"] = e
            finally:
                done.set()

        try:
            scheduler = self.plugin.server.scheduler
            scheduler.run_task(self.plugin, _wrapper, delay=0)
        except Exception as e:  # noqa: BLE001
            return False, None, e
        if not done.wait(timeout):
            return False, None, TimeoutError(f"main-thread task not done within {timeout:.0f}s")
        if "error" in box:
            return False, None, box["error"]
        return True, box.get("result"), None

    # ------------------------------------------------------------------
    # JSON-RPC / MCP 分发（与 HTTP 层解耦，测试可直接调）
    # ------------------------------------------------------------------

    def handle_jsonrpc(self, payload: Any) -> Optional[Dict[str, Any]]:
        """处理单条 JSON-RPC 请求。通知（无 id）返回 None，否则返回响应对象。"""
        if not isinstance(payload, dict):
            return self._error_response(None, JSON_RPC_INVALID_REQUEST, "request must be a JSON object")
        request_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params") or {}
        is_notification = "id" not in payload

        if not isinstance(method, str) or not method:
            if is_notification:
                return None
            return self._error_response(request_id, JSON_RPC_INVALID_REQUEST, "missing method")

        try:
            if method == "initialize":
                return self._handle_initialize(request_id, params)
            if method == "ping":
                return self._result_response(request_id, {})
            if method == "tools/list":
                prefix = self.tool_prefix
                tools = [
                    {"name": f"{prefix}{spec['name']}", "description": spec["description"], "inputSchema": spec["schema"]}
                    for spec in self._tools.values()
                ]
                tools.extend(
                    {
                        "name": f"{prefix}{spec['name']}",
                        "description": f"[{spec['plugin']}] {spec['description']}",
                        "inputSchema": spec["schema"],
                    }
                    for spec in self._iter_external_tools()
                )
                return self._result_response(request_id, {"tools": tools})
            if method == "tools/call":
                return self._handle_tools_call(request_id, params)
            # notifications/initialized 等一切未知方法：通知静默，请求报错
            if is_notification:
                return None
            return self._error_response(request_id, JSON_RPC_METHOD_NOT_FOUND, f"method not found: {method}")
        except Exception as e:  # noqa: BLE001
            if is_notification:
                return None
            return self._error_response(request_id, JSON_RPC_INTERNAL_ERROR, f"internal error: {e}")

    def _handle_initialize(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        requested = str(_safe(lambda: params["protocolVersion"], "") or "")
        version = requested if requested in MCP_KNOWN_PROTOCOL_VERSIONS else MCP_DEFAULT_PROTOCOL_VERSION
        return self._result_response(
            request_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
            },
        )

    def _handle_tools_call(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        raw_name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        spec, is_external = self._resolve_tool(raw_name if isinstance(raw_name, str) else "")
        if spec is None:
            return self._error_response(request_id, JSON_RPC_INVALID_PARAMS, f"unknown tool: {raw_name}")
        if is_external:
            # 第三方工具全量审计（args 截断，防审计文件膨胀）
            self._audit(
                {
                    "tool": str(raw_name),
                    "plugin": spec.get("plugin", ""),
                    "args": json.dumps(arguments, ensure_ascii=False, default=str)[:2000],
                }
            )
            handler = spec["handler"]
        else:
            handler = spec["fn"]
        try:
            result = handler(arguments)
        except Exception as e:  # noqa: BLE001 - 工具内异常转 isError 响应
            return self._result_response(
                request_id,
                {
                    "content": [{"type": "text", "text": f"tool error: {e}"}],
                    "isError": True,
                },
            )
        if isinstance(result, str):
            text = result
        else:
            text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        return self._result_response(request_id, {"content": [{"type": "text", "text": text}]})

    @staticmethod
    def _result_response(request_id: Any, result: Any) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error_response(request_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    # ------------------------------------------------------------------
    # 工具注册
    # ------------------------------------------------------------------

    def _register_tools(self) -> None:
        def register(name: str, description: str, schema: Dict[str, Any], fn: Callable[[Dict[str, Any]], Any]) -> None:
            self._tools[name] = {"name": name, "description": description, "schema": schema, "fn": fn}

        register(
            "execute_command",
            "在服务器控制台执行一条原版/插件命令并返回回显。"
            f"硬拦命令（禁止执行）：{', '.join(sorted(BLOCKED_COMMAND_TOKENS))}——重启/重载必须由服主亲自操作。"
            "玩家名含特殊字符时由调用方自行转义。",
            {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "完整命令行，不含开头斜杠，如 list / give @s diamond 1"}},
                "required": ["command"],
            },
            self._tool_execute_command,
        )
        register(
            "get_server_status",
            "获取服务器状态：版本、TPS、MSPT、在线人数、运行时长、已加载插件列表。",
            {"type": "object", "properties": {}},
            self._tool_get_server_status,
        )
        register(
            "get_online_players",
            "获取在线玩家列表：名字、XUID、延迟、坐标、维度、游戏模式、设备系统、是否OP。",
            {"type": "object", "properties": {}},
            self._tool_get_online_players,
        )
        register(
            "get_player_info",
            "查玩家档案：在线状态、银行余额与排名、定期存款、领地数量/总价值/清单（走 ArcCore 数据）。",
            {
                "type": "object",
                "properties": {"player_name": {"type": "string", "description": "玩家名（大小写不敏感）"}},
                "required": ["player_name"],
            },
            self._tool_get_player_info,
        )
        register(
            "get_block_info",
            "按维度与坐标查方块类型。",
            {
                "type": "object",
                "properties": {
                    "dimension": {"type": "string", "description": "维度名：overworld / nether / the_end（也接受 minecraft: 前缀）"},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "z": {"type": "integer"},
                },
                "required": ["dimension", "x", "y", "z"],
            },
            self._tool_get_block_info,
        )
        register(
            "economy_top",
            "财富榜 Top N（银行存款余额降序，含玩家名）。",
            {
                "type": "object",
                "properties": {"count": {"type": "integer", "description": "取前 N 名，默认 10，上限 50"}},
            },
            self._tool_economy_top,
        )
        register(
            "query_sky_eye",
            "查天眼监控日志（开箱/破坏/攻击/死亡等行为记录，追查窃案入口）。"
            "可按玩家名（模糊）、行为类型、目标名、时间窗过滤。",
            {
                "type": "object",
                "properties": {
                    "player_name": {"type": "string", "description": "行为人玩家名（默认模糊匹配）"},
                    "action": {"type": "string", "description": "行为类型，如 PlayerDeath / BlockBreak / OpenContainer（别名 death/break/open 也可）"},
                    "target_name": {"type": "string", "description": "目标名（如被开箱子的领地名/被攻击者）"},
                    "minutes": {"type": "integer", "description": "只查最近 N 分钟"},
                    "limit": {"type": "integer", "description": "返回条数上限，默认 40，上限 100"},
                },
            },
            self._tool_query_sky_eye,
        )

    # ------------------------------------------------------------------
    # 第三方插件工具注册表
    # ------------------------------------------------------------------

    def _iter_external_tools(self) -> List[Dict[str, Any]]:
        """快照全部外部工具（附带 plugin 字段），遍历期间注册表可安全变更。"""
        with self._plugin_tools_lock:
            return [
                dict(spec, plugin=pname)
                for pname, specs in self._plugin_tools.items()
                for spec in specs
            ]

    def _resolve_tool(self, name: str) -> Tuple[Optional[Dict[str, Any]], bool]:
        """按暴露名解析工具（先剥 MCP_TOOL_PREFIX，裸名兼容）。返回 (spec, is_external)。"""
        bare = name
        if self.tool_prefix and bare.startswith(self.tool_prefix):
            bare = bare[len(self.tool_prefix):]
        if not bare:
            return None, False
        if bare in self._tools:
            return self._tools[bare], False
        for spec in self._iter_external_tools():
            if spec["name"] == bare:
                return spec, True
        return None, False

    def register_plugin_tools(self, plugin_name: str, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """注册第三方插件的 MCP 工具（幂等：同插件重复注册整体替换）。

        每个 spec：name（裸名，不带 MCP_TOOL_PREFIX）、description、
        schema（JSON Schema dict）、handler(args: dict) -> Any。

        线程约定：handler 在 MCP HTTP 工作线程被调用，须自行保证线程安全——
        委托 run_ai_tool 这类内部自带主线程跳转的入口即可；不要在 handler 里
        直接触碰玩家对象或执行命令（那请包一层 scheduler.run_task）。
        不在 MCP 层统一包 _run_on_main：handler 若再内部跳主线程会嵌套调度，
        有"主线程等主线程"死锁风险。

        重名（与内建或其他插件冲突）的工具按条拒绝并 warning，其余照常注册。

        返回 {"registered": [裸名...], "rejected": [[name, reason], ...]}。
        """
        pname = str(plugin_name or "").strip()
        if not pname:
            raise ValueError("plugin_name required")
        valid: List[Dict[str, Any]] = []
        rejected: List[List[str]] = []
        with self._plugin_tools_lock:
            # 冲突判定只看内建工具 + 其他插件（本插件旧注册允许被自身替换）
            taken = set(self._tools.keys())
            for owner, specs in self._plugin_tools.items():
                if owner == pname:
                    continue
                for spec in specs:
                    taken.add(spec["name"])
            for spec in tools or []:
                spec = spec if isinstance(spec, dict) else {}
                name = str(spec.get("name") or "").strip()
                handler = spec.get("handler")
                if not name or not callable(handler):
                    rejected.append([name or "?", "missing name or callable handler"])
                    continue
                if name in taken:
                    self._log("warning", f"plugin tool '{pname}:{name}' rejected: name conflict")
                    rejected.append([name, "name conflict"])
                    continue
                taken.add(name)
                valid.append(
                    {
                        "name": name,
                        "description": str(spec.get("description") or name),
                        "schema": spec.get("schema") if isinstance(spec.get("schema"), dict) else {"type": "object", "properties": {}},
                        "handler": handler,
                    }
                )
            if valid:
                self._plugin_tools[pname] = valid
            # valid 为空时不动旧注册：一次性校验失败不应把整个插件静默注销
        self._log(
            "info",
            f"plugin '{pname}' registered {len(valid)} MCP tool(s)"
            + (f", {len(rejected)} rejected" if rejected else ""),
        )
        return {"registered": [s["name"] for s in valid], "rejected": rejected}

    def unregister_plugin_tools(self, plugin_name: str) -> bool:
        """注销某插件的全部工具。返回是否确有注销。"""
        pname = str(plugin_name or "").strip()
        with self._plugin_tools_lock:
            removed = self._plugin_tools.pop(pname, None)
        if removed:
            self._log("info", f"plugin '{pname}' unregistered {len(removed)} MCP tool(s)")
        return bool(removed)

    # ------------------------------------------------------------------
    # 工具实现
    # ------------------------------------------------------------------

    def _tool_execute_command(self, args: Dict[str, Any]) -> Any:
        command = str(args.get("command") or "").strip()
        if not command:
            return {"success": False, "error": "empty command"}
        first_token = command.split()[0].lstrip("/").lower()
        blocked = first_token in BLOCKED_COMMAND_TOKENS
        self._audit({"tool": "execute_command", "command": command, "blocked": blocked})
        if blocked:
            self._log("warning", f"blocked command: {command}")
            return {
                "success": False,
                "blocked": True,
                "error": (
                    f"命令 '{first_token}' 已被 MCP 层硬拦：重启/重载必须由服主亲自在服务器控制台操作，"
                    "AI 不代劳。"
                ),
            }

        def _dispatch() -> Dict[str, Any]:
            server = self.plugin.server
            lines: List[str] = []
            sender = server.command_sender
            language = _safe(lambda: server.language)
            try:
                from endstone.command import CommandSenderWrapper  # 惰性导入，便于离线单测

                wrapper = CommandSenderWrapper(
                    sender,
                    on_message=lambda m: lines.append(_to_text(m, language)),
                    on_error=lambda m: lines.append("[error] " + _to_text(m, language)),
                )
            except Exception:  # noqa: BLE001 - 包装器不可用时退化为无回显执行
                wrapper = sender
            ok = bool(server.dispatch_command(wrapper, command))
            return {"success": ok, "output": lines}

        ok, result, error = self._run_on_main(_dispatch)
        if error is not None:
            self._log("error", f"execute_command failed: {command!r}: {error}")
            return {"success": False, "error": str(error)}
        return result

    def _tool_get_server_status(self, _args: Dict[str, Any]) -> Any:
        def _collect() -> Dict[str, Any]:
            server = self.plugin.server
            plugins = []
            try:
                for p in server.plugin_manager.plugins:
                    plugins.append(f"{p.name}@{getattr(p, 'version', '?')}")
            except Exception:
                pass
            start_time = _safe(lambda: server.start_time, None)
            uptime = round(time.time() - start_time, 0) if start_time else None
            return {
                "server_name": _safe(lambda: server.name),
                "endstone_version": _safe(lambda: server.version),
                "minecraft_version": _safe(lambda: server.minecraft_version),
                "online_count": _safe(lambda: len(server.online_players), 0),
                "max_players": _safe(lambda: server.max_players),
                "tps": {
                    "current": _safe(lambda: round(server.current_tps, 1)),
                    "average": _safe(lambda: round(server.average_tps, 1)),
                },
                "mspt": {
                    "current": _safe(lambda: round(server.current_mspt, 1)),
                    "average": _safe(lambda: round(server.average_mspt, 1)),
                },
                "uptime_seconds": uptime,
                "plugins": sorted(plugins),
            }

        ok, result, error = self._run_on_main(_collect)
        if error is not None:
            return {"error": str(error)}
        return result

    def _tool_get_online_players(self, _args: Dict[str, Any]) -> Any:
        def _collect() -> List[Dict[str, Any]]:
            players = []
            for p in self.plugin.server.online_players:
                location = _safe(lambda: p.location, None)
                players.append(
                    {
                        "name": _safe(lambda: p.name),
                        "xuid": _safe(lambda: p.xuid),
                        "ping": _safe(lambda: p.ping),
                        "dimension": _safe(lambda: location.dimension.name) if location else None,
                        "position": (
                            {
                                "x": _safe(lambda: round(location.x, 1)),
                                "y": _safe(lambda: round(location.y, 1)),
                                "z": _safe(lambda: round(location.z, 1)),
                            }
                            if location
                            else None
                        ),
                        "game_mode": _safe(lambda: str(p.game_mode)),
                        "device_os": _safe(lambda: p.device_os),
                        "is_op": _safe(lambda: p.is_op, False),
                    }
                )
            return players

        ok, result, error = self._run_on_main(_collect)
        if error is not None:
            return {"error": str(error)}
        return {"count": len(result or []), "players": result}

    def _tool_get_player_info(self, args: Dict[str, Any]) -> Any:
        player_name = str(args.get("player_name") or "").strip()
        if not player_name:
            return {"error": "player_name required"}
        plugin = self.plugin
        xuid = _safe(lambda: plugin.get_player_xuid_by_name(player_name))
        if not xuid:
            return {"found": False, "player_name": player_name}

        economy = _safe(lambda: plugin.economy, None)
        land_system = _safe(lambda: plugin.land_system, None)

        money = _safe(lambda: float(economy.get_player_money_by_xuid(xuid)), None) if economy else None
        rank = _safe(lambda: economy.get_player_money_rank_by_xuid(xuid)) if economy else None
        deposits_total = _safe(lambda: float(economy.get_fixed_deposits_total_by_xuid(xuid)), None) if economy else None
        matured_count = _safe(lambda: economy.count_matured_fixed_deposits_by_xuid(xuid)) if economy else None

        land_count = _safe(lambda: land_system.get_player_land_count(xuid), 0) if land_system else None
        land_total_value = _safe(lambda: float(land_system.get_player_lands_total_value(xuid)), None) if land_system else None
        lands: List[Dict[str, Any]] = []
        if land_system:
            player_lands = _safe(lambda: land_system.get_player_lands(xuid), {}) or {}
            for land_id, land in list(player_lands.items())[:20]:
                lands.append(
                    {
                        "land_id": land_id,
                        "name": land.get("land_name") or land.get("name"),
                        "dimension": land.get("dimension"),
                        "value": _safe(lambda: float(land.get("owner_paid_money") or 0)),
                    }
                )

        # 在线状态与实时位置（只读访问，与位置检测线程同款做法）
        online_player = _safe(lambda: self.plugin.server.get_player(player_name))
        info: Dict[str, Any] = {
            "found": True,
            "player_name": player_name,
            "xuid": str(xuid),
            "online": online_player is not None,
            "economy": {
                "balance": money,
                "rank": rank,
                "fixed_deposits_total": deposits_total,
                "fixed_deposits_matured": matured_count,
            },
            "lands": {"count": land_count, "total_value": land_total_value, "items": lands},
        }
        if online_player is not None:
            location = _safe(lambda: online_player.location)
            if location is not None:
                info["position"] = {
                    "dimension": _safe(lambda: location.dimension.name),
                    "x": _safe(lambda: round(location.x, 1)),
                    "y": _safe(lambda: round(location.y, 1)),
                    "z": _safe(lambda: round(location.z, 1)),
                }
        return info

    def _tool_get_block_info(self, args: Dict[str, Any]) -> Any:
        dimension_name = str(args.get("dimension") or "").strip()
        try:
            x, y, z = int(args["x"]), int(args["y"]), int(args["z"])
        except (KeyError, TypeError, ValueError):
            return {"error": "dimension/x/y/z required (integers)"}
        if not dimension_name:
            return {"error": "dimension required"}

        def _collect() -> Dict[str, Any]:
            level = self.plugin.server.level
            name = dimension_name
            dimension = _safe(lambda: level.get_dimension(name))
            if dimension is None and name.startswith("minecraft:"):
                dimension = _safe(lambda: level.get_dimension(name.split(":", 1)[1]))
            if dimension is None:
                return {"error": f"dimension not found: {dimension_name}"}
            block = dimension.get_block_at(x, y, z)
            return {
                "type": _safe(lambda: block.type),
                "position": {"x": x, "y": y, "z": z},
                "dimension": _safe(lambda: dimension.name),
            }

        ok, result, error = self._run_on_main(_collect)
        if error is not None:
            return {"error": str(error)}
        return result

    def _tool_economy_top(self, args: Dict[str, Any]) -> Any:
        try:
            count = int(args.get("count") or 10)
        except (TypeError, ValueError):
            count = 10
        count = max(1, min(count, 50))
        economy = _safe(lambda: self.plugin.economy, None)
        if economy is None:
            return {"error": "economy unavailable"}
        rows = _safe(lambda: economy.get_top_richest_xuids(count), []) or []

        # xuid -> 玩家名（player_basic_info 本地库必在；查不到就显示 ?）
        name_map: Dict[str, str] = {}
        db = _safe(lambda: self.plugin.database_manager, None)
        if db is not None and rows:
            xuids = [str(r.get("xuid") or "") for r in rows if r.get("xuid")]
            if xuids:
                placeholders = ",".join("?" * len(xuids))
                for row in _safe(
                    lambda: db.query_all(
                        f"SELECT xuid, name FROM player_basic_info WHERE xuid IN ({placeholders})",
                        tuple(xuids),
                    ),
                    [],
                ) or []:
                    name_map[str(row.get("xuid") or "")] = str(row.get("name") or "?")
        ranking = []
        for index, row in enumerate(rows, start=1):
            xuid = str(row.get("xuid") or "")
            ranking.append(
                {
                    "rank": index,
                    "name": name_map.get(xuid, "?"),
                    "xuid": xuid,
                    "money": _safe(lambda: float(row.get("money") or 0), 0.0),
                }
            )
        return {"count": len(ranking), "ranking": ranking}

    def _tool_query_sky_eye(self, args: Dict[str, Any]) -> Any:
        store = _safe(lambda: self.plugin.sky_eye_store, None)
        if store is None:
            return {"error": "sky eye store unavailable"}
        kwargs: Dict[str, Any] = {}
        for key in ("player_name", "action", "target_name"):
            value = str(args.get(key) or "").strip()
            if value:
                kwargs[key] = value
        if args.get("minutes") is not None:
            try:
                kwargs["minutes"] = int(args["minutes"])
            except (TypeError, ValueError):
                return {"error": "minutes must be an integer"}
        try:
            limit = int(args.get("limit") or 40)
        except (TypeError, ValueError):
            limit = 40
        kwargs["limit"] = max(1, min(limit, 100))
        records = _safe(lambda: store.query(**kwargs), []) or []
        return {"count": len(records), "records": records}


class _MCPHTTPServer(ThreadingHTTPServer):
    """Windows 下 SO_REUSEADDR 允许两个进程绑同一端口且不报错，连接会被随机
    路由到其中一个——两台服若撞端口会静默错乱。显式关闭，撞端口直接 bind 失败。"""

    allow_reuse_address = 0
    daemon_threads = True


class _MCPRequestHandler(BaseHTTPRequestHandler):
    """POST /mcp = JSON-RPC；其余方法 405。鉴权失败一律 401（不泄露细节）。"""

    # 由 functools.partial 注入
    mcp_server: MCPServer

    def do_POST(self) -> None:  # noqa: N802 - http.server 命名约定
        mcp = self.mcp_server
        if self.path.split("?", 1)[0] != "/mcp":
            self._send_json(404, {"error": "not found, endpoint is /mcp"})
            return
        if not mcp.token or not self._check_auth():
            self._send_json(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length > 0 else b"{}"
            payload = json.loads(raw.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            self._send_json(200, mcp._error_response(None, JSON_RPC_PARSE_ERROR, f"parse error: {e}"))
            return
        response = mcp.handle_jsonrpc(payload)
        if response is None:  # 通知：HTTP 202 无 body
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send_json(200, response)

    def do_GET(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        # 无会话状态，无需终止会话
        self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        self.send_response(405)
        self.send_header("Allow", "POST")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _check_auth(self) -> bool:
        header = self.headers.get("Authorization") or ""
        if header.startswith("Bearer "):
            return secrets.compare_digest(header[7:].strip(), self.mcp_server.token)
        # 兼容用查询参数传 token：/mcp?token=xxx
        from urllib.parse import parse_qs, urlsplit

        query = parse_qs(urlsplit(self.path).query)
        supplied = (query.get("token") or [""])[0]
        return bool(supplied) and secrets.compare_digest(supplied, self.mcp_server.token)

    def _send_json(self, status: int, obj: Dict[str, Any]) -> None:
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - 父类签名
        # 默认会往 stderr 打每条访问日志，改为静默（审计走 mcp_audit.jsonl）
        return


def generate_mcp_token() -> str:
    """生成 32 位十六进制 token（写入 MCP_TOKEN 设置）。"""
    return secrets.token_hex(16)
