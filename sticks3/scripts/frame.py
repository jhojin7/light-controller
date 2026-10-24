"""Small dependency-free PNG writer for RGB565 firmware frames."""
from pathlib import Path
import struct
import zlib


def png(path, pixels, width=135, height=240):
    if len(pixels) != width * height:
        raise ValueError("Incomplete framebuffer")
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for color in pixels[y * width:(y + 1) * width]:
            r, g, b = (color >> 11) & 31, (color >> 5) & 63, color & 31
            rows.extend(((r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    contents = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    contents += chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    Path(path).write_bytes(contents)


def decode_runs(reply):
    runs = reply["runs"]
    if len(runs) % 2:
        raise ValueError("Invalid framebuffer runs")
    pixels = []
    for count, color in zip(runs[::2], runs[1::2]):
        if not 0 < count <= 32400 or not 0 <= color <= 65535:
            raise ValueError("Invalid framebuffer run")
        pixels.extend([color] * count)
        if len(pixels) > 32400:
            raise ValueError("Framebuffer exceeds screen size")
    if len(pixels) != 32400:
        raise ValueError("Incomplete framebuffer")
    return pixels
