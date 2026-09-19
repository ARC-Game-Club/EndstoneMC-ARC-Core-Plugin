# -*- coding: utf-8 -*-
"""跨服数据同步后端服务端"""
import json
import socket
import threading
import time
import uuid
from contextlib import suppress
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

from endstone_arc_core.sync_config import (
    categories_from_tables,
    filter_incoming_settings,
    snapshot_shared_settings,
)
from endstone_arc_core.sync_plugin_api import (
    build_create_table_sql,
    is_plugin_logical_name,
    normalize_fields,
    normalize_primary_keys,
    parse_logical_name,
    physical_from_logical,
    select_all_physical_rows,
    query_physical_rows,
)
from endstone_arc_core.sync_protocol import (
    SyncMessageType,
    SyncTable,
    TABLE_TO_ENUM,
    ENUM_TO_TABLE,
    PROTOCOL_VERSION,
    REQUEST_TO_RESPONSE,
    decode_message,
    build_auth_response,
    build_query_response,
    build_data_response,
    build_batch_sync_response,
    build_full_sync_response,
    build_heartbeat,
    build_push_notify,
    build_error_response,
    build_settings_push,
)
from endstone_arc_core.sync_write import iter_mirror_write_actions, query_sync_table, select_all_sync_table
from endstone_arc_core.sync_player_audit import (
    append_player_sync_log,
    classify_basic_info_event,
    extract_xuid_from_request,
    guard_basic_info_counters,
    format_counter_changes,
    player_label,
    summarize_basic_info_row,
)


@dataclass(eq=False)
class ConnectedClient:
    """已连接的客户端（按对象身份参与 set，字段可变）"""
    conn: socket.socket
    addr: tuple
    server_id: str = ""
    server_name: str = ""
    authenticated: bool = False
    # 全量同步完成前不接受 PUSH，避免与 request/response 粘包错位
    accepts_push: bool = False
    last_heartbeat: float = field(default_factory=time.time)
    sync_tables: Set[str] = field(default_factory=set)
    # 第三方插件逻辑表名 plugin_id:table
    plugin_tables: Set[str] = field(default_factory=set)
    protocol_version: int = 1

    def is_alive(self) -> bool:
        """检查连接是否存活（心跳超时 60 秒）"""
        return time.time() - self.last_heartbeat < 60


class SyncServer:
    """跨服数据同步后端服务端
    
    运行在独立的线程中，接收来自多个插件端服务器的连接请求，
    并将数据变更同步给所有已连接的客户端。
    """

    def __init__(
        self,
        database_manager,
        auth_key: str = "",
        bind_host: str = "0.0.0.0",  # nosec B104 — 跨服同步中心需监听所有网卡
        bind_port: int = 19999,
        logger=None,
        setting_manager=None,
        on_economy_mutated: Optional[Callable[[], None]] = None,
        audit_log_path: str = "",
    ):
        """
        初始化同步服务器

        :param database_manager: 数据库管理器实例
        :param auth_key: 认证密钥
        :param bind_host: 绑定地址
        :param bind_port: 绑定端口
        :param logger: 日志记录器
        :param setting_manager: 配置管理器（用于向从服下发玩法配置）
        :param on_economy_mutated: 从服成功写入 player_economy 后的回调（主服条件头衔刷新）
        :param audit_log_path: 玩家数据同步审计日志文件路径（player_basic_info 进退服/变更/查询全记录）
        """
        self.db = database_manager
        self.settings = setting_manager
        self.auth_key = auth_key
        self.bind_host = bind_host
        self.bind_port = bind_port
        self.logger = logger
        self._on_economy_mutated = on_economy_mutated
        self.audit_log_path = audit_log_path
        # 无变化整行上行（对账重放）计数：按客户端合并降噪，不逐行刷日志
        self._noop_uplink_counts: Dict[str, int] = {}
        
        self._socket: Optional[socket.socket] = None
        self._running = False
        self._server_thread: Optional[threading.Thread] = None
        self._clients: Set[ConnectedClient] = set()
        self._clients_lock = threading.Lock()
        
        # 需要同步的表列表
        self._sync_tables = set(TABLE_TO_ENUM.keys())
        # 逻辑表名 -> {"fields", "primary_keys"}（来自客户端 auth 或本机插件注册）
        self._plugin_schemas: Dict[str, Dict[str, Any]] = {}
        self._plugin_schema_lock = threading.Lock()

        # 变更记录队列（用于异步推送给客户端）
        self._change_queue: List[Dict[str, Any]] = []
        self._change_queue_lock = threading.Lock()

        # 全量同步锁（防止同步期间数据不一致）
        self._full_sync_lock = threading.Lock()

    def _log(self, level: str, message: str):
        """安全日志记录"""
        if self.logger:
            getattr(self.logger, level.lower(), self.logger.info)(f"[ARC SyncServer] {message}")
        else:
            print(f"[{level.upper()}] [ARC SyncServer] {message}")

    def _player_audit(self, line: str, level: str = "info") -> None:
        """玩家同步审计：写 player_sync_log.txt 并进服务器日志，双落点。"""
        append_player_sync_log(self.audit_log_path, line)
        self._log(level, line)

    def _fetch_basic_info_old(self, data: Dict) -> Optional[Dict[str, Any]]:
        """按请求定位中心侧旧行：整行 xuid 或 where+params（xuid = ?）。"""
        xuid = extract_xuid_from_request(data)
        if not xuid:
            return None
        try:
            rows = query_sync_table(self.db, "player_basic_info", "xuid = ?", (xuid,))
        except Exception:
            return None
        return rows[0] if rows else None

    def _noop_key(self, client: ConnectedClient) -> str:
        return client.server_id or f"{client.addr[0]}:{client.addr[1]}"

    def _record_noop_uplink(self, client: ConnectedClient) -> None:
        """累计无变化行；每满 200 行输出一条汇总，避免整表重放刷屏。"""
        key = self._noop_key(client)
        self._noop_uplink_counts[key] = self._noop_uplink_counts.get(key, 0) + 1
        count = self._noop_uplink_counts[key]
        if count % 200 == 0:
            self._player_audit(
                f"[对账] 从服<{client.server_name}> 无变化整行上行已累计 ×{count}"
                f"（原值落库，无数据变更）"
            )

    def _take_noop_pending(self, client: ConnectedClient) -> None:
        """真实事件到来前，先汇总冲掉此前积累的无变化行计数。"""
        key = self._noop_key(client)
        count = self._noop_uplink_counts.pop(key, 0)
        if count > 0:
            self._player_audit(
                f"[对账] 从服<{client.server_name}> 无变化整行上行 ×{count}"
                f"（原值落库，无数据变更）"
            )

    def _audit_basic_info_payload(
        self, client: ConnectedClient, data: Dict, op_label: str
    ) -> Dict[str, Any]:
        """写前审计：取旧行 → 分类事件 → 计数回退防护（就地改写 data['data']）。

        返回审计上下文；写后由 _audit_basic_info_after 补 old→new 一行。
        """
        ctx: Dict[str, Any] = {"old_row": None, "event": "", "guarded": False}
        row_data = data.get("data")
        if not isinstance(row_data, dict) or not row_data:
            return ctx
        old_row = self._fetch_basic_info_old(data)
        event = classify_basic_info_event(old_row, row_data)
        if event == "无变化":
            # 与中心完全一致的整行（对账重放）：不逐行记审计，只计数
            ctx["old_row"] = old_row
            ctx["event"] = "无变化"
            self._record_noop_uplink(client)
            return ctx
        guarded_data, blocked = guard_basic_info_counters(old_row, row_data)
        if blocked:
            # 就地替换，_handle_insert/_handle_update 持有的是同一引用
            data["data"] = guarded_data
            ctx["guarded"] = True
            self._player_audit(
                f"[拦截回退] 从服<{client.server_name}> {player_label(row_data)}"
                f" {' | '.join(blocked)} → 均按原值保留（{op_label}，按 {event} 载荷处理）",
                level="warning",
            )
        ctx["old_row"] = old_row
        ctx["event"] = event
        return ctx

    def _audit_basic_info_after(
        self,
        client: ConnectedClient,
        data: Dict,
        ctx: Dict[str, Any],
        op_label: str,
        success: bool,
        error: str = "",
    ) -> None:
        """写后审计：一行 old→new（含进退服、时长变化、拦截后实际生效值）。"""
        if not ctx or not ctx.get("event"):
            return
        if ctx["event"] == "无变化":
            # 已在 _record_noop_uplink 计数汇总，不逐行记审计
            return
        self._take_noop_pending(client)
        server = f"从服<{client.server_name}>"
        new_data = data.get("data") or {}
        old_row = ctx.get("old_row")
        if not success:
            self._player_audit(
                f"[写入失败] {server} {player_label(new_data)}"
                f" {op_label} 失败: {error or '未知错误'}",
                level="error",
            )
            return
        if old_row is None:
            new_row = self._fetch_basic_info_old(data)
            self._player_audit(
                f"[{ctx['event']}] {server} {player_label(new_row or new_data)}"
                f" 中心新建档 | {format_counter_changes(None, new_row or new_data)}"
            )
            return
        new_row = self._fetch_basic_info_old(data)
        final_view = new_row if new_row else {**old_row, **new_data}
        # 只展示本次上报涉及的字段（值取中心侧最终值），避免每次都把整行打出来
        display_view = {k: v for k, v in final_view.items() if k in new_data}
        self._player_audit(
            f"[{ctx['event']}] {server} {player_label(final_view)}"
            f" {format_counter_changes(old_row, display_view)}"
        )

    def start(self) -> bool:
        """启动同步服务器"""
        if self._running:
            self._log("warning", "Server is already running")
            return True
        
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self.bind_host, self.bind_port))
            self._socket.listen(10)
            self._socket.settimeout(5.0)  # 5秒超时，用于检查_running标志
            
            self._running = True
            self._server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self._server_thread.start()
            
            self._log("info", f"Sync server started on {self.bind_host}:{self.bind_port}")
            return True
        except Exception as e:
            self._log("error", f"Failed to start sync server: {e}")
            self._running = False
            return False

    def stop(self):
        """停止同步服务器"""
        if not self._running:
            return
        
        self._running = False
        
        # 关闭所有客户端连接
        with self._clients_lock:
            for client in self._clients:
                with suppress(OSError):
                    client.conn.close()
            self._clients.clear()

        if self._socket:
            with suppress(OSError):
                self._socket.close()
            self._socket = None
        
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=5)
        
        self._log("info", "Sync server stopped")

    def is_running(self) -> bool:
        """检查服务器是否运行中"""
        return self._running

    def _server_loop(self):
        """服务器主循环"""
        while self._running:
            try:
                client_socket, addr = self._socket.accept()
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, addr),
                    daemon=True
                )
                client_thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    self._log("error", f"Accept connection error: {e}")
                break
        
        # 清理客户端
        self._cleanup_dead_clients()

    def _handle_client(self, conn: socket.socket, addr: tuple):
        """处理客户端连接"""
        client = ConnectedClient(conn=conn, addr=addr)
        buffer = b""
        
        try:
            conn.settimeout(30.0)
            
            while self._running:
                try:
                    data = conn.recv(4096)
                    if not data:
                        break
                    
                    buffer += data
                    
                    # 处理粘包
                    while len(buffer) >= 5:
                        msg_len = int.from_bytes(buffer[:4], 'big')
                        if len(buffer) < 5 + msg_len:
                            break  # 数据不完整，等待更多数据
                        
                        raw_msg = buffer[:5 + msg_len]
                        buffer = buffer[5 + msg_len:]
                        
                        self._process_message(client, raw_msg)
                        
                except socket.timeout:
                    if not client.authenticated:
                        break  # 未认证的客户端超时断开
                    continue
                except OSError as e:
                    # 关服时 stop() 会从其它线程 close 套接字；Windows 上 recv 常报
                    # WinError 10038（非套接字操作），属预期清理，勿当故障打 ERROR。
                    if self._running:
                        self._log("error", f"Client {addr} error: {e}")
                    break
                except Exception as e:
                    if self._running:
                        self._log("error", f"Client {addr} error: {e}")
                    break
            
        except Exception as e:
            if self._running:
                self._log("error", f"Client {addr} handler error: {e}")
        finally:
            # 移除客户端
            with self._clients_lock:
                self._clients.discard(client)
            try:
                conn.close()
            except Exception:
                pass
            if self._running:
                self._log("info", f"Client {addr} disconnected")

    def _process_message(self, client: ConnectedClient, raw_msg: bytes):
        """处理接收到的消息"""
        try:
            msg_type, data = decode_message(raw_msg)
            client.last_heartbeat = time.time()

            if msg_type == SyncMessageType.AUTH_REQUEST:
                self._handle_auth(client, data)
                return
            if msg_type == SyncMessageType.HEARTBEAT:
                self._handle_heartbeat(client)
                return
            if not client.authenticated:
                client.conn.sendall(build_error_response(1, "Not authenticated"))
                return

            handler = self._AUTHED_HANDLERS.get(msg_type)
            if handler:
                handler(self, client, data)
            else:
                client.conn.sendall(
                    build_error_response(2, f"Unknown message type: {msg_type}")
                )
        except Exception as e:
            self._log("error", f"Process message error: {e}")
            try:
                client.conn.sendall(build_error_response(3, str(e)))
            except Exception:
                pass

    # 已认证后的消息分发（避免长 elif 链抬高圈复杂度）
    _AUTHED_HANDLERS = {
        SyncMessageType.QUERY_REQUEST: lambda self, c, d: self._handle_query(c, d),
        SyncMessageType.INSERT_REQUEST: lambda self, c, d: self._handle_insert(c, d),
        SyncMessageType.UPDATE_REQUEST: lambda self, c, d: self._handle_update(c, d),
        SyncMessageType.DELETE_REQUEST: lambda self, c, d: self._handle_delete(c, d),
        SyncMessageType.BATCH_SYNC_REQUEST: lambda self, c, d: self._handle_batch_sync(c, d),
        SyncMessageType.FULL_SYNC_REQUEST: lambda self, c, d: self._handle_full_sync(c, d),
        SyncMessageType.PULL_REQUEST: lambda self, c, d: self._handle_pull(c, d),
        SyncMessageType.SETTINGS_PULL_REQUEST: lambda self, c, d: self._handle_settings_pull(c, d),
    }

    def _handle_auth(self, client: ConnectedClient, data: Dict):
        """处理认证请求"""
        server_id = data.get('server_id', '')
        server_name = data.get('server_name', '')
        auth_key = data.get('auth_key', '')

        if self.auth_key and auth_key != self.auth_key:
            client.conn.sendall(build_auth_response(False, "Invalid auth key"))
            self._log("warning", f"Auth failed for {client.addr}: invalid key")
            return

        client.server_id = server_id
        client.server_name = server_name
        client.authenticated = True
        try:
            client.protocol_version = int(data.get('protocol_version') or 1)
        except (TypeError, ValueError):
            client.protocol_version = 1

        requested_tables = data.get('sync_tables')
        if isinstance(requested_tables, list):
            # 空列表表示仅事件转发、不同步任何表
            client.sync_tables = {
                str(t) for t in requested_tables if str(t) in self._sync_tables
            }
        else:
            client.sync_tables = set(self._sync_tables)

        client.plugin_tables = self._absorb_plugin_tables(data.get('plugin_tables'))

        with self._clients_lock:
            self._clients.add(client)

        auth_settings = None
        if client.protocol_version >= 2:
            auth_settings = self._settings_for_client(client)
        client.conn.sendall(build_auth_response(
            True,
            "Authentication successful",
            settings=auth_settings,
            protocol_version=PROTOCOL_VERSION,
        ))
        self._log("info", f"Client authenticated: {server_name} ({server_id}) from {client.addr}")

    def _absorb_plugin_tables(self, raw: Any) -> Set[str]:
        """登记客户端声明的插件表并确保中心物理表存在（字段类型与主键均校验）。"""
        allowed: Set[str] = set()
        if not isinstance(raw, list):
            return allowed
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get('name') or '').strip()
            parsed = parse_logical_name(name)
            if not parsed:
                continue
            fields = item.get('fields')
            pks = item.get('primary_keys')
            if not isinstance(fields, dict) or not fields:
                with self._plugin_schema_lock:
                    if name not in self._plugin_schemas:
                        continue
            else:
                try:
                    self._ensure_plugin_table(name, fields, pks)
                except Exception as e:
                    self._log("warning", f"Ensure plugin table {name} failed: {e}")
                    continue
            allowed.add(name)
        return allowed

    def register_plugin_namespace(
        self, logical_tables: Dict[str, Any]
    ) -> None:
        """本机插件注册：记录 schema 并建物理表（同步中心侧）。

        logical_tables: {logical_name: {"fields": {...}, "primary_keys": [...]}}
        或兼容旧调用 {logical_name: fields_dict}。
        """
        for name, meta in (logical_tables or {}).items():
            try:
                if isinstance(meta, dict) and "fields" in meta:
                    self._ensure_plugin_table(
                        name, meta.get("fields"), meta.get("primary_keys")
                    )
                else:
                    self._ensure_plugin_table(name, meta, None)
            except Exception as e:
                self._log("error", f"Register plugin table {name} error: {e}")

    def _ensure_plugin_table(
        self, logical: str, fields: Any, primary_keys: Any = None
    ) -> str:
        phys = physical_from_logical(logical)
        if not phys:
            raise ValueError(f"invalid plugin table name: {logical!r}")
        norm_fields = normalize_fields(fields)
        # 已有 schema 且未给 PK 时沿用旧 PK，避免重复注册丢主键
        with self._plugin_schema_lock:
            prev = self._plugin_schemas.get(logical) or {}
        if primary_keys is None and prev.get("primary_keys"):
            pks = list(prev["primary_keys"])
        else:
            pks = normalize_primary_keys(primary_keys, norm_fields)
        create_sql = build_create_table_sql(phys, norm_fields, pks)
        with self._plugin_schema_lock:
            self._plugin_schemas[logical] = {
                "fields": dict(norm_fields),
                "primary_keys": list(pks),
            }
        if not self.db.table_exists(phys):
            # 不用 create_table：需要表级复合主键
            if not self.db.execute(create_sql):
                raise RuntimeError(f"create plugin table failed: {phys}")
        return phys

    def _resolve_request_tables(
        self, client: ConnectedClient, data: Dict
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """返回 (core_table, plugin_logical, physical)；均未授权时 physical 为 None。"""
        table_name = data.get('table_name')
        if is_plugin_logical_name(table_name):
            logical = str(table_name).strip()
            if client is not None and logical not in client.plugin_tables:
                return None, logical, None
            phys = physical_from_logical(logical)
            with self._plugin_schema_lock:
                known = logical in self._plugin_schemas
            if not phys or not known:
                return None, logical, None
            return None, logical, phys
        try:
            table_enum = SyncTable(data.get('table', 0))
        except ValueError:
            return None, None, None
        core = ENUM_TO_TABLE.get(table_enum)
        if core not in self._sync_tables:
            return None, None, None
        return core, None, core

    def _handle_heartbeat(self, client: ConnectedClient):
        """处理心跳包"""
        client.last_heartbeat = time.time()
        # 客户端进入 listen 循环后才会发心跳，此时全量同步已结束
        client.accepts_push = True
        try:
            client.conn.sendall(build_heartbeat())
        except Exception:
            pass


    def _handle_query(self, client: ConnectedClient, data: Dict):
        """处理查询请求"""
        try:
            core_table, plugin_logical, phys = self._resolve_request_tables(client, data)
            where = data.get('where', '1=1')
            params = data.get('params', [])

            if not phys:
                client.conn.sendall(build_query_response(False, [], "Table not allowed"))
                return

            if plugin_logical:
                results = query_physical_rows(self.db, phys, where, tuple(params))
            else:
                results = query_sync_table(self.db, core_table, where, tuple(params))
            if core_table == "player_basic_info":
                summary = summarize_basic_info_row(results[0]) if results else "(无记录)"
                self._player_audit(
                    f"[查询] 从服<{client.server_name}> where={where!r}"
                    f" params={list(params or [])} → {len(results)}行: {summary}"
                )
            client.conn.sendall(build_query_response(True, results))
        except Exception as e:
            client.conn.sendall(build_query_response(False, [], str(e)))
            self._log("error", f"Query error: {e}")

    def _notify_economy_mutated(self, table_name: Optional[str]) -> None:
        if table_name != "player_economy":
            return
        cb = self._on_economy_mutated
        if cb is None:
            return
        try:
            cb()
        except Exception as e:
            self._log("error", f"on_economy_mutated error: {e}")

    def _apply_client_mutation(
        self,
        client: ConnectedClient,
        data: Dict,
        *,
        log_label: str,
        push_op: str,
        request_type: SyncMessageType,
    ) -> None:
        """校验表权限 → （玩家表：审计+计数回退防护）→ 抑制通知写库 → 成功则广播 → 回响应（带 seq）。"""
        seq = data.get("seq")
        try:
            seq = int(seq) if seq is not None else None
        except (TypeError, ValueError):
            seq = None
        resp_type = REQUEST_TO_RESPONSE.get(
            request_type, SyncMessageType.INSERT_RESPONSE
        )
        audit_ctx: Optional[Dict[str, Any]] = None
        try:
            core_table, plugin_logical, phys = self._resolve_request_tables(client, data)
            if not phys:
                client.conn.sendall(
                    build_data_response(
                        resp_type, False, 0, "Table not allowed", seq=seq
                    )
                )
                return
            if phys == "player_basic_info" and isinstance(data.get("data"), dict):
                audit_ctx = self._audit_basic_info_payload(client, data, log_label)
            row_data = dict(data.get("data") or {})
            with self.db.suppress_write_notify():
                if push_op == "insert":
                    success = self.db.upsert(phys, row_data)
                elif push_op == "update":
                    success = self.db.update(
                        phys,
                        row_data,
                        data.get("where", ""),
                        tuple(data.get("params") or []),
                    )
                else:
                    success = False
            if success:
                if push_op == "update":
                    push_payload: Dict = {
                        **row_data,
                        "_where": data.get("where", ""),
                        "_params": list(data.get("params") or []),
                    }
                else:
                    push_payload = row_data
                self._broadcast_push_resolved(
                    core_table, plugin_logical, push_op, push_payload, exclude=client
                )
                self._notify_economy_mutated(core_table)
            if audit_ctx is not None:
                self._audit_basic_info_after(client, data, audit_ctx, log_label, success)
            client.conn.sendall(
                build_data_response(
                    resp_type, success, 1 if success else 0, seq=seq
                )
            )
        except Exception as e:
            client.conn.sendall(
                build_data_response(resp_type, False, 0, str(e), seq=seq)
            )
            self._log("error", f"{log_label} error: {e}")
            if audit_ctx is not None:
                self._audit_basic_info_after(
                    client, data, audit_ctx, log_label, False, str(e)
                )

    def _handle_insert(self, client: ConnectedClient, data: Dict):
        """处理插入/整行 upsert 请求"""
        self._apply_client_mutation(
            client,
            data,
            log_label="Insert",
            push_op="insert",
            request_type=SyncMessageType.INSERT_REQUEST,
        )

    def _handle_update(self, client: ConnectedClient, data: Dict):
        """处理更新请求"""
        self._apply_client_mutation(
            client,
            data,
            log_label="Update",
            push_op="update",
            request_type=SyncMessageType.UPDATE_REQUEST,
        )

    def _handle_delete(self, client: ConnectedClient, data: Dict):
        """处理删除请求"""
        core_table, _plugin_logical, phys = self._resolve_request_tables(client, data)
        if phys == "player_basic_info":
            # 玩家主数据删除属高危操作：审计留痕（行为不变）
            self._player_audit(
                f"[删除] 从服<{client.server_name}> 请求删除 player_basic_info:"
                f" where={data.get('where', '')!r} params={list(data.get('params') or [])}",
                level="warning",
            )
        self._apply_client_mutation(
            client,
            data,
            log_label="Delete",
            push_op="delete",
            request_type=SyncMessageType.DELETE_REQUEST,
        )

    def _run_batch_op(self, op_type: str, table_name: str, op: Dict) -> Dict:
        runners = {
            "insert": lambda: self.db.upsert(table_name, op.get("data", {})),
            "update": lambda: self.db.update(
                table_name,
                op.get("data", {}),
                op.get("where", ""),
                tuple(op.get("params", [])),
            ),
            "delete": lambda: self.db.delete(
                table_name, op.get("where", ""), tuple(op.get("params", []))
            ),
        }
        runner = runners.get(op_type)
        if not runner:
            return {"success": False, "error": "Unknown operation type"}
        with self.db.suppress_write_notify():
            return {"success": runner()}

    def _broadcast_batch_op(self, client: ConnectedClient, op: Dict) -> None:
        table_enum = SyncTable(op.get("table", 0))
        op_type = op.get("type")
        if op_type == "insert":
            self._broadcast_push(table_enum, "insert", op.get("data", {}), exclude=client)
        elif op_type == "update":
            self._broadcast_push(table_enum, "update", op.get("data", {}), exclude=client)
        elif op_type == "delete":
            self._broadcast_push(
                table_enum,
                "delete",
                {"_where": op.get("where", ""), "_params": op.get("params", [])},
                exclude=client,
            )

    def _handle_batch_sync(self, client: ConnectedClient, data: Dict):
        """处理批量同步请求"""
        try:
            operations = data.get("operations", [])
            results = []
            economy_touched = False
            for op in operations:
                table_name = ENUM_TO_TABLE.get(SyncTable(op.get("table", 0)))
                if table_name not in self._sync_tables:
                    results.append({"success": False, "error": "Table not allowed"})
                    continue
                audit_ctx = None
                if table_name == "player_basic_info" and isinstance(op.get("data"), dict):
                    audit_ctx = self._audit_basic_info_payload(
                        client, op, f"Batch/{op.get('type', '?')}"
                    )
                result = self._run_batch_op(op.get("type"), table_name, op)
                results.append(result)
                if audit_ctx is not None:
                    self._audit_basic_info_after(
                        client,
                        op,
                        audit_ctx,
                        f"Batch/{op.get('type', '?')}",
                        bool(result.get("success")),
                        str(result.get("error") or ""),
                    )
                if result.get("success") and table_name == "player_economy":
                    economy_touched = True

            client.conn.sendall(build_batch_sync_response(True, results))
            for op, result in zip(operations, results):
                if result.get("success"):
                    self._broadcast_batch_op(client, op)
            if economy_touched:
                self._notify_economy_mutated("player_economy")
        except Exception as e:
            client.conn.sendall(build_batch_sync_response(False, [], str(e)))
            self._log("error", f"Batch sync error: {e}")

    def _handle_full_sync(self, client: ConnectedClient, data: Dict):
        """处理全量同步请求。

        只在读库时短暂加锁，发送响应不占锁，避免多从服互相堵到超时。
        """
        try:
            core_table, plugin_logical, phys = self._resolve_request_tables(client, data)

            if not phys:
                client.conn.sendall(build_full_sync_response(False, [], "Table not allowed"))
                return

            with self._full_sync_lock:
                if plugin_logical:
                    rows = select_all_physical_rows(self.db, phys)
                else:
                    rows = select_all_sync_table(self.db, core_table)
            client.conn.sendall(build_full_sync_response(True, rows))
            label = plugin_logical or core_table
            self._log(
                "info",
                f"Full sync for {label}: {len(rows)} rows to {client.server_name}",
            )
        except Exception as e:
            try:
                client.conn.sendall(build_full_sync_response(False, [], str(e)))
            except Exception:
                pass
            self._log("error", f"Full sync error: {e}")

    def _handle_pull(self, client: ConnectedClient, data: Dict):
        """处理拉取请求"""
        try:
            core_table, plugin_logical, phys = self._resolve_request_tables(client, data)
            where = data.get('where', '1=1')
            params = data.get('params', [])

            if not phys:
                client.conn.sendall(build_query_response(False, [], "Table not allowed"))
                return

            if plugin_logical:
                results = query_physical_rows(self.db, phys, where, tuple(params))
            else:
                results = query_sync_table(self.db, core_table, where, tuple(params))
            if core_table == "player_basic_info":
                summary = summarize_basic_info_row(results[0]) if results else "(无记录)"
                self._player_audit(
                    f"[查询] 从服<{client.server_name}> PULL where={where!r}"
                    f" params={list(params or [])} → {len(results)}行: {summary}"
                )
            client.conn.sendall(build_query_response(True, results))
        except Exception as e:
            client.conn.sendall(build_query_response(False, [], str(e)))

    def _settings_for_client(self, client: ConnectedClient) -> Dict[str, str]:
        if self.settings is None:
            return {}
        cats = categories_from_tables(client.sync_tables)
        return snapshot_shared_settings(self.settings, cats)

    def _handle_settings_pull(self, client: ConnectedClient, data: Dict) -> None:
        try:
            settings = self._settings_for_client(client)
            client.conn.sendall(build_settings_push(settings))
        except Exception as e:
            self._log("error", f"Settings pull error: {e}")

    def broadcast_settings(self, settings: Optional[Dict[str, str]] = None) -> None:
        """向协议版本 >=2 的从服推送玩法配置（可部分键；None 表示按客户端类别全量快照）。"""
        disconnected = []
        with self._clients_lock:
            for client in self._clients:
                if not client.authenticated or client.protocol_version < 2:
                    continue
                cats = categories_from_tables(client.sync_tables)
                if settings is None:
                    payload = self._settings_for_client(client)
                else:
                    payload = filter_incoming_settings(settings, cats)
                if not payload:
                    continue
                try:
                    client.conn.sendall(build_settings_push(payload))
                except Exception:
                    disconnected.append(client)
            for client in disconnected:
                self._clients.discard(client)

    def _broadcast_push(self, table: SyncTable, operation: str, data: Dict, exclude: Optional[ConnectedClient] = None):
        """广播内置表推送通知给所有已连接的客户端"""
        table_name = ENUM_TO_TABLE.get(table)
        self._broadcast_push_resolved(table_name, None, operation, data, exclude=exclude)

    def _broadcast_push_resolved(
        self,
        core_table: Optional[str],
        plugin_logical: Optional[str],
        operation: str,
        data: Dict,
        exclude: Optional[ConnectedClient] = None,
    ):
        """按 core 表名或插件逻辑表名广播 PUSH。"""
        table_enum = TABLE_TO_ENUM.get(core_table) if core_table else None
        msg = build_push_notify(
            table_enum if table_enum is not None else 0,
            operation,
            data,
            table_name=plugin_logical,
        )
        disconnected = []

        with self._clients_lock:
            for client in self._clients:
                if client is exclude:
                    continue
                if not client.accepts_push:
                    continue
                if plugin_logical:
                    if plugin_logical not in client.plugin_tables:
                        continue
                elif core_table and client.sync_tables and core_table not in client.sync_tables:
                    continue
                if not client.is_alive():
                    disconnected.append(client)
                    continue
                try:
                    client.conn.sendall(msg)
                except Exception:
                    disconnected.append(client)

            for client in disconnected:
                self._clients.discard(client)

    def apply_plugin_upsert(self, logical: str, row: Dict[str, Any]) -> bool:
        """同步中心本机插件写：落物理表并广播（不经 outbox）。"""
        if not is_plugin_logical_name(logical) or not row:
            return False
        with self._plugin_schema_lock:
            known = logical in self._plugin_schemas
        if not known:
            return False
        phys = physical_from_logical(logical)
        if not phys:
            return False
        with self.db.suppress_write_notify():
            ok = self.db.upsert(phys, dict(row))
        if ok:
            self._broadcast_push_resolved(None, logical, "insert", dict(row))
        return bool(ok)

    def apply_plugin_delete(
        self, logical: str, where: str, params: Optional[List[Any]] = None
    ) -> bool:
        """同步中心本机插件删：落物理表并广播。"""
        if not is_plugin_logical_name(logical) or not where or ";" in str(where):
            return False
        with self._plugin_schema_lock:
            known = logical in self._plugin_schemas
        if not known:
            return False
        phys = physical_from_logical(logical)
        if not phys:
            return False
        params_t = tuple(params or ())
        with self.db.suppress_write_notify():
            ok = self.db.delete(phys, str(where), params_t)
        if ok:
            self._broadcast_push_resolved(
                None,
                logical,
                "delete",
                {"_where": str(where), "_params": list(params_t)},
            )
        return bool(ok)

    def _cleanup_dead_clients(self):
        """清理已断开的客户端"""
        disconnected = []
        
        with self._clients_lock:
            for client in self._clients:
                if not client.is_alive():
                    disconnected.append(client)
            
            for client in disconnected:
                self._clients.discard(client)
                try:
                    client.conn.close()
                except Exception:
                    pass
        
        if disconnected:
            self._log("info", f"Cleaned up {len(disconnected)} dead clients")

    def mirror_local_write(self, kind: str, table: str, **kwargs) -> None:
        """主机本地写库后广播给已连接的子服（库已改好，只推送）。"""
        if table not in self._sync_tables:
            return
        table_enum = TABLE_TO_ENUM.get(table)
        if table_enum is None:
            return
        try:
            for action in iter_mirror_write_actions(self.db, kind, table, **kwargs):
                if action[0] == "delete":
                    _, where, params = action
                    self._broadcast_push(
                        table_enum, "delete", {"_where": where, "_params": params}
                    )
                else:
                    self._broadcast_push(table_enum, "insert", action[1])
        except Exception as e:
            self._log("error", f"Mirror local write {table}/{kind} error: {e}")


    def get_connected_count(self) -> int:
        """获取已连接的客户端数量"""
        with self._clients_lock:
            return len([c for c in self._clients if c.authenticated])

    def get_client_list(self) -> List[Dict[str, str]]:
        """获取客户端列表"""
        with self._clients_lock:
            return [
                {
                    'server_id': c.server_id,
                    'server_name': c.server_name,
                    'addr': f"{c.addr[0]}:{c.addr[1]}",
                    'last_heartbeat': c.last_heartbeat,
                }
                for c in self._clients if c.authenticated
            ]