#!/usr/bin/env python3
"""Analog clock for the Waveshare 1.47" ST7789 SPI LCD on a Pi Zero W.

Landscape layout (320x172): analog face on the left, digital time/date right.
The panel is native 172x320 portrait; we render landscape and map it onto the
panel with a fixed rotate+flip (see to_panel)."""
import math
import time
from datetime import datetime

import st7789
from PIL import Image, ImageDraw, ImageFont

PANEL_W, PANEL_H = 172, 320        # native panel resolution
LW, LH = 320, 172                  # our landscape canvas
ROTATE = 270                       # CCW degrees to map landscape -> panel

CX, CY = 86, 86                    # analog face center (left half)
R = 80                             # face radius

# ---- colours ----
BG = (8, 10, 16)
FACE = (18, 22, 32)
RIM = (90, 110, 150)
TICK = (200, 210, 230)
TICK_MINOR = (70, 80, 100)
HOUR_HAND = (235, 240, 250)
MIN_HAND = (150, 200, 255)
SEC_HAND = (255, 80, 80)
HUB = (255, 80, 80)
TEXT = (225, 232, 245)
TEXT_DIM = (130, 145, 170)
ACCENT = (150, 200, 255)


def load_font(size, bold=False):
    base = "/usr/share/fonts/truetype/dejavu/"
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(base + name, size)
    except OSError:
        return ImageFont.load_default()


FONT_TIME = load_font(46, bold=True)
FONT_SEC = load_font(22, bold=True)
FONT_DATE = load_font(20)


def hand(draw, frac, length, width, color):
    theta = 2 * math.pi * frac
    x = CX + length * math.sin(theta)
    y = CY - length * math.cos(theta)
    draw.line([(CX, CY), (x, y)], fill=color, width=width)


def draw_static_face(img):
    d = ImageDraw.Draw(img)
    d.ellipse([CX - R, CY - R, CX + R, CY + R], fill=FACE, outline=RIM, width=3)
    for m in range(60):
        theta = 2 * math.pi * (m / 60.0)
        outer = R - 4
        if m % 5 == 0:
            inner, col, w = R - 15, TICK, 3
        else:
            inner, col, w = R - 8, TICK_MINOR, 1
        x0, y0 = CX + inner * math.sin(theta), CY - inner * math.cos(theta)
        x1, y1 = CX + outer * math.sin(theta), CY - outer * math.cos(theta)
        d.line([(x0, y0), (x1, y1)], fill=col, width=w)


def text_at(d, cx, cy, text, font, fill, anchor="mm"):
    d.text((cx, cy), text, font=font, fill=fill, anchor=anchor)


def to_panel(img):
    """Landscape canvas -> native panel buffer.

    The panel's net transform mirrors the image horizontally (text comes out
    backwards), so we pre-flip the landscape canvas left-right to cancel it,
    then rotate to the panel's portrait frame and apply its vertical flip."""
    return (
        img.transpose(Image.FLIP_LEFT_RIGHT)
        .rotate(ROTATE, expand=True)
        .transpose(Image.FLIP_TOP_BOTTOM)
    )


def main():
    disp = st7789.ST7789(
        port=0, cs=0, dc=25, rst=27, backlight=24,
        width=PANEL_W, height=PANEL_H, rotation=0, invert=True,
        offset_left=34, offset_top=0, spi_speed_hz=4000000,
    )
    disp.reset()
    disp._init()
    disp.command(0x36)
    disp.data(0x00)

    face = Image.new("RGB", (LW, LH), BG)
    draw_static_face(face)
    rx = 172 + (LW - 172) // 2  # center of the right-hand text column

    try:
        while True:
            now = datetime.now()
            img = face.copy()
            d = ImageDraw.Draw(img)

            sec = now.second + now.microsecond / 1e6
            minute = now.minute + sec / 60.0
            hour = (now.hour % 12) + minute / 60.0

            hand(d, hour / 12.0, R * 0.52, 6, HOUR_HAND)
            hand(d, minute / 60.0, R * 0.78, 4, MIN_HAND)
            hand(d, sec / 60.0, R * 0.86, 2, SEC_HAND)
            d.ellipse([CX - 4, CY - 4, CX + 4, CY + 4], fill=HUB)

            text_at(d, rx, 55, now.strftime("%I:%M"), FONT_TIME, TEXT)
            text_at(d, rx, 95, now.strftime(":%S"), FONT_SEC, ACCENT)
            text_at(d, rx, 130, now.strftime("%a %b %d"), FONT_DATE, TEXT_DIM)

            disp.display(to_panel(img))
            time.sleep(max(0, 1.0 - datetime.now().microsecond / 1e6))
    except KeyboardInterrupt:
        disp.display(to_panel(Image.new("RGB", (LW, LH), (0, 0, 0))))


if __name__ == "__main__":
    main()
