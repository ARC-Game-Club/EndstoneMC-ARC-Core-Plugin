# -*- coding: utf-8 -*-
"""玩家数据同步审计（同步中心侧）。

两件事：
1. 完整日志：哪个服进了谁、走了谁、总时长/次数怎么变、谁查了谁，
   追加写入 plugins/ARCCore/player_sync_log.txt（与 error_log.txt 同目录）。
2. 数值回退防护：total_playtime / session_count 在中心侧只增不减，
   从服拿旧缓存整行覆盖时按原值保留，杜绝"所有人数据不停消失"。

行格式示例：
[2026-09-19 00:57:33] [进服] 从服<弧光无规则生存服务器> featherWinded(2535468140536592) 次数 10→11 | 总时长 6045s→6045s | 进服时间 2026-09-19T00:57:33
[2026-09-19 00:59:21] [退服] 从服<弧光无规则生存服务器> featherWinded(2535468140536592) 总时长 6045s→6148s(本次 +103s) | 退服时间 2026-09-19T00:59:21
[2026-09-19 00:57:33] [拦截回退] 从服<弧光xxx> featherWinded(...) 总时长 6045→103 | 次数 10→1 → 均按原值保留
"""
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_file_lock = threading.Lock()

# 计数类字段：中心为权威值，只允许增长，不允许被从服旧缓存回退覆盖
MONOTONIC_INT_FIELDS = ("total_playtime", "session_count")


def append_player_sync_log(log_file_path: str, line: str) -> None:
    """线程安全追加一行审计记录（自动加时间戳）；失败静默，不影响同步链路。"""
    if not log_file_path:
        return
    timestamp = datetime.now().isoformat(sep=" ", timespec="seconds")
    text = f"[{timestamp}] {line}\n"
    with _file_lock:
        try:
            path_obj = Path(log_file_path)
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            with path_obj.open("a", encoding="utf-8") as log_file:
                log_file.write(text)
        except Exception:
            pass


def as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def player_label(row: Optional[Dict[str, Any]]) -> str:
    """行/数据里取 玩家名(xuid) 展示串。"""
    src = row or {}
    name = str(src.get("name") or "").strip() or "?"
    xuid = str(src.get("xuid") or "").strip() or "?"
    return f"{name}({xuid})"


def extract_xuid_from_request(data: Dict[str, Any]) -> str:
    """从 INSERT/UPDATE 请求提取 xuid：整行取 data.xuid，条件更新取 params。"""
    row_data = data.get("data") or {}
    xuid = str(row_data.get("xuid") or "").strip()
    if xuid:
        return xuid
    where = str(data.get("where") or "").strip().lower()
    params = list(data.get("params") or [])
    if where.startswith("xuid") and params:
        return str(params[0]).strip()
    return ""


def classify_basic_info_event(
    old_row: Optional[Dict[str, Any]], new_data: Dict[str, Any]
) -> str:
    """按旧值对比判定业务事件：进服 / 退服 / 新建档 / 资料 / 无变化。

    只有次数或进退服时间相对中心旧值真的变化了才算进/退服；
    与旧值完全一致的整行上行（对账重放）返回「无变化」，由中心侧合并降噪。
    """
    new_data = new_data or {}
    if old_row is None:
        if "last_join_time" in new_data:
            return "进服"
        if "last_quit_time" in new_data or "total_playtime" in new_data:
            return "退服"
        return "新建档"
    join_changed = (
        "last_join_time" in new_data
        and new_data.get("last_join_time") != old_row.get("last_join_time")
    )
    count_up = "session_count" in new_data and as_int(
        new_data.get("session_count")
    ) > as_int(old_row.get("session_count"))
    if join_changed or count_up:
        return "进服"
    quit_changed = (
        "last_quit_time" in new_data
        and new_data.get("last_quit_time") != old_row.get("last_quit_time")
    )
    playtime_up = "total_playtime" in new_data and as_int(
        new_data.get("total_playtime")
    ) > as_int(old_row.get("total_playtime"))
    if quit_changed or playtime_up:
        return "退服"
    for key, value in new_data.items():
        if old_row.get(key) != value:
            return "资料"
    return "无变化"


def guard_basic_info_counters(
    old_row: Optional[Dict[str, Any]], new_data: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[str]]:
    """拦截计数回退：total_playtime / session_count 只增不减。

    返回 (最终写入数据, 被拦截项的描述列表)。old_row 为 None（新玩家建档）不拦截。
    """
    final = dict(new_data or {})
    blocked: List[str] = []
    if not old_row:
        return final, blocked
    for field in MONOTONIC_INT_FIELDS:
        if field not in final:
            continue
        old_value = as_int(old_row.get(field))
        new_value = as_int(final.get(field))
        if new_value < old_value:
            blocked.append(f"{field} {old_value}→{new_value}")
            final[field] = old_value
    return final, blocked


def format_counter_changes(
    old_row: Optional[Dict[str, Any]], final_data: Dict[str, Any]
) -> str:
    """生成 次数 old→new | 总时长 old→new(本次 +Xs) | 进退服时间 摘要。"""
    src = old_row or {}
    parts: List[str] = []
    if "session_count" in final_data:
        parts.append(
            f"次数 {as_int(src.get('session_count'))}→{as_int(final_data.get('session_count'))}"
        )
    if "total_playtime" in final_data:
        old_pt = as_int(src.get("total_playtime"))
        new_pt = as_int(final_data.get("total_playtime"))
        delta = new_pt - old_pt
        delta_note = f"(本次 +{delta}s)" if delta > 0 else ""
        parts.append(f"总时长 {old_pt}s→{new_pt}s{delta_note}")
    if "last_join_time" in final_data:
        parts.append(f"进服时间 {final_data.get('last_join_time')}")
    if "last_quit_time" in final_data:
        parts.append(f"退服时间 {final_data.get('last_quit_time')}")
    if "name" in final_data:
        parts.append(f"名称→{final_data.get('name')}")
    return " | ".join(parts)


def summarize_basic_info_row(row: Optional[Dict[str, Any]]) -> str:
    """查询结果摘要：玩家名(xuid) 次数 N 总时长 Ns。"""
    if not row:
        return "(无记录)"
    src = dict(row)
    return (
        f"{player_label(src)} 次数 {as_int(src.get('session_count'))}"
        f" 总时长 {as_int(src.get('total_playtime'))}s"
    )
