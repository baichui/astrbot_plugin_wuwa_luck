# -*- coding: utf-8 -*-
"""从 GitHub 更新本插件代码（保留用户配置）。

安全策略：
- 下载内容先写入同目录临时文件，再 os.replace 原子替换，中断不会写坏现有文件；
- 覆盖前把旧文件备份为 <文件名>.bak，更新失败可手动回滚；
- 返回信息附带 zip 内 metadata.yaml 的版本号，用户可核对更新到了哪一版。
"""

from __future__ import annotations

import io
import os
import re
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


def _zip_url(repo: str) -> str:
    return f"https://codeload.github.com/{repo}/zip/refs/heads/master"


def _read_version(zf: zipfile.ZipFile, root: str) -> str | None:
    """从压缩包内 metadata.yaml 读取版本号；读不到不阻断更新。"""
    try:
        text = zf.read(root + "metadata.yaml").decode("utf-8", errors="replace")
    except (KeyError, UnicodeDecodeError):
        return None
    m = re.search(r"^version:\s*[\"']?([0-9][0-9A-Za-z.\-]*)", text, re.MULTILINE)
    return m.group(1) if m else None


def _atomic_write(dst: Path, data: bytes, backup: bool = True) -> None:
    """临时文件 → 备份旧文件 → os.replace 原子替换。

    全程不直接写目标文件：中途断网/断电最多留下一个 .tmp，
    现有代码文件要么是旧版要么是完整新版，不会出现半写损坏。
    """
    tmp = dst.with_name(dst.name + ".tmp")
    tmp.write_bytes(data)
    if backup and dst.exists():
        try:
            dst.with_name(dst.name + ".bak").write_bytes(dst.read_bytes())
        except OSError:
            pass  # 备份失败不阻断更新
    os.replace(tmp, dst)  # 同目录内原子操作


async def update_plugin(platform: str = "nonebot") -> str:
    """下载仓库 zip，覆盖插件代码文件。返回用户可读结果。"""
    if platform not in CODE_FILES:
        raise ValueError(f"unknown platform {platform}")
    repo = NONEBOT_REPO if platform == "nonebot" else ASTRBOT_REPO
    files = CODE_FILES[platform]

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            r = await client.get(_zip_url(repo))
            if r.status_code != 200:
                return f"更新失败：GitHub HTTP {r.status_code}"
            data = r.content
    except OSError as e:
        return f"更新失败：网络/DNS 不可用（{e.strerror or e}）。需能访问 github.com；无外网请手动覆盖文件。"
    except Exception as e:  # noqa: BLE001
        return f"更新失败：{type(e).__name__}: {e}"

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return "下载内容不是有效的 zip（网络中断或代理异常），已放弃更新，现有文件未受影响"
    names = zf.namelist()
    if not names:
        return "压缩包为空"
    root = names[0].split("/")[0] + "/"
    version = _read_version(zf, root)

    updated: list[str] = []
    for rel in files:
        src = root + rel
        if src not in zf.namelist():
            continue
        _atomic_write(PLUGIN_DIR / rel, zf.read(src))
        updated.append(rel)

    for rel in ASSET_FILES:
        dst = PLUGIN_DIR / rel
        if dst.exists():
            continue
        src = root + rel
        if src in zf.namelist():
            dst.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(dst, zf.read(src), backup=False)
            updated.append(rel)

    if not updated:
        return "没有可更新的文件"
    ver = f" v{version}" if version else ""
    return f"已更新{ver}：{', '.join(updated)}（{repo}）。配置未改动，旧文件备份为 *.bak，热加载后生效。"
