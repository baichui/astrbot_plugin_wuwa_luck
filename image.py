# -*- coding: utf-8 -*-
"""鸣潮主题「今日谐振」运势图渲染（白底卡片风）。"""

from __future__ import annotations

import hashlib
import random
from datetime import date
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from wuwa_data import (
    BAD_DEEDS_DAILY,
    BAD_DEEDS_WUWA,
    GACHA_METRICS,
    GOOD_DEEDS_DAILY,
    GOOD_DEEDS_WUWA,
    QUOTES_FOOTER,
    pick_character_guide,
    weighted_fortune,
)

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
TTF = ROOT / "ttf"

CANVAS_W, CANVAS_H = 900, 1140
MARGIN = 40

# 明亮配色：白底墨字 + 鸣潮青/金点缀
INK = "#1A2433"
MUTED = "#5B6B7C"
TEAL = "#0E7C8B"
CYAN = "#1B9AAA"
GOLD = "#B8892E"
RED = "#C2413A"
GREEN = "#1F8A5F"
WHITE = "#FFFFFF"
PANEL = "#FFFFFF"
SOFT = "#F4F8FB"
LINE = "#C9D8E4"
BORDER = "#8FB8C8"


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size=size)


def _pick_fonts() -> dict[str, Path]:
    """按 OS 常见字体目录查找；插件 ttf/ 作兜底。"""
    dirs: list[Path] = []
    for d in (
        Path(r"C:\Windows\Fonts"),
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".fonts",
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path.home() / "Library" / "Fonts",
        TTF,
    ):
        if d.exists():
            dirs.append(d)

    def _find(names: list[str]) -> Path | None:
        for name in names:
            for d in dirs:
                p = d / name
                if p.is_file():
                    return p
            # 子目录里再找一层（Linux 发行版常见）
            for d in dirs:
                for p in d.rglob(name):
                    if p.is_file():
                        return p
        return None

    sans = _find([
        "msyh.ttc", "Microsoft YaHei.ttc",
        "NotoSansSC-VF.ttf", "NotoSansSC-Regular.otf", "NotoSansCJK-Regular.ttc",
        "SourceHanSansCN-Regular.otf", "WenQuanYi Micro Hei.ttf", "wqy-microhei.ttc",
        "PingFang.ttc", "Hiragino Sans GB.ttc", "simhei.ttf",
    ])
    bold = _find([
        "msyhbd.ttc", "Microsoft YaHei Bold.ttc",
        "NotoSansSC-Bold.ttf", "NotoSansCJK-Bold.ttc",
        "SourceHanSansCN-Bold.otf", "simhei.ttf",
    ]) or sans
    serif = _find([
        "NotoSerifSC-VF.ttf", "NotoSerifSC-Regular.otf", "NotoSerifCJK-Regular.ttc",
        "SourceHanSerifCN-Regular.otf", "simsun.ttc", "SimSun.ttf",
        "Songti.ttc", "STSong.ttf",
    ]) or bold

    return {"serif": serif, "sans": sans or bold, "bold": bold}


def _seed_from(nickname: str, uid: int | str, day: date) -> random.Random:
    raw = f"{nickname}|{uid}|{day.isoformat()}|wuwa-luck-v14".encode()
    digest = hashlib.sha256(raw).hexdigest()
    return random.Random(int(digest[:16], 16))


def _round_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill=None, outline=None, width: int = 1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _center_text(
    draw: ImageDraw.ImageDraw,
    cx: float,
    cy: float,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((cx - w / 2, cy - h / 2 - bbox[1]), text, font=font, fill=fill)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    buf = ""
    for ch in text:
        trial = buf + ch
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] > max_w and buf:
            lines.append(buf)
            buf = ch
        else:
            buf = trial
    if buf:
        lines.append(buf)
    return lines


def _metric_bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    label: str,
    value: int,
    accent: str,
    fonts: dict[str, ImageFont.FreeTypeFont],
):
    label_w = 120
    bar_x = x + label_w + 12
    bar_w = w - label_w - 56
    draw.text((x, y + h / 2), label, font=fonts["sans"], fill=INK, anchor="lm")
    _round_rect(draw, (bar_x, y + 7, bar_x + bar_w, y + h - 7), radius=9, fill="#E8F0F5", outline=LINE, width=1)
    fill_w = int((bar_w - 6) * max(0, min(100, value)) / 100)
    if fill_w > 8:
        _round_rect(draw, (bar_x + 3, y + 10, bar_x + 3 + fill_w, y + h - 10), radius=6, fill=accent)
    draw.text((x + w, y + h / 2), f"{value}", font=fonts["bold"], fill=GOLD, anchor="rm")


def _draw_wave_deco(draw: ImageDraw.ImageDraw, y: int, color: str = CYAN):
    """顶部/底部简单波浪装饰线。"""
    amp, wave_len, thick = 6, 70, 2
    start_x = MARGIN + 24
    end_x = CANVAS_W - MARGIN - 24
    pts = []
    x = start_x
    up = True
    while x <= end_x:
        pts.append((x, y - amp if up else y + amp))
        up = not up
        x += wave_len // 2
    if len(pts) >= 2:
        draw.line(pts, fill=color, width=thick)


def get_image(
    nickname: str = "漂泊者",
    uid: int | str = 0,
    *,
    character_weights: dict[str, float] | None = None,
    wuwa_deed_chance: float = 0.30,
    metric_labels: list[str] | None = None,
) -> bytes:
    day = date.today()
    rng = _seed_from(nickname, uid, day)
    fortune_zh, _fortune_alias, fortune_color = weighted_fortune(rng)

    # 宜/忌默认各 2 条；大吉→忌缩成「诸事皆宜」；大凶→宜缩成「诸事不宜」
    # 鸣潮文案：全卡最多替换 1 条（约 30%），绝不出现两条鸣潮

    def _two_unique(pool, used: set[str]):
        first = rng.choice(pool)
        second = rng.choice([x for x in pool if x[0] != first[0]] or pool)
        guard = 0
        while second[0] in used and guard < 20:
            second = rng.choice([x for x in pool if x[0] != first[0]] or pool)
            guard += 1
        used.add(first[0])
        used.add(second[0])
        return first, second

    used: set[str] = set()
    special = None  # "诸事不宜" | "诸事皆宜" | None
    if fortune_zh == "大凶":
        goods = [("诸事不宜", "在家躺一天")]
        b1, b2 = _two_unique(BAD_DEEDS_DAILY, used)
        bads = [b1, b2]
        special = "诸事不宜"
    elif fortune_zh == "大吉":
        g1, g2 = _two_unique(GOOD_DEEDS_DAILY, used)
        goods = [g1, g2]
        bads = [("诸事皆宜", "去做想做的事情吧")]
        special = "诸事皆宜"
    else:
        g1, g2 = _two_unique(GOOD_DEEDS_DAILY, used)
        b1, b2 = _two_unique(BAD_DEEDS_DAILY, used)
        goods = [g1, g2]
        bads = [b1, b2]

    # 约 wuwa_deed_chance 把「非特判」的一格换成鸣潮；可替换槽位为空则跳过
    if rng.random() < max(0.0, min(1.0, float(wuwa_deed_chance))):
        slots: list[tuple[str, int]] = []
        if special != "诸事不宜":
            slots.append(("good", 0))
            slots.append(("good", 1))
        if special != "诸事皆宜":
            slots.append(("bad", 0))
            slots.append(("bad", 1))
        if slots:
            side, idx = rng.choice(slots)
            if side == "good":
                goods[idx] = rng.choice(GOOD_DEEDS_WUWA)
            else:
                bads[idx] = rng.choice(BAD_DEEDS_WUWA)

    char_name, char_quote = pick_character_guide(
        rng,
        character_weights=character_weights,
    )
    footer = rng.choice(QUOTES_FOOTER)

    bonus = {
        "大吉": 18, "上吉": 12, "中吉": 6, "小吉": 0,
        "末吉": -6, "凶": -14, "大凶": -22,
    }.get(fortune_zh, 0)
    labels = metric_labels if metric_labels else GACHA_METRICS
    metrics = [(label, max(5, min(99, rng.randint(48, 92) + bonus))) for label in labels]

    fonts_map = _pick_fonts()
    f_title = _font(fonts_map["serif"], 38)
    f_alias = _font(fonts_map["sans"], 22)
    f_fortune = _font(fonts_map["serif"], 88)
    f_date = _font(fonts_map["sans"], 19)
    f_label = _font(fonts_map["bold"], 24)
    f_item = _font(fonts_map["bold"], 28)
    # 小字：雅黑 Regular，字号 +1，不描边
    f_detail = _font(fonts_map["sans"], 20)
    f_char = _font(fonts_map["serif"], 26)
    f_quote = _font(fonts_map["sans"], 22)
    f_footer = _font(fonts_map["sans"], 18)
    f_metric_val = _font(fonts_map["bold"], 22)

    # 画布：浅冰蓝纸底
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (236, 244, 248, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    # 若有底图，极淡地铺一层纹理（不压暗文字区）
    bg_path = ASSETS / "bg.png"
    if bg_path.exists():
        tex = Image.open(bg_path).convert("RGBA").resize((CANVAS_W, CANVAS_H), Image.Resampling.LANCZOS)
        # 盖掉生成图右下角「AI生成 / Xiaomi MiMo」水印：整块用左侧纹理+纸色覆盖
        wm_w, wm_h = 420, 140
        src_x = max(0, CANVAS_W - wm_w - 80)
        patch = tex.crop((src_x, CANVAS_H - wm_h, src_x + wm_w, CANVAS_H))
        tex.paste(patch, (CANVAS_W - wm_w, CANVAS_H - wm_h))
        overlay = Image.new("RGBA", (wm_w + 40, wm_h + 20), (236, 244, 248, 230))
        tex.alpha_composite(overlay, (CANVAS_W - wm_w - 20, CANVAS_H - wm_h - 10))
        # 提亮 + 降透明，只作纸纹
        white = Image.new("RGBA", tex.size, (255, 255, 255, 255))
        tex = Image.blend(white, tex, alpha=0.12)
        img = Image.alpha_composite(img, tex)
        draw = ImageDraw.Draw(img, "RGBA")

    # 外框（双线，青+金）
    _round_rect(draw, (18, 18, CANVAS_W - 18, CANVAS_H - 18), radius=22, fill=None, outline=GOLD, width=2)
    _round_rect(draw, (26, 26, CANVAS_W - 26, CANVAS_H - 26), radius=18, fill=None, outline=BORDER, width=1)

    # 内层主白卡
    card_box = (MARGIN, MARGIN, CANVAS_W - MARGIN, CANVAS_H - MARGIN)
    _round_rect(draw, card_box, radius=16, fill=PANEL, outline=BORDER, width=1)

    # 顶部色带
    band_h = 10
    _round_rect(draw, (MARGIN, MARGIN, CANVAS_W - MARGIN, MARGIN + band_h + 8), radius=16, fill=None)
    draw.rectangle((MARGIN + 8, MARGIN, CANVAS_W - MARGIN - 8, MARGIN + band_h), fill=TEAL)

    cx = CANVAS_W / 2
    y = MARGIN + 36

    # 标题
    _center_text(draw, cx, y + 18, "今 日 运 势", f_title, TEAL)
    y += 56
    date_str = f"{day.year}年{day.month}月{day.day}日"
    _center_text(draw, cx, y + 10, date_str, f_date, MUTED)
    y += 36
    _draw_wave_deco(draw, y, CYAN)
    y += 24

    # 昵称
    nick = (nickname or "漂泊者").strip() or "漂泊者"
    if len(nick) > 16:
        nick = nick[:15] + "…"
    _center_text(draw, cx, y + 12, f"「{nick}」", f_alias, CYAN)
    y += 44

    # 大字运势（无潮汐别称）
    _center_text(draw, cx, y + 46, fortune_zh, f_fortune, fortune_color)
    y += 100

    for i, xoff in enumerate((-26, 0, 26)):
        r = 3 if i != 1 else 5
        draw.ellipse((cx + xoff - r, y - r, cx + xoff + r, y + r), fill=GOLD if i == 1 else CYAN)
    y += 28

    # 指标区（浅灰白卡）
    panel_y = y
    panel_h = 170
    px0, px1 = MARGIN + 28, CANVAS_W - MARGIN - 28
    _round_rect(draw, (px0, panel_y, px1, panel_y + panel_h), radius=14, fill=SOFT, outline=LINE, width=1)
    draw.text((px0 + 24, panel_y + 16), "谐 振 指 数", font=f_label, fill=TEAL)
    bar_x = px0 + 24
    bar_w = px1 - px0 - 48
    for idx, (label, value) in enumerate(metrics):
        _metric_bar(
            draw, bar_x, panel_y + 52 + idx * 34, bar_w, 28, label, value,
            fortune_color if idx == 0 else CYAN,
            {"sans": f_detail, "bold": f_metric_val},
        )
    y = panel_y + panel_h + 20

    # 宜 / 忌
    gap = 16
    half_w = (CANVAS_W - MARGIN * 2 - gap) // 2
    n_slots = max(len(goods), len(bads))
    card_h = 190 if n_slots <= 1 else 290
    left_x = MARGIN + 4
    right_x = left_x + half_w + gap

    _round_rect(draw, (left_x, y, left_x + half_w, y + card_h), radius=14, fill="#F3FBF7", outline="#A8D9C0", width=1)
    _round_rect(draw, (right_x, y, right_x + half_w, y + card_h), radius=14, fill="#FFF6F5", outline="#E8B4B0", width=1)

    # 宜/忌标题条
    _round_rect(draw, (left_x, y, left_x + half_w, y + 40), radius=14, fill="#E5F6EE")
    draw.rectangle((left_x, y + 28, left_x + half_w, y + 40), fill="#E5F6EE")
    _round_rect(draw, (right_x, y, right_x + half_w, y + 40), radius=14, fill="#FDECEA")
    draw.rectangle((right_x, y + 28, right_x + half_w, y + 40), fill="#FDECEA")
    draw.text((left_x + 18, y + 8), "宜", font=f_label, fill=GREEN)
    draw.text((right_x + 18, y + 8), "忌", font=f_label, fill=RED)

    def _deed_block(origin_x: int, origin_y: int, deeds: tuple):
        cy_item = origin_y + 64
        for title, detail in deeds:
            draw.text((origin_x + 18, cy_item), title, font=f_item, fill=INK)
            lines = _wrap(draw, detail, f_detail, half_w - 36)
            for line in lines[:2]:
                cy_item += 40
                draw.text((origin_x + 18, cy_item), line, font=f_detail, fill=MUTED)
            cy_item += 52

    _deed_block(left_x, y, goods)
    _deed_block(right_x, y, bads)
    y += card_h + 18

    # 角色指引
    guide_h = 130
    _round_rect(draw, (MARGIN + 4, y, CANVAS_W - MARGIN - 4, y + guide_h), radius=14, fill="#F7F4EC", outline="#E0D4B0", width=1)
    draw.text((MARGIN + 28, y + 16), f"共鸣指引 · {char_name}", font=f_char, fill=GOLD)
    quote_lines = _wrap(draw, char_quote, f_quote, CANVAS_W - MARGIN * 2 - 56)
    qy = y + 58
    for line in quote_lines[:2]:
        draw.text((MARGIN + 28, qy), line, font=f_quote, fill=INK)
        qy += 32
    y += guide_h + 20

    # 页脚（仅一句短语）
    _draw_wave_deco(draw, y - 6, LINE)
    y += 10
    _center_text(draw, cx, y + 10, footer, f_footer, MUTED)

    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def save_preview(path: str | Path, nickname: str = "漂泊者", uid: int | str = 0) -> Path:
    data = get_image(nickname=nickname, uid=uid)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out
