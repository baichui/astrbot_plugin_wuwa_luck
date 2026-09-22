# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Image

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))


def _load_local(name: str):
    """按绝对路径加载同目录模块，避免与顶层同名包冲突。"""
    path = _PLUGIN_DIR / f"{name}.py"
    mod_name = f"wuwa_luck_{name}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


_wuwa_data = _load_local("wuwa_data")
sys.modules.setdefault("wuwa_data", _wuwa_data)
_image_mod = _load_local("image")
get_image = _image_mod.get_image
_updater = _load_local("updater")


class WUWALuck(star.Star):
    """鸣潮主题今日运势（白底卡片）。

    指令：/luck /今日运势 /更新luck
    WebUI 可配置：各角色权重、鸣潮宜忌概率、谐振指数文案。
    """

    def __init__(self, context: star.Context, config: dict | None = None) -> None:
        super().__init__(context)
        self.config = config or {}

    def _cfg_float(self, key: str, default: float) -> float:
        try:
            v = self.config.get(key, default)
            return float(v) if v is not None else default
        except Exception:  # noqa: BLE001
            return default

    def _cfg_int(self, key: str, default: int) -> int:
        try:
            v = self.config.get(key, default)
            return int(v) if v is not None else default
        except Exception:  # noqa: BLE001
            return default

    def _cfg_list(self, key: str) -> list[str]:
        v = self.config.get(key) or []
        if not isinstance(v, list):
            return []
        return [str(x).strip() for x in v if str(x).strip()]

    def _sender(self, event: AstrMessageEvent) -> tuple[str, str]:
        uid = ""
        nickname = ""
        try:
            uid = str(event.get_sender_id() or "")
        except Exception:  # noqa: BLE001
            uid = ""
        try:
            nickname = str(event.get_sender_name() or "")
        except Exception:  # noqa: BLE001
            nickname = ""

        sender = getattr(getattr(event, "message_obj", None), "sender", None)
        if sender is not None:
            if not uid:
                user_id = getattr(sender, "user_id", None)
                if user_id is not None:
                    uid = str(user_id)
            if not nickname:
                nickname = str(
                    getattr(sender, "card", None)
                    or getattr(sender, "nickname", None)
                    or ""
                )

        if not uid:
            uid = "0"
        nickname = nickname.strip() or "漂泊者"
        return uid, nickname[:16]

    def _cfg_weights(self) -> dict[str, float]:
        """读取 character_weights 下各角色 0-100 权重。"""
        raw = self.config.get("character_weights") or {}
        out: dict[str, float] = {}
        if not isinstance(raw, dict):
            return out
        for name in _wuwa_data.all_guide_characters():
            if name not in raw:
                w = 80.0 if name == _wuwa_data.XIAO_AI_NAME else 1.0
            else:
                try:
                    w = float(raw[name])
                except Exception:  # noqa: BLE001
                    continue
            if w > 0:
                out[name] = w
        return out

    @filter.command("luck", alias={"今日运势"})
    async def luck(self, event: AstrMessageEvent):
        """生成今日运势图"""
        uid, nickname = self._sender(event)
        metrics = self._cfg_list("metric_labels")
        try:
            data = get_image(
                nickname=nickname,
                uid=uid,
                character_weights=self._cfg_weights() or None,
                wuwa_deed_chance=self._cfg_float("wuwa_deed_chance", 0.3),
                metric_labels=metrics or None,
            )
        except Exception as e:  # noqa: BLE001
            yield event.plain_result(f"运势图生成失败：{e}")
            return

        chain: list = []
        if not event.is_private_chat():
            try:
                chain.append(At(qq=uid))
            except Exception:  # noqa: BLE001
                pass
        chain.append(Image.fromBytes(data))
        yield event.chain_result(chain)

    @filter.command("更新luck", alias={"更新运势", "luck更新"})
    async def update_luck(self, event: AstrMessageEvent):
        """从 GitHub 更新本插件（保留配置）"""
        try:
            msg = await _updater.update_plugin("astrbot")
        except Exception as e:  # noqa: BLE001
            yield event.plain_result(f"更新失败：{e}")
            return
        yield event.plain_result(msg + "\n如代码有改动，请重载插件或重启 AstrBot。")
