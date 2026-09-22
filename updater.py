# -*- coding: utf-8 -*-
"""从 GitHub 更新本插件代码（保留用户配置）。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx

PLUGIN_DIR = Path(__file__).resolve().parent
# NoneBot 版仓库根目录即插件；AstrBot 版用 astrbot_plugin_wuwa_luck
NONEBOT_REPO = "baichui/wuwa_luck"
ASTRBOT_REPO = "baichui/astrbot_plugin_wuwa_luck"

# 更新时覆盖的代码文件；config.json / 用户数据不覆盖
CODE_FILES = {
    "nonebot": ["__init__.py", "data.py", "image.py", "config.py", "updater.py"],
    "astrbot": ["main.py", "image.py", "wuwa_data.py", "metadata.yaml", "_conf_schema.json", "updater.py"],
}

# 资源文件仅在缺失时补
ASSET_FILES = ["assets/bg.png"]

_KEEP = {"config.json", "config.py", "__init__.py", "main.py"}


def _zip_url(repo: str) -> str:
    return f"https://codeload.github.com/{repo}/zip/refs/heads/master"


async def update_plugin(platform: str = "nonebot") -> str:
    """下载仓库 zip，覆盖插件代码文件。返回用户可读结果。"""
    if platform not in CODE_FILES:
        raise ValueError(f"unknown platform {platform}")
    repo = NONEBOT_REPO if platform == "nonebot" else ASTRBOT_REPO
    files = CODE_FILES[platform]

    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        r = await client.get(_zip_url(repo))
        if r.status_code != 200:
            return f"下载失败 HTTP {r.status_code}"
        data = r.content

    zf = zipfile.ZipFile(io.BytesIO(data))
    names = zf.namelist()
    if not names:
        return "压缩包为空"
    root = names[0].split("/")[0] + "/"

    updated: list[str] = []
    for rel in files:
        src = root + rel
        if src not in zf.namelist():
            continue
        dst = PLUGIN_DIR / rel
        dst.write_bytes(zf.read(src))
        updated.append(rel)

    for rel in ASSET_FILES:
        dst = PLUGIN_DIR / rel
        if dst.exists():
            continue
        src = root + rel
        if src in zf.namelist():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(zf.read(src))
            updated.append(rel)

    if not updated:
        return "没有可更新的文件"
    return f"已更新：{', '.join(updated)}（{repo}）。配置未改动，热加载后生效。"
