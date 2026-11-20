# -*- coding: utf-8 -*-
"""从命令 sender 反查"命令背后真正的玩家"。

背景（2026-11-19 服主报：`execute as @p run arc tp` 一点输出都没有）
--------------------------------------------------------------------------
Endstone 0.11.15 之前，转发过来的 sender 是 `ProxiedCommandSender`，它带
`callee`（= execute 的目标实体）和 `caller`，插件靠 `sender.name` 就能拿到
玩家名。上游 2025-06-22 把 `ProxiedCommandSender` 删了（commit f5e6c039），
转发过来的 sender 退化成基类 `CommandSender`：

* `name` 是**空串**——实测 `execute as @p run say x` 在服务器日志里显示成
  `[] x`，而控制台直连是 `[Server] x`；
* 没有 `is_player` / `xuid`；
* 也拿不到 BDS 的 origin 实体——`CommandOriginWrapper` 只暴露
  sendMessage / sendErrorMessage / getName / getPermissionLevel 四个方法。

所以身份**无法**从 sender 上恢复，只能退一步：线上**只有一个人类玩家**就代他
执行；多个真人无法猜，由调用方提示用户改用显式指定玩家的命令。

刻意**不 import endstone**：全部走鸭子类型，方便离线跑测试。
"""


def sender_name(sender) -> str:
    """sender 显示名（去掉颜色码）。

    返回空串 = 匿名 sender = execute 转发过来的。
    """
    name = str(getattr(sender, "name", "") or "").strip()
    if "§r" in name:
        name = name.rsplit("§r", 1)[-1]
    out = []
    index = 0
    while index < len(name):
        char = name[index]
        if char == "§" and index + 1 < len(name):
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out).strip()


def is_console_sender(sender, server) -> bool:
    """这个 sender 是不是服务器控制台本体。

    控制台 sender 是 `server.command_sender` 这一个**单例对象**；execute 转发
    过来的每次都新建一个包装对象——用对象同一性就能把两者分开。
    """
    try:
        console = getattr(server, "command_sender", None)
    except Exception:
        console = None
    return console is not None and sender is console


def human_players(server) -> list:
    """在线的**真人**玩家列表。

    判据是 xuid 非空——AI 假人（模拟玩家）没有 Xbox Live 客户端，xuid 必然是空的
    （弧光核心自己的 `is_ai_bot` 判据也是同一件事）。
    """
    humans = []
    for online_player in list(getattr(server, "online_players", []) or []):
        try:
            xuid = str(getattr(online_player, "xuid", "") or "").strip()
        except Exception:
            xuid = ""
        if xuid:
            humans.append(online_player)
    return humans


def sole_human_player(server):
    """线上**恰好一个**真人时返回他；0 个或多个都返回 None（多真人时无法猜）。"""
    humans = human_players(server)
    if len(humans) == 1:
        return humans[0]
    return None


def _dimension_id(location) -> str:
    """从 Location 拿维度 id（拿不到就当主世界）。"""
    dim = getattr(location, "dimension", None)
    if dim is None:
        return "overworld"
    for attr in ("id", "name"):
        val = getattr(dim, attr, None)
        if val:
            return str(val).strip()
    return str(dim).strip() or "overworld"


def nearest_human_to_block(server, sender):
    """命令方块 → 离方块最近的**真人**玩家。

    踏板 + 命令方块的经典玩法：命令方块里**直接写** `arc tp`，插件按"离方块最近的
    真人"执行——这就是 BDS `@p` 的意思，但只算真人（AI 假人没有客户端，抢到也
    看不见界面）。

    坐标拿得到：Endstone 的 `BlockCommandSender` 暴露了 `.block`，`Block` 又有
    `.location`（x/y/z/dimension）。
    """
    block = getattr(sender, "block", None)
    if block is None:
        return None
    loc = getattr(block, "location", None)
    if loc is None:
        return None
    try:
        block_x = float(loc.x)
        block_y = float(loc.y)
        block_z = float(loc.z)
    except Exception:
        return None
    block_dim = _dimension_id(loc)
    candidates = []
    for online_player in list(getattr(server, "online_players", []) or []):
        try:
            player_loc = getattr(online_player, "location", None)
            if player_loc is None:
                continue
            if _dimension_id(player_loc) != block_dim:
                continue
            distance = (
                (float(player_loc.x) - block_x) ** 2
                + (float(player_loc.y) - block_y) ** 2
                + (float(player_loc.z) - block_z) ** 2
            )
        except Exception:
            continue
        candidates.append((distance, online_player))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    for _distance, online_player in candidates:
        if str(getattr(online_player, "xuid", "") or "").strip():
            return online_player
    # 一个真人都没有：退而求其次给最近的假人
    return candidates[0][1]


def resolve_player_for_sender(sender, server, player_cls, resolve_by_name):
    """三段式解析"命令背后真正的玩家"。

    ① sender 就是 Player 本体 → 直接返回；
    ② 老版 Endstone 的 `ProxiedCommandSender` 带 `callee`（= execute 的目标实体）
       → 万一上游加回来还能用；
    ③ sender 有名字（命令方块 / 代理 / 控制台，名字是 "Server"）→ 按名字解析；
    ④ sender **匿名**（名字是空串 = execute 转发）→ 线上唯一真人就代他执行。

    `player_cls` 是用来做 isinstance 判断的 Player 类；`resolve_by_name` 是
    "按名字查在线玩家"的回调（返回 None 表示查不到）。
    """
    if isinstance(sender, player_cls):
        return sender
    callee = getattr(sender, "callee", None)
    if isinstance(callee, player_cls):
        return callee
    # 命令方块（踏板玩法）：按"离方块最近的真人"执行 = BDS @p 的意思。
    # 这里**直接返回**：命令方块附近没人就是没人，不许再掉到"唯一真人"兜底
    # ——否则会把界面开给一个离得老远的无关玩家。
    if getattr(sender, "block", None) is not None:
        return nearest_human_to_block(server, sender)
    name = sender_name(sender)
    if name:
        # 命令方块 / 代理 / 控制台：按名字解析，查不到就返回 None（保持旧行为）
        return resolve_by_name(name)
    if is_console_sender(sender, server):
        return None
    return sole_human_player(server)


def ambiguous_target_message(server) -> str:
    """多真人时的提示文案；不是多真人场景就返回空串。"""
    humans = human_players(server)
    if len(humans) > 1:
        return f"[ARC Core]无法确定目标玩家：当前有 {len(humans)} 个真人在线。"
    return ""
