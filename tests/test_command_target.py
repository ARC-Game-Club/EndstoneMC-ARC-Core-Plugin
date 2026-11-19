# -*- coding: utf-8 -*-
"""execute 转发拿不到玩家身份时，弧光核心怎么反查目标玩家。

背景（2026-11-19 服主报：`execute as @p run arc tp` 一点输出都没有）
--------------------------------------------------------------------------
Endstone 0.11.15 之前，转发过来的 sender 是 `ProxiedCommandSender`（带 callee /
caller），插件靠 `sender.name` 就能拿到玩家名。上游 2025-06-22 把它删了
（commit f5e6c039），转发过来的 sender 退化成基类 `CommandSender`：

* `name` 是**空串**——实测 `execute as @p run say x` 在服务器日志里是 `[] x`，
  而控制台直连是 `[Server] x`；
* 拿不到 BDS 的 origin 实体（`CommandOriginWrapper` 只暴露 4 个方法）。

所以身份**无法**从 sender 上恢复，只能退一步：线上唯一真人就代他执行。
这里把"怎么猜、什么时候不猜"钉死，别以后被改回去。
"""
import importlib.util
import sys
import unittest
from pathlib import Path

_MOD_PATH = (Path(__file__).resolve().parents[1]
             / "src" / "endstone_arc_core" / "command_target.py")
_spec = importlib.util.spec_from_file_location("command_target", _MOD_PATH)
assert _spec and _spec.loader
command_target = importlib.util.module_from_spec(_spec)
sys.modules["command_target"] = command_target
_spec.loader.exec_module(command_target)


class StubPlayer:
    def __init__(self, name, xuid=""):
        self.name = name
        self.xuid = xuid


class StubServer:
    def __init__(self, players, console=None):
        self.online_players = players
        self.command_sender = console


class AnonymousSender:
    """execute 转发过来的 sender：名字空串，没有 is_player / xuid。"""

    name = ""


class NamedSender:
    def __init__(self, name):
        self.name = name


def resolve(server, sender):
    def by_name(name):
        for p in server.online_players:
            if p.name.lower() == name.lower():
                return p
        return None

    return command_target.resolve_player_for_sender(
        sender, server, StubPlayer, by_name)


class CommandTargetTests(unittest.TestCase):
    def test_anonymous_sender_falls_back_to_the_only_human(self):
        """匿名 sender（execute 转发）+ 线上唯一真人 → 代他执行。"""
        human = StubPlayer("DEVILENMO", "2535408197449845")
        server = StubServer([human, StubPlayer("bot_a"), StubPlayer("bot_b")])
        self.assertIs(resolve(server, AnonymousSender()), human)

    def test_bots_are_not_humans(self):
        """假人 xuid 为空 → 不算真人（线上 7 假人 + 1 真人仍然命中那个真人）。"""
        bots = [StubPlayer(f"bot_{i}") for i in range(7)]
        human = StubPlayer("DEVILENMO", "2535408197449845")
        server = StubServer(bots + [human])
        self.assertIs(resolve(server, AnonymousSender()), human)

    def test_anonymous_sender_with_two_humans_is_ambiguous(self):
        """两个真人 → 猜不出来，返回 None（由调用方提示用户显式点名）。"""
        server = StubServer([StubPlayer("A", "1"), StubPlayer("B", "2")])
        self.assertIsNone(resolve(server, AnonymousSender()))

    def test_anonymous_sender_without_human_is_none(self):
        """没有真人在线 → None。"""
        server = StubServer([StubPlayer("bot_a")])
        self.assertIsNone(resolve(server, AnonymousSender()))

    def test_console_sender_is_not_treated_as_execute_forward(self):
        """控制台本体（server.command_sender 单例）→ 不走"唯一真人"兜底。"""
        human = StubPlayer("DEVILENMO", "2535")
        console = NamedSender("Server")
        server = StubServer([human], console=console)
        self.assertIsNone(resolve(server, console))

    def test_named_sender_resolves_by_name(self):
        """命令方块/代理：sender 有名字 → 按名字解析在线玩家。"""
        human = StubPlayer("DEVILENMO", "2535")
        server = StubServer([human])
        sender = NamedSender("§rDEVILENMO")
        self.assertIs(resolve(server, sender), human)

    def test_named_sender_without_match_is_none(self):
        """有名字但查不到人 → None（保持旧行为：提示只能由玩家使用）。"""
        server = StubServer([StubPlayer("DEVILENMO", "2535")])
        self.assertIsNone(resolve(server, NamedSender("Console")))

    def test_player_sender_returns_itself(self):
        """sender 本身就是 Player → 直接返回。"""
        human = StubPlayer("DEVILENMO", "2535")
        server = StubServer([human])
        self.assertIs(resolve(server, human), human)

    def test_callee_attribute_is_used_when_present(self):
        """老版 ProxiedCommandSender 的 callee（= execute 的目标实体）仍然认。"""
        human = StubPlayer("DEVILENMO", "2535")
        server = StubServer([human])
        sender = AnonymousSender()
        sender.callee = human
        self.assertIs(resolve(server, sender), human)

    def test_sender_name_strips_format_codes(self):
        # 名字牌形如 "§a[VIP]§rSteve"：取最后一个 §r 之后的部分
        self.assertEqual(command_target.sender_name(NamedSender("§rDEVILENMO")), "DEVILENMO")
        self.assertEqual(command_target.sender_name(NamedSender("§a[VIP]§rSteve")), "Steve")
        self.assertEqual(command_target.sender_name(NamedSender("§aSteve")), "Steve")
        self.assertEqual(command_target.sender_name(AnonymousSender()), "")

    def test_ambiguous_message_only_when_multiple_humans(self):
        server = StubServer([StubPlayer("A", "1"), StubPlayer("B", "2")])
        self.assertIn("无法确定目标玩家", command_target.ambiguous_target_message(server))
        one = StubServer([StubPlayer("A", "1")])
        self.assertEqual(command_target.ambiguous_target_message(one), "")


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(CommandTargetTests))
    if result.wasSuccessful():
        print(f"全部 {result.testsRun} 项通过")
    raise SystemExit(0 if result.wasSuccessful() else 1)
