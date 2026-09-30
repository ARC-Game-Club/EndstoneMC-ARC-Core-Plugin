# -*- coding: utf-8 -*-
"""新手书（newbie_book.json）数据层：书式新手引导的存储、种子、旧文件迁移。

结构（plugins/ARCCore/newbie_book.json）：
{
  "version": 1,
  "title": "新手手册",        # 封面标题
  "intro_title": "简介",      # 封面简介小标题
  "intro": "...",             # 封面简介正文（一进去看到的内容）
  "sections": [               # 板块（封面上的一个个按钮）
    {
      "name": "插件",
      "intro": "...",         # 板块介绍（板块页正文）
      "chapters": [           # 章节（板块页上的按钮）
        {"title": "每日签到", "content": "..."}
      ]
    }
  ]
}

旧版 newbie_welcome.txt 仅作迁移源：书文件不存在时把旧文本并入「旧版教学」板块，
此后以书文件为准；OP 重载会重新读盘。
"""
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

BOOK_VERSION = 1
BOOK_FILE_NAME = "newbie_book.json"
LEGACY_WELCOME_FILE_NAME = "newbie_welcome.txt"

# 与 arc_core_plugin._ensure_newbie_files_exist 的默认文案一致；
# 内容完全等于该默认值时视为「未配置过」，不再迁入旧版教学板块。
LEGACY_DEFAULT_WELCOME = (
    "欢迎来到我们的服务器！\n希望你在这里玩得愉快！\n如有疑问请联系管理员。"
)

# 单行字段超长截断上限；正文不截断（OP 手改 JSON 时也不丢内容）
MAX_TITLE_LEN = 32
MAX_SECTION_NAME_LEN = 16
MAX_INTRO_TITLE_LEN = 16
MAX_CONTENT_LEN = 8000


def normalize_multiline_text(raw: Any, max_len: int = MAX_CONTENT_LEN) -> str:
    """正文规范化：字面 \\n 转真实换行、统一换行符、去首尾空白、超长截断。"""
    text = "" if raw is None else str(raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\\n", "\n")
    text = text.strip()
    if len(text) > max_len:
        text = text[:max_len]
    return text


def normalize_single_line(raw: Any, max_len: int) -> str:
    """单行字段规范化：换行（含字面 \\n）压成空格、去首尾空白、超长截断。"""
    text = normalize_multiline_text(raw, max_len=10**9)
    text = text.replace("\n", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    if len(text) > max_len:
        text = text[:max_len]
    return text


def _normalize_section(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {"name": "", "intro": "", "chapters": []}
    raw_chapters = raw.get("chapters")
    chapters: List[Dict[str, str]] = []
    if isinstance(raw_chapters, list):
        for ch in raw_chapters:
            if not isinstance(ch, dict):
                continue
            chapters.append(
                {
                    "title": normalize_single_line(ch.get("title"), MAX_TITLE_LEN),
                    "content": normalize_multiline_text(ch.get("content")),
                }
            )
    return {
        "name": normalize_single_line(raw.get("name"), MAX_SECTION_NAME_LEN),
        "intro": normalize_multiline_text(raw.get("intro")),
        "chapters": chapters,
    }


def normalize_book(raw: Any) -> Dict[str, Any]:
    """把任意来源（手改 JSON / 旧数据）整理成规范书结构；永不抛异常。"""
    if not isinstance(raw, dict):
        raw = {}
    sections_raw = raw.get("sections")
    sections = (
        [_normalize_section(s) for s in sections_raw if isinstance(s, dict)]
        if isinstance(sections_raw, list)
        else []
    )
    return {
        "version": BOOK_VERSION,
        "title": normalize_single_line(raw.get("title"), MAX_TITLE_LEN),
        "intro_title": normalize_single_line(raw.get("intro_title"), MAX_INTRO_TITLE_LEN),
        "intro": normalize_multiline_text(raw.get("intro")),
        "sections": sections,
    }


def default_book() -> Dict[str, Any]:
    """全新安装的默认模板：封面简介 + 插件/模组两个板块（各带一个示例章节）。"""
    return normalize_book(
        {
            "title": "新手手册",
            "intro_title": "简介",
            "intro": (
                "欢迎来到本服务器！\n"
                "这本《新手手册》就是你的随身指南：下面每个按钮是一个板块，"
                "点进去后再选章节阅读。\n"
                "发送 /arc 可随时打开主菜单，点「新手引导」即可回到本书。\n"
                "祝你在服务器玩得愉快！"
            ),
            "sections": [
                {
                    "name": "插件",
                    "intro": (
                        "服务器玩法主要由一个个插件提供，本板块逐个介绍常用插件的用法。\n"
                        "（在 OP 面板·新手书编辑 中为每个插件各建一个章节）"
                    ),
                    "chapters": [
                        {
                            "title": "示例：每日签到",
                            "content": (
                                "每天签到一次，可领存款与随机物资。\n"
                                "入口：/arc 主菜单 → 每日签到。\n"
                                "本章节为示例，请在 OP 面板中改写成你的服务器内容。"
                            ),
                        }
                    ],
                },
                {
                    "name": "模组",
                    "intro": (
                        "本板块逐个介绍服务器安装的模组（行为包/资源包玩法）。\n"
                        "（在 OP 面板·新手书编辑 中为每个模组各建一个章节）"
                    ),
                    "chapters": [
                        {
                            "title": "示例：世界与模组",
                            "content": (
                                "在这里介绍服务器的模组世界观与特色玩法。\n"
                                "本章节为示例，请在 OP 面板中改写成你的服务器内容。"
                            ),
                        }
                    ],
                },
            ],
        }
    )


def legacy_welcome_section(legacy_text: str) -> Optional[Dict[str, Any]]:
    """旧版一次性教学文本 → 「旧版教学」板块；空文本或默认文案返回 None。"""
    text = normalize_multiline_text(legacy_text)
    if not text or text == normalize_multiline_text(LEGACY_DEFAULT_WELCOME):
        return None
    return {
        "name": "旧版教学",
        "intro": "旧版一次性新手教学全文，仅供查阅/搬运，可在编辑后删除本板块。",
        "chapters": [{"title": "旧版新手教学", "content": text}],
    }


def seed_book(legacy_text: str = "") -> Dict[str, Any]:
    """生成初始书：默认模板 +（可选）旧版教学板块。"""
    book = default_book()
    section = legacy_welcome_section(legacy_text)
    if section is not None:
        book["sections"].append(_normalize_section(section))
    return book


def load_book(path: Path) -> Optional[Dict[str, Any]]:
    """读书文件；损坏/缺失返回 None（由调用方决定是否用 seed 兜底）。"""
    try:
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return normalize_book(raw)
    except Exception:
        return None


def save_book(path: Path, data: Dict[str, Any]) -> None:
    """原子写盘：先写临时文件再替换，避免写一半被读到坏 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(tmp_path, path)


class NewbieBookStore:
    """书数据 + 磁盘同步；线程安全（OP 编辑与主线程读都在服务器线程，仅兜底）。"""

    def __init__(self, base_dir: Path, legacy_welcome_path: Optional[Path] = None):
        self.path = Path(base_dir) / BOOK_FILE_NAME
        self.legacy_path = (
            Path(legacy_welcome_path)
            if legacy_welcome_path is not None
            else Path(base_dir) / LEGACY_WELCOME_FILE_NAME
        )
        self._lock = threading.RLock()
        self.data: Dict[str, Any] = self._load_or_seed()

    def _load_or_seed(self) -> Dict[str, Any]:
        book = load_book(self.path)
        if book is not None:
            return book
        book = seed_book(self._read_legacy_text())
        self._write(book)
        return book

    def _read_legacy_text(self) -> str:
        try:
            if self.legacy_path.exists():
                return self.legacy_path.read_text(encoding="utf-8")
        except Exception:
            pass
        return ""

    def _write(self, data: Dict[str, Any]) -> None:
        try:
            save_book(self.path, data)
        except Exception:
            pass  # 写盘失败不阻塞游戏逻辑；OP 重载时可重试

    def reload(self) -> None:
        with self._lock:
            self.data = load_book(self.path) or self.data

    def save(self) -> None:
        with self._lock:
            self._write(self.data)

    def reset_to_default(self, keep_legacy: bool = True) -> None:
        with self._lock:
            self.data = seed_book(self._read_legacy_text() if keep_legacy else "")
            self._write(self.data)

    # ---- 只读便捷访问（线程内快照，调用方不再改） ----

    def get_book(self) -> Dict[str, Any]:
        with self._lock:
            return self.data

    def get_section(self, index: int) -> Optional[Dict[str, Any]]:
        sections = self.get_book().get("sections") or []
        if 0 <= index < len(sections):
            return sections[index]
        return None

    def get_chapter(self, section_index: int, chapter_index: int) -> Optional[Dict[str, Any]]:
        section = self.get_section(section_index)
        if section is None:
            return None
        chapters = section.get("chapters") or []
        if 0 <= chapter_index < len(chapters):
            return chapters[chapter_index]
        return None

    def count_sections(self) -> int:
        return len(self.get_book().get("sections") or [])


def book_to_plain_text(book: Dict[str, Any], max_len: int = 3000) -> str:
    """把整本书摊平成纯文本（供 AI 助手等 API 使用），超长截断。"""
    parts: List[str] = []
    title = str(book.get("title") or "").strip()
    intro = str(book.get("intro") or "").strip()
    if title:
        parts.append(f"【{title}】")
    if intro:
        parts.append(intro)
    for section in book.get("sections") or []:
        name = str(section.get("name") or "").strip()
        s_intro = str(section.get("intro") or "").strip()
        if name:
            parts.append(f"■ {name}")
        if s_intro:
            parts.append(s_intro)
        for idx, ch in enumerate(section.get("chapters") or [], start=1):
            ch_title = str(ch.get("title") or "").strip() or f"章节{idx}"
            parts.append(f"· {ch_title}")
            ch_content = str(ch.get("content") or "").strip()
            if ch_content:
                parts.append(ch_content)
    text = "\n".join(part for part in parts if part)
    if len(text) > max_len:
        text = text[:max_len]
    return text
