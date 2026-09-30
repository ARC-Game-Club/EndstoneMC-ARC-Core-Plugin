# -*- coding: utf-8 -*-
"""新手书 UI：玩家侧书式阅读（封面简介 → 板块 → 章节）+ OP 游戏内编辑。

玩家侧：
  封面 = 书标题 + 简介正文 + 各板块按钮；板块页 = 板块介绍 + 章节按钮；
  章节页 = 章节正文 + 上一章/下一章。全部表单化，无聊天刷屏。

OP 侧（OP 面板·新手书编辑）：
  简介编辑、板块/章节的增删改、上下移、整书重置、玩家视角预览；
  每次修改立即写盘 newbie_book.json 并即时生效，无需重载或重启。
"""
import json
from typing import Callable, Optional

from endstone import Player
from endstone.form import ActionForm, ModalForm, TextInput

from endstone_arc_core import ui_icons
from endstone_arc_core.newbie_book import (
    MAX_SECTION_NAME_LEN,
    MAX_TITLE_LEN,
    normalize_multiline_text,
    normalize_single_line,
)

# 语言键 → 缺省兜底文案（语言文件缺键时 UI 仍可用）
_TEXTS = {
    "NEWBIE_BOOK_ENTRY": "新手书编辑",
    "NEWBIE_BOOK_PREVIEW": "预览玩家视角",
    "NEWBIE_BOOK_EDIT_INTRO": "编辑封面简介",
    "NEWBIE_BOOK_INTRO_TITLE_LABEL": "简介小标题",
    "NEWBIE_BOOK_SECTIONS_MANAGE": "板块管理",
    "NEWBIE_BOOK_ADD_SECTION": "新建板块",
    "NEWBIE_BOOK_ADD_CHAPTER": "新建章节",
    "NEWBIE_BOOK_CHAPTERS_MANAGE": "章节管理",
    "NEWBIE_BOOK_RENAME": "改名",
    "NEWBIE_BOOK_EDIT_SECTION_INTRO": "编辑板块介绍",
    "NEWBIE_BOOK_EDIT_CHAPTER_TITLE": "编辑章节标题",
    "NEWBIE_BOOK_EDIT_CONTENT": "编辑内容",
    "NEWBIE_BOOK_MOVE_UP": "上移",
    "NEWBIE_BOOK_MOVE_DOWN": "下移",
    "NEWBIE_BOOK_DELETE": "删除",
    "NEWBIE_BOOK_CONFIRM_DELETE": "确认删除",
    "NEWBIE_BOOK_RESET": "重置为默认模板",
    "NEWBIE_BOOK_RESET_CONFIRM": "确认重置",
    "NEWBIE_BOOK_RESET_DONE": "已重置为默认模板。",
    "NEWBIE_BOOK_PREV_CHAPTER": "上一章",
    "NEWBIE_BOOK_NEXT_CHAPTER": "下一章",
    "NEWBIE_BOOK_PREV_PAGE": "上一页",
    "NEWBIE_BOOK_NEXT_PAGE": "下一页",
    "NEWBIE_BOOK_SAVED": "§a[新手书] §f已保存并即时生效",
    "NEWBIE_BOOK_INVALID_INPUT": "§c[新手书] §f输入无效（名称/标题不能为空），已取消",
    "NEWBIE_BOOK_EMPTY_NOTE": "（这里还没有内容，请 OP 在 OP 面板·新手书编辑 中配置）",
    "NEWBIE_BOOK_COVER_EMPTY": "（简介暂未配置）",
    "NEWBIE_BOOK_NO_SECTION": "（暂无板块）",
    "NEWBIE_BOOK_NO_CHAPTER": "（本板块暂无章节）",
    "NEWBIE_BOOK_DELETE_CONFIRM_CONTENT": "确定要删除「{0}」吗？此操作不可撤销。",
    "NEWBIE_BOOK_RESET_CONFIRM_CONTENT": "确定要重置整本新手书吗？\n当前所有板块与章节将被默认模板覆盖（含旧版教学迁移）！",
    "NEWBIE_BOOK_CONTENT_LABEL": "正文（用字面 \\n 表示换行）",
    "NEWBIE_BOOK_JOIN_HINT": "§e[欢迎] §f新玩家你好！已为你打开《新手手册》，可点「返回」进入主菜单；之后随时在 §b/arc§r 里点 §a新手引导§r 回看。",
    "NEWBIE_BOOK_COVER_HINT": "点下方按钮进入各板块 ↓",
    "NEWBIE_BOOK_SECTION_HINT": "点下方按钮阅读各章节 ↓",
    "NEWBIE_BOOK_CHAPTER_OF": "{0}/{1}",
}


class _BookUiBase:
    PAGE_SIZE = 8

    def __init__(self, plugin):
        self.plugin = plugin

    def _text(self, key: str) -> str:
        fallback = _TEXTS.get(key, "")
        try:
            value = self.plugin.language_manager.GetText(key)
        except Exception:
            value = ""
        return value or fallback

    def _icon(self, icon) -> Optional[str]:
        return self.plugin._ui_icon(icon)

    def _page_prev_next(self, panel, page: int, total_pages: int, on_page: Callable[[Player, int], None]) -> None:
        if page > 0:
            panel.add_button(
                self._text("NEWBIE_BOOK_PREV_PAGE") or "上一页",
                on_click=lambda p, pg=page: on_page(p, pg - 1),
            )
        if page < total_pages - 1:
            panel.add_button(
                self._text("NEWBIE_BOOK_NEXT_PAGE") or "下一页",
                on_click=lambda p, pg=page: on_page(p, pg + 1),
            )


class NewbieBookUi(_BookUiBase):
    """玩家侧阅读 UI。所有跳转用参数传索引，不保存每玩家状态。"""

    def show_cover(self, player: Player, on_back: Optional[Callable] = None) -> None:
        book = self.plugin.newbie_book.get_book()
        intro = str(book.get("intro") or "").strip()
        sections = book.get("sections") or []
        content = intro or self._text("NEWBIE_BOOK_COVER_EMPTY")
        if sections:
            content += "\n\n" + self._text("NEWBIE_BOOK_COVER_HINT")
        else:
            note = self._text("NEWBIE_BOOK_EMPTY_NOTE")
            if note and note not in content:
                content += "\n\n" + note
        cover = ActionForm(
            title=str(book.get("title") or "新手手册"),
            content=content,
            on_close=None,
        )
        for idx, section in enumerate(sections):
            name = str(section.get("name") or "").strip() or f"板块{idx + 1}"
            chapters = section.get("chapters") or []
            label = f"{name}（{len(chapters)}章）" if chapters else name
            cover.add_button(
                label,
                icon=self._icon(ui_icons.NEWBIE),
                on_click=lambda p, i=idx: self.show_section(p, i, 0),
            )
        back = on_back or self.plugin.show_main_menu
        cover.add_button(
            self.plugin.language_manager.GetText("RETURN_BUTTON_TEXT"),
            icon=self._icon(ui_icons.BACK),
            on_click=lambda p: back(p),
        )
        player.send_form(cover)

    def show_section(self, player: Player, section_index: int, page: int = 0) -> None:
        book = self.plugin.newbie_book.get_book()
        sections = book.get("sections") or []
        if section_index < 0 or section_index >= len(sections):
            return self.show_cover(player)
        section = sections[section_index]
        chapters = section.get("chapters") or []
        intro = str(section.get("intro") or "").strip()
        content = intro or self._text("NEWBIE_BOOK_EMPTY_NOTE")
        if chapters:
            content += "\n\n" + self._text("NEWBIE_BOOK_SECTION_HINT")
        else:
            content += "\n" + self._text("NEWBIE_BOOK_NO_CHAPTER")
        name = str(section.get("name") or "").strip() or f"板块{section_index + 1}"
        panel = ActionForm(title=name, content=content, on_close=None)
        total_pages = max(1, (len(chapters) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        start = page * self.PAGE_SIZE
        for idx in range(start, min(start + self.PAGE_SIZE, len(chapters))):
            title = str(chapters[idx].get("title") or "").strip() or f"章节{idx + 1}"
            panel.add_button(
                title,
                on_click=lambda p, si=section_index, ci=idx: self.show_chapter(p, si, ci, 0),
            )
        self._page_prev_next(
            panel, page, total_pages,
            lambda p, pg: self.show_section(p, section_index, pg),
        )
        panel.add_button(
            self.plugin.language_manager.GetText("RETURN_BUTTON_TEXT"),
            icon=self._icon(ui_icons.BACK),
            on_click=lambda p: self.show_cover(p),
        )
        player.send_form(panel)

    def show_chapter(
        self,
        player: Player,
        section_index: int,
        chapter_index: int,
        section_page: int = 0,
    ) -> None:
        book = self.plugin.newbie_book.get_book()
        sections = book.get("sections") or []
        if section_index < 0 or section_index >= len(sections):
            return self.show_cover(player)
        section = sections[section_index]
        chapters = section.get("chapters") or []
        if chapter_index < 0 or chapter_index >= len(chapters):
            return self.show_section(player, section_index, section_page)
        chapter = chapters[chapter_index]
        content = str(chapter.get("content") or "").strip() or self._text("NEWBIE_BOOK_EMPTY_NOTE")
        panel = ActionForm(
            title=str(chapter.get("title") or f"章节{chapter_index + 1}"),
            content=content,
            on_close=None,
        )
        if chapter_index > 0:
            panel.add_button(
                self._text("NEWBIE_BOOK_PREV_CHAPTER"),
                on_click=lambda p, ci=chapter_index - 1: self.show_chapter(p, section_index, ci, section_page),
            )
        if chapter_index < len(chapters) - 1:
            panel.add_button(
                self._text("NEWBIE_BOOK_NEXT_CHAPTER"),
                on_click=lambda p, ci=chapter_index + 1: self.show_chapter(p, section_index, ci, section_page),
            )
        panel.add_button(
            self.plugin.language_manager.GetText("RETURN_BUTTON_TEXT"),
            icon=self._icon(ui_icons.BACK),
            on_click=lambda p: self.show_section(p, section_index, section_page),
        )
        player.send_form(panel)


class NewbieBookOpUi(_BookUiBase):
    """OP 编辑 UI：所有修改即时落盘生效。"""

    def _saved(self, player: Player) -> None:
        try:
            self.plugin.newbie_book.save()
        except Exception:
            pass
        player.send_message(self._text("NEWBIE_BOOK_SAVED"))

    # ---- 入口 ----

    def show_menu(self, player: Player) -> None:
        book = self.plugin.newbie_book.get_book()
        sections = book.get("sections") or []
        chapter_count = sum(len(s.get("chapters") or []) for s in sections)
        panel = ActionForm(
            title=self._text("NEWBIE_BOOK_ENTRY"),
            content=(
                f"{book.get('title') or '新手手册'}｜{len(sections)} 个板块 / {chapter_count} 个章节\n"
                "修改即时保存生效；玩家视角见主菜单「新手引导」。"
            ),
            on_close=None,
        )
        panel.add_button(
            self._text("NEWBIE_BOOK_PREVIEW"),
            icon=self._icon(ui_icons.NEWBIE),
            on_click=self.show_preview,
        )
        panel.add_button(
            self._text("NEWBIE_BOOK_EDIT_INTRO"),
            on_click=self.show_intro_edit,
        )
        panel.add_button(
            self._text("NEWBIE_BOOK_SECTIONS_MANAGE"),
            on_click=lambda p: self.show_sections(p, 0),
        )
        panel.add_button(
            self._text("NEWBIE_BOOK_RESET"),
            on_click=self.show_reset_confirm,
        )
        panel.add_button(
            self.plugin.language_manager.GetText("RETURN_BUTTON_TEXT"),
            icon=self._icon(ui_icons.BACK),
            on_click=self.plugin.show_op_main_panel,
        )
        player.send_form(panel)

    def show_preview(self, player: Player) -> None:
        self.plugin._newbie_book_ui().show_cover(player)

    # ---- 封面简介 ----

    def show_intro_edit(self, player: Player) -> None:
        book = self.plugin.newbie_book.get_book()
        title_input = TextInput(
            label="书名（封面标题）",
            placeholder="新手手册",
            default_value=str(book.get("title") or ""),
        )

        def on_submit_title(p: Player, json_str: str) -> None:
            if self._is_back(p, json_str):
                return self.show_menu(p)
            data = self._parse(p, json_str)
            if data is None:
                return self.show_menu(p)
            title = normalize_single_line(str(data[1] or ""), MAX_TITLE_LEN)
            if not title:
                p.send_message(self._text("NEWBIE_BOOK_INVALID_INPUT"))
                return self.show_intro_edit(p)
            book["title"] = title
            self._saved(p)
            self._edit_intro_content(p)

        form = ModalForm(
            title="编辑书名",
            controls=[self.plugin._modal_nav_dropdown(), title_input],
            on_close=None,
            on_submit=on_submit_title,
        )
        player.send_form(form)

    def _edit_intro_content(self, player: Player) -> None:
        book = self.plugin.newbie_book.get_book()
        intro_input = TextInput(
            label=self._text("NEWBIE_BOOK_CONTENT_LABEL"),
            placeholder="欢迎来到本服务器！\\n祝你玩得愉快！",
            default_value=str(book.get("intro") or "").replace("\n", "\\n"),
        )

        def on_submit(p: Player, json_str: str) -> None:
            if self._is_back(p, json_str):
                return self.show_intro_edit(p)
            data = self._parse(p, json_str)
            if data is None:
                return self.show_intro_edit(p)
            book["intro"] = normalize_multiline_text(str(data[1] or ""))
            self._saved(p)
            self.show_menu(p)

        form = ModalForm(
            title="编辑封面简介",
            controls=[self.plugin._modal_nav_dropdown(), intro_input],
            on_close=None,
            on_submit=on_submit,
        )
        player.send_form(form)

    # ---- 板块 ----

    def show_sections(self, player: Player, page: int = 0) -> None:
        sections = self.plugin.newbie_book.get_book().get("sections") or []
        total_pages = max(1, (len(sections) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        start = page * self.PAGE_SIZE
        panel = ActionForm(
            title=self._text("NEWBIE_BOOK_SECTIONS_MANAGE"),
            content=f"共 {len(sections)} 个板块（第 {page + 1}/{total_pages} 页）",
            on_close=None,
        )
        panel.add_button(
            self._text("NEWBIE_BOOK_ADD_SECTION"),
            on_click=self.show_section_add,
        )
        for idx in range(start, min(start + self.PAGE_SIZE, len(sections))):
            section = sections[idx]
            name = str(section.get("name") or "").strip() or f"板块{idx + 1}"
            chapters = section.get("chapters") or []
            panel.add_button(
                f"{name}（{len(chapters)}章）",
                on_click=lambda p, i=idx: self.show_section_menu(p, i),
            )
        self._page_prev_next(
            panel, page, total_pages,
            lambda p, pg: self.show_sections(p, pg),
        )
        panel.add_button(
            self.plugin.language_manager.GetText("RETURN_BUTTON_TEXT"),
            icon=self._icon(ui_icons.BACK),
            on_click=self.show_menu,
        )
        player.send_form(panel)

    def show_section_menu(self, player: Player, section_index: int) -> None:
        section = self.plugin.newbie_book.get_section(section_index)
        if section is None:
            return self.show_sections(player, 0)
        name = str(section.get("name") or "").strip() or f"板块{section_index + 1}"
        chapters = section.get("chapters") or []
        sections = self.plugin.newbie_book.get_book().get("sections") or []
        panel = ActionForm(
            title=name,
            content=f"共 {len(chapters)} 个章节\n板块介绍：\n{section.get('intro') or '（空）'}",
            on_close=None,
        )
        panel.add_button(
            self._text("NEWBIE_BOOK_CHAPTERS_MANAGE"),
            on_click=lambda p: self.show_chapters(p, section_index, 0),
        )
        panel.add_button(self._text("NEWBIE_BOOK_RENAME"), on_click=lambda p: self.show_section_rename(p, section_index))
        panel.add_button(
            self._text("NEWBIE_BOOK_EDIT_SECTION_INTRO"),
            on_click=lambda p: self.show_section_intro_edit(p, section_index),
        )
        if section_index > 0:
            panel.add_button(
                self._text("NEWBIE_BOOK_MOVE_UP"),
                on_click=lambda p: self._move_section(p, section_index, -1),
            )
        if section_index < len(sections) - 1:
            panel.add_button(
                self._text("NEWBIE_BOOK_MOVE_DOWN"),
                on_click=lambda p: self._move_section(p, section_index, 1),
            )
        panel.add_button(
            self._text("NEWBIE_BOOK_DELETE"),
            on_click=lambda p: self.show_section_delete_confirm(p, section_index),
        )
        panel.add_button(
            self.plugin.language_manager.GetText("RETURN_BUTTON_TEXT"),
            icon=self._icon(ui_icons.BACK),
            on_click=lambda p: self.show_sections(p, 0),
        )
        player.send_form(panel)

    def _move_section(self, player: Player, section_index: int, delta: int) -> None:
        sections = self.plugin.newbie_book.get_book().get("sections") or []
        target = section_index + delta
        if 0 <= target < len(sections):
            sections[section_index], sections[target] = sections[target], sections[section_index]
            self._saved(player)
        self.show_sections(player, 0)

    def show_section_delete_confirm(self, player: Player, section_index: int) -> None:
        section = self.plugin.newbie_book.get_section(section_index)
        if section is None:
            return self.show_sections(player, 0)
        name = str(section.get("name") or "").strip() or f"板块{section_index + 1}"
        panel = ActionForm(
            title=self._text("NEWBIE_BOOK_CONFIRM_DELETE"),
            content=self._text("NEWBIE_BOOK_DELETE_CONFIRM_CONTENT").format(name),
            on_close=None,
        )
        panel.add_button(
            self._text("NEWBIE_BOOK_CONFIRM_DELETE"),
            on_click=lambda p: self._delete_section(p, section_index),
        )
        panel.add_button(
            self.plugin.language_manager.GetText("RETURN_BUTTON_TEXT"),
            icon=self._icon(ui_icons.BACK),
            on_click=lambda p: self.show_section_menu(p, section_index),
        )
        player.send_form(panel)

    def _delete_section(self, player: Player, section_index: int) -> None:
        book = self.plugin.newbie_book.get_book()
        sections = book.get("sections") or []
        if 0 <= section_index < len(sections):
            del sections[section_index]
            self._saved(player)
        self.show_sections(player, 0)

    def show_section_rename(self, player: Player, section_index: int) -> None:
        section = self.plugin.newbie_book.get_section(section_index)
        if section is None:
            return self.show_sections(player, 0)
        name_input = TextInput(
            label="板块名称（显示为封面按钮）",
            placeholder="插件",
            default_value=str(section.get("name") or ""),
        )

        def on_submit(p: Player, json_str: str) -> None:
            if self._is_back(p, json_str):
                return self.show_section_menu(p, section_index)
            data = self._parse(p, json_str)
            if data is None:
                return self.show_section_menu(p, section_index)
            name = normalize_single_line(str(data[1] or ""), MAX_SECTION_NAME_LEN)
            if not name:
                p.send_message(self._text("NEWBIE_BOOK_INVALID_INPUT"))
                return self.show_section_menu(p, section_index)
            section["name"] = name
            self._saved(p)
            self.show_section_menu(p, section_index)

        form = ModalForm(
            title="板块改名",
            controls=[self.plugin._modal_nav_dropdown(), name_input],
            on_close=None,
            on_submit=on_submit,
        )
        player.send_form(form)

    def show_section_intro_edit(self, player: Player, section_index: int) -> None:
        section = self.plugin.newbie_book.get_section(section_index)
        if section is None:
            return self.show_sections(player, 0)
        intro_input = TextInput(
            label=self._text("NEWBIE_BOOK_CONTENT_LABEL"),
            placeholder="本板块逐个介绍……\\n（点下方按钮阅读各章节）",
            default_value=str(section.get("intro") or "").replace("\n", "\\n"),
        )

        def on_submit(p: Player, json_str: str) -> None:
            if self._is_back(p, json_str):
                return self.show_section_menu(p, section_index)
            data = self._parse(p, json_str)
            if data is None:
                return self.show_section_menu(p, section_index)
            section["intro"] = normalize_multiline_text(str(data[1] or ""))
            self._saved(p)
            self.show_section_menu(p, section_index)

        form = ModalForm(
            title="编辑板块介绍",
            controls=[self.plugin._modal_nav_dropdown(), intro_input],
            on_close=None,
            on_submit=on_submit,
        )
        player.send_form(form)

    def show_section_add(self, player: Player) -> None:
        name_input = TextInput(
            label="新板块名称",
            placeholder="插件 / 模组 / 玩法规则 ……",
            default_value="",
        )

        def on_submit(p: Player, json_str: str) -> None:
            if self._is_back(p, json_str):
                return self.show_sections(p, 0)
            data = self._parse(p, json_str)
            if data is None:
                return self.show_sections(p, 0)
            name = normalize_single_line(str(data[1] or ""), MAX_SECTION_NAME_LEN)
            if not name:
                p.send_message(self._text("NEWBIE_BOOK_INVALID_INPUT"))
                return self.show_sections(p, 0)
            book = self.plugin.newbie_book.get_book()
            book.setdefault("sections", []).append({"name": name, "intro": "", "chapters": []})
            self._saved(p)
            self.show_sections(p, 0)

        form = ModalForm(
            title=self._text("NEWBIE_BOOK_ADD_SECTION"),
            controls=[self.plugin._modal_nav_dropdown(), name_input],
            on_close=None,
            on_submit=on_submit,
        )
        player.send_form(form)

    # ---- 章节 ----

    def show_chapters(self, player: Player, section_index: int, page: int = 0) -> None:
        section = self.plugin.newbie_book.get_section(section_index)
        if section is None:
            return self.show_sections(player, 0)
        chapters = section.get("chapters") or []
        total_pages = max(1, (len(chapters) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        start = page * self.PAGE_SIZE
        name = str(section.get("name") or "").strip() or f"板块{section_index + 1}"
        panel = ActionForm(
            title=f"{name}·{self._text('NEWBIE_BOOK_CHAPTERS_MANAGE')}",
            content=f"共 {len(chapters)} 个章节（第 {page + 1}/{total_pages} 页）",
            on_close=None,
        )
        panel.add_button(
            self._text("NEWBIE_BOOK_ADD_CHAPTER"),
            on_click=lambda p: self.show_chapter_add(p, section_index),
        )
        for idx in range(start, min(start + self.PAGE_SIZE, len(chapters))):
            title = str(chapters[idx].get("title") or "").strip() or f"章节{idx + 1}"
            panel.add_button(
                f"{idx + 1}. {title}",
                on_click=lambda p, ci=idx: self.show_chapter_menu(p, section_index, ci),
            )
        self._page_prev_next(
            panel, page, total_pages,
            lambda p, pg: self.show_chapters(p, section_index, pg),
        )
        panel.add_button(
            self.plugin.language_manager.GetText("RETURN_BUTTON_TEXT"),
            icon=self._icon(ui_icons.BACK),
            on_click=lambda p: self.show_section_menu(p, section_index),
        )
        player.send_form(panel)

    def show_chapter_menu(self, player: Player, section_index: int, chapter_index: int) -> None:
        section = self.plugin.newbie_book.get_section(section_index)
        chapter = self.plugin.newbie_book.get_chapter(section_index, chapter_index)
        if section is None or chapter is None:
            return self.show_chapters(player, section_index, 0)
        title = str(chapter.get("title") or "").strip() or f"章节{chapter_index + 1}"
        chapters = section.get("chapters") or []
        panel = ActionForm(
            title=title,
            content=(chapter.get("content") or "（空）")[:200],
            on_close=None,
        )
        panel.add_button(
            self._text("NEWBIE_BOOK_EDIT_CHAPTER_TITLE"),
            on_click=lambda p: self.show_chapter_title_edit(p, section_index, chapter_index),
        )
        panel.add_button(
            self._text("NEWBIE_BOOK_EDIT_CONTENT"),
            on_click=lambda p: self.show_chapter_content_edit(p, section_index, chapter_index),
        )
        if chapter_index > 0:
            panel.add_button(
                self._text("NEWBIE_BOOK_MOVE_UP"),
                on_click=lambda p: self._move_chapter(p, section_index, chapter_index, -1),
            )
        if chapter_index < len(chapters) - 1:
            panel.add_button(
                self._text("NEWBIE_BOOK_MOVE_DOWN"),
                on_click=lambda p: self._move_chapter(p, section_index, chapter_index, 1),
            )
        panel.add_button(
            self._text("NEWBIE_BOOK_DELETE"),
            on_click=lambda p: self.show_chapter_delete_confirm(p, section_index, chapter_index),
        )
        panel.add_button(
            self.plugin.language_manager.GetText("RETURN_BUTTON_TEXT"),
            icon=self._icon(ui_icons.BACK),
            on_click=lambda p: self.show_chapters(p, section_index, 0),
        )
        player.send_form(panel)

    def _move_chapter(self, player: Player, section_index: int, chapter_index: int, delta: int) -> None:
        section = self.plugin.newbie_book.get_section(section_index)
        if section is None:
            return self.show_chapters(player, section_index, 0)
        chapters = section.get("chapters") or []
        target = chapter_index + delta
        if 0 <= target < len(chapters):
            chapters[chapter_index], chapters[target] = chapters[target], chapters[chapter_index]
            self._saved(player)
        self.show_chapters(player, section_index, 0)

    def show_chapter_delete_confirm(self, player: Player, section_index: int, chapter_index: int) -> None:
        chapter = self.plugin.newbie_book.get_chapter(section_index, chapter_index)
        if chapter is None:
            return self.show_chapters(player, section_index, 0)
        title = str(chapter.get("title") or "").strip() or f"章节{chapter_index + 1}"
        panel = ActionForm(
            title=self._text("NEWBIE_BOOK_CONFIRM_DELETE"),
            content=self._text("NEWBIE_BOOK_DELETE_CONFIRM_CONTENT").format(title),
            on_close=None,
        )
        panel.add_button(
            self._text("NEWBIE_BOOK_CONFIRM_DELETE"),
            on_click=lambda p: self._delete_chapter(p, section_index, chapter_index),
        )
        panel.add_button(
            self.plugin.language_manager.GetText("RETURN_BUTTON_TEXT"),
            icon=self._icon(ui_icons.BACK),
            on_click=lambda p: self.show_chapter_menu(p, section_index, chapter_index),
        )
        player.send_form(panel)

    def _delete_chapter(self, player: Player, section_index: int, chapter_index: int) -> None:
        section = self.plugin.newbie_book.get_section(section_index)
        if section is None:
            return self.show_chapters(player, section_index, 0)
        chapters = section.get("chapters") or []
        if 0 <= chapter_index < len(chapters):
            del chapters[chapter_index]
            self._saved(player)
        self.show_chapters(player, section_index, 0)

    def show_chapter_title_edit(self, player: Player, section_index: int, chapter_index: int) -> None:
        chapter = self.plugin.newbie_book.get_chapter(section_index, chapter_index)
        if chapter is None:
            return self.show_chapters(player, section_index, 0)
        title_input = TextInput(
            label="章节标题（显示为章节按钮/页面标题）",
            placeholder="每日签到",
            default_value=str(chapter.get("title") or ""),
        )

        def on_submit(p: Player, json_str: str) -> None:
            if self._is_back(p, json_str):
                return self.show_chapter_menu(p, section_index, chapter_index)
            data = self._parse(p, json_str)
            if data is None:
                return self.show_chapter_menu(p, section_index, chapter_index)
            title = normalize_single_line(str(data[1] or ""), MAX_TITLE_LEN)
            if not title:
                p.send_message(self._text("NEWBIE_BOOK_INVALID_INPUT"))
                return self.show_chapter_menu(p, section_index, chapter_index)
            chapter["title"] = title
            self._saved(p)
            self.show_chapter_menu(p, section_index, chapter_index)

        form = ModalForm(
            title=self._text("NEWBIE_BOOK_EDIT_CHAPTER_TITLE"),
            controls=[self.plugin._modal_nav_dropdown(), title_input],
            on_close=None,
            on_submit=on_submit,
        )
        player.send_form(form)

    def show_chapter_content_edit(self, player: Player, section_index: int, chapter_index: int) -> None:
        chapter = self.plugin.newbie_book.get_chapter(section_index, chapter_index)
        if chapter is None:
            return self.show_chapters(player, section_index, 0)
        content_input = TextInput(
            label=self._text("NEWBIE_BOOK_CONTENT_LABEL"),
            placeholder="第一行内容\\n第二行内容",
            default_value=str(chapter.get("content") or "").replace("\n", "\\n"),
        )

        def on_submit(p: Player, json_str: str) -> None:
            if self._is_back(p, json_str):
                return self.show_chapter_menu(p, section_index, chapter_index)
            data = self._parse(p, json_str)
            if data is None:
                return self.show_chapter_menu(p, section_index, chapter_index)
            chapter["content"] = normalize_multiline_text(str(data[1] or ""))
            self._saved(p)
            self.show_chapter_menu(p, section_index, chapter_index)

        form = ModalForm(
            title=self._text("NEWBIE_BOOK_EDIT_CONTENT"),
            controls=[self.plugin._modal_nav_dropdown(), content_input],
            on_close=None,
            on_submit=on_submit,
        )
        player.send_form(form)

    def show_chapter_add(self, player: Player, section_index: int) -> None:
        section = self.plugin.newbie_book.get_section(section_index)
        if section is None:
            return self.show_sections(player, 0)
        title_input = TextInput(
            label="新章节标题",
            placeholder="每日签到",
            default_value="",
        )
        content_input = TextInput(
            label=self._text("NEWBIE_BOOK_CONTENT_LABEL"),
            placeholder="第一行内容\\n第二行内容（可留空稍后编辑）",
            default_value="",
        )

        def on_submit(p: Player, json_str: str) -> None:
            if self._is_back(p, json_str):
                return self.show_chapters(p, section_index, 0)
            data = self._parse(p, json_str)
            if data is None:
                return self.show_chapters(p, section_index, 0)
            title = normalize_single_line(str(data[1] or ""), MAX_TITLE_LEN)
            if not title:
                p.send_message(self._text("NEWBIE_BOOK_INVALID_INPUT"))
                return self.show_chapters(p, section_index, 0)
            content = normalize_multiline_text(str(data[2] or "")) if len(data) >= 3 else ""
            section.setdefault("chapters", []).append({"title": title, "content": content})
            self._saved(p)
            self.show_chapters(p, section_index, 0)

        form = ModalForm(
            title=self._text("NEWBIE_BOOK_ADD_CHAPTER"),
            controls=[self.plugin._modal_nav_dropdown(), title_input, content_input],
            on_close=None,
            on_submit=on_submit,
        )
        player.send_form(form)

    # ---- 重置 ----

    def show_reset_confirm(self, player: Player) -> None:
        panel = ActionForm(
            title=self._text("NEWBIE_BOOK_RESET_CONFIRM"),
            content=self._text("NEWBIE_BOOK_RESET_CONFIRM_CONTENT"),
            on_close=None,
        )
        panel.add_button(
            self._text("NEWBIE_BOOK_RESET_CONFIRM"),
            on_click=self._do_reset,
        )
        panel.add_button(
            self.plugin.language_manager.GetText("RETURN_BUTTON_TEXT"),
            icon=self._icon(ui_icons.BACK),
            on_click=self.show_menu,
        )
        player.send_form(panel)

    def _do_reset(self, player: Player) -> None:
        try:
            self.plugin.newbie_book.reset_to_default(keep_legacy=True)
            player.send_message(self._text("NEWBIE_BOOK_RESET_DONE"))
        except Exception as e:
            player.send_message(f"§c[新手书] 重置失败：{e}")
        self.show_menu(player)

    # ---- Modal 工具 ----

    def _parse(self, player: Player, json_str: str) -> Optional[list]:
        try:
            data = json.loads(json_str)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        player.send_message(self.plugin.language_manager.GetText("OP_CORE_SETTINGS_INVALID") or "输入无效")
        return None

    def _is_back(self, player: Player, json_str: str) -> bool:
        try:
            data = json.loads(json_str)
        except Exception:
            return False
        if isinstance(data, list):
            return self.plugin._modal_choice_is_back(data, 0)
        return False
