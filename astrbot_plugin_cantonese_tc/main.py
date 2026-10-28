"""粤语 + 繁體字输出（Cantonese + Traditional Chinese）

两层保险：
1. on_llm_request：往系统提示词里追加「只用香港粤语口语 + 全部繁體字」的硬性要求；
2. on_decorating_result：发送前把正文里残留的簡體字统一转成繁體（zhconv，HK 字形），
   并跳过代码块、行内代码、链接、CQ 码，避免把不该转的东西转坏。

依赖：zhconv（已安装到 AstrBot 的 data/site-packages）。缺失时插件仍可用，只是不做字形兜底。
"""

from __future__ import annotations

import re

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig

try:  # 字形转换是可选增强
    import zhconv
except Exception:  # noqa: BLE001
    zhconv = None

DEFAULT_STYLE = """【語言風格：粵語 + 繁體字（最高優先級，覆蓋默認語言習慣）】
1. 無論對方用甚麼語言，你只用「香港粵語口語」回答，不要用普通話書面語。
2. 所有漢字一律用繁體，禁止出現簡體字。例：这→這、说→說、时→時、个→個、们→們、还→還、会→會、来→來、为→為、么→麼、里→裡、后→後。
3. 粵語用詞自然穿插，不要堆砌：係、唔、咗、緊、嘅、喺、嗰、咁、啲、嚟、睇、識、俾、攞、揾、諗、而家、琴日、聽日、冇、搞掂、唔該、得閒、點解、點算、幾時、邊度、乜嘢。
4. 句式按粵語習慣。例如：「你講咩？」「係咁先啦」「咁都得？」「唔使客氣」「我唔知喎」「等陣先」。
5. 唔好解釋自己講緊粵語，唔好加「（粵語）」「（粵語翻譯）」之類標註，唔好翻譯成普通話。
6. 專有名詞、人名、代碼、連結、英文縮寫保持原樣。
7. 上面的人格設定、語氣、人設全部保留，只係把語言換成粵語 + 繁體字。"""

# 需要原样保留的片段：代码块、行内代码、URL、CQ 码、<xml/json> 段
PROTECT_RE = re.compile(
    r"(```.*?```|~~~.*?~~~|`[^`\n]+`|https?://[^\s)]+|\[CQ:[^\]]+\]|<[^>\n]{1,60}>)",
    re.S,
)
MASK_RE = re.compile("\ue000(\\d+)\ue001")


class CantoneseTraditional(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.conf = config
        self.locale = str(self.conf.get("locale", "zh-hk") or "zh-hk")
        self.protect = bool(self.conf.get("protect_code_and_links", True))
        self.use_conversion = bool(self.conf.get("convert_traditional", True))
        logger.info(
            "[cantonese_tc] 插件已加载：enabled=%s 范围=%s 字形转换=%s(%s) zhconv=%s",
            self.conf.get("enabled", True),
            self.conf.get("scope", "all"),
            self.use_conversion,
            self.locale,
            "可用" if zhconv is not None else "缺失",
        )
        if self.use_conversion and zhconv is None:
            logger.warning(
                "[cantonese_tc] 未找到 zhconv，繁體兜底不可用；"
                "可执行 pip install zhconv -t <AstrBot>/data/site-packages",
            )

    # ---------- 配置 ----------
    def _cfg(self, key: str, default):
        try:
            value = self.conf.get(key, default)
        except Exception:  # noqa: BLE001
            return default
        return default if value is None else value

    def _in_scope(self, event: AstrMessageEvent) -> bool:
        scope = str(self._cfg("scope", "all") or "all").lower()
        if scope == "group":
            return not event.is_private_chat()
        if scope == "private":
            return event.is_private_chat()
        return True

    # ---------- 繁体转换 ----------
    def _convert(self, text: str) -> str:
        if not text or zhconv is None:
            return text
        spans: list[str] = []

        def _mask(match: re.Match) -> str:
            spans.append(match.group(0))
            return f"\ue000{len(spans) - 1}\ue001"

        masked = PROTECT_RE.sub(_mask, text) if self.protect else text
        converted = zhconv.convert(masked, self.locale)

        if spans:
            def _unmask(match: re.Match) -> str:
                idx = int(match.group(1))
                return spans[idx] if 0 <= idx < len(spans) else match.group(0)

            converted = MASK_RE.sub(_unmask, converted)
        return converted

    # ---------- 1. 提示词注入 ----------
    @filter.on_llm_request()
    async def inject_style(self, event: AstrMessageEvent, req):
        try:
            if not bool(self._cfg("enabled", True)):
                return
            if not self._in_scope(event):
                return
            if event.get_extra("_cantonese_tc_injected"):
                return
            style = str(self._cfg("style_prompt", "") or "").strip() or DEFAULT_STYLE
            req.system_prompt = (req.system_prompt or "") + "\n\n" + style
            event.set_extra("_cantonese_tc_injected", True)
            if bool(self._cfg("debug", False)):
                logger.info(f"[cantonese_tc] 已注入粤语风格提示 umo={event.unified_msg_origin}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[cantonese_tc] 注入提示词失败：{exc}")

    # ---------- 2. 发送前字形兜底 ----------
    @filter.on_decorating_result()
    async def convert_result(self, event: AstrMessageEvent):
        try:
            if not bool(self._cfg("enabled", True)):
                return
            if not self.use_conversion:
                return
            if not self._in_scope(event):
                return
            result = event.get_result()
            if result is None or not getattr(result, "chain", None):
                return
            changed = 0
            for comp in result.chain:
                if isinstance(comp, Plain) and comp.text:
                    new_text = self._convert(comp.text)
                    if new_text != comp.text:
                        comp.text = new_text
                        changed += 1
            if changed and bool(self._cfg("debug", False)):
                logger.info(f"[cantonese_tc] 已转换 {changed} 段文本为繁體")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[cantonese_tc] 繁體转换失败：{exc}")

    # ---------- 调试命令 ----------
    @filter.command("繁体测试")
    async def cmd_convert(self, event: AstrMessageEvent):
        text = (event.message_str or "").strip()
        text = re.sub(r"^/?繁体测试\s*", "", text).strip()
        if not text:
            yield event.plain_result("用法：/繁体测试 这个软件真的很厉害，我们一起去玩吧")
            return
        converted = self._convert(text)
        yield event.plain_result(f"原文：{text}\n繁體：{converted}")
