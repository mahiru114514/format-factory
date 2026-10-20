from __future__ import annotations

import io
import sys
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, ImageStat

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
_ocr_lock = threading.Lock()
_formula_lock = threading.Lock()


def load_image(source: Path | bytes | Image.Image) -> Image.Image:
    from .images import register_codecs
    register_codecs()
    if isinstance(source, Image.Image):
        image = ImageOps.exif_transpose(source).copy()
    else:
        with Image.open(io.BytesIO(source) if isinstance(source, bytes) else source) as opened:
            image = ImageOps.exif_transpose(opened).copy()
    if image.mode in ('RGBA', 'LA', 'P'):
        rgba = image.convert('RGBA')
        alpha = np.asarray(rgba.getchannel('A'))
        visible = np.asarray(rgba.convert('L'))[alpha >= 16]
        # White formula glyphs copied with transparency disappear on a white
        # canvas. Use a dark canvas only for uniformly light ink on a mostly
        # transparent image; ordinary document pages keep their white margins.
        light_ink = visible.size and visible.min() >= 192 and (alpha < 16).mean() > .5
        background = Image.new('RGB', rgba.size, 'black' if light_ink else 'white')
        background.paste(rgba, mask=rgba.getchannel('A'))
        return background
    return image.convert('RGB')


@lru_cache(maxsize=1)
def ordinary_engine():
    from rapidocr_onnxruntime import RapidOCR
    # The upstream loader uses top-level dynamic imports. Qualified imports allow
    # exactly the same model code to load from a packaged application as well.
    import importlib
    class LocalOCR(RapidOCR):
        @staticmethod
        def init_module(module_name, class_name):
            return getattr(importlib.import_module('rapidocr_onnxruntime.' + module_name), class_name)
    return LocalOCR()


def recognize_image(source: Path | bytes | Image.Image) -> str:
    image = load_image(source)
    image.thumbnail((5000, 5000))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    with _ocr_lock:
        result, _ = ordinary_engine()(buffer.getvalue())
    text = '\n'.join(line[1] for line in (result or []) if line[1].strip())
    if not text.strip():
        raise ValueError('未识别到文字，请选择清晰图片或裁剪文字区域后重试。')
    return text


@lru_cache(maxsize=1)
def formula_engine():
    from vendor.rapid_latex_ocr import LaTeXOCR
    models = ROOT / 'resources' / 'formula'
    names = ['image_resizer.onnx', 'encoder.onnx', 'decoder.onnx', 'tokenizer.json']
    if any(not (models / name).is_file() for name in names):
        raise ValueError('公式模型未准备好，请运行项目中的“准备运行环境.ps1”后重试。')
    return LaTeXOCR(image_resizer_path=models / names[0], encoder_path=models / names[1],
                    decoder_path=models / names[2], tokenizer_json=models / names[3])


def recognize_formula(source: Path | bytes | Image.Image) -> str:
    image = prepare_formula_image(load_image(source))
    if max(ImageStat.Stat(image.convert('L')).stddev) < 1:
        raise ValueError('未识别到公式，请裁剪一条清晰的印刷公式。')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    with _formula_lock:
        result, _ = formula_engine()(buffer.getvalue())
    if not result.strip():
        raise ValueError('未识别到公式，请裁剪单条印刷公式后重试。')
    return verify_large_logic_operator(image, result)


def verify_large_logic_operator(image: Image.Image, latex: str) -> str:
    """Check a single model-predicted large wedge against clear V/∧ geometry.

    This only verifies orientation, not whether an arbitrary shape is a logical
    operator. Multiple operators, ordinary sized letters, curved/asymmetric
    shapes and weak evidence leave the model output unchanged.
    """
    import re
    matches = list(re.finditer(r'\\big(?:vee|wedge)(?![a-zA-Z])', latex))
    if len(matches) != 1:
        return latex
    if re.search(r'(?<![a-zA-Z])V(?![a-zA-Z])|\\(?:Lambda|vee|wedge|land|lor)(?![a-zA-Z])|[Λ∨∧]', latex):
        return latex
    match = matches[0]
    if not re.match(r'\s*(?:\\limits\s*)?_(?:\{[^{}]+\}|[a-zA-Z0-9])\s*\^(?:\{[^{}]+\}|[a-zA-Z0-9])', latex[match.end():]):
        return latex
    import cv2
    sample = image.copy()
    sample.thumbnail((1600, 1600))
    gray = np.asarray(sample.convert('L'))
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.median(gray) > 128:
        mask = 255 - mask
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    heights = [h for x, y, w, h, area in stats[1:]
               if area >= 8 and h >= 5 and w >= 2 and h < .85 * gray.shape[0]]
    if not heights:
        return latex
    median_height = float(np.median(heights))
    directions = []
    ambiguous_shapes = 0
    for component in range(1, count):
        x, y, width, height, area = stats[component]
        if not (height >= 10 and height < .85 * gray.shape[0]
                and .3 * height <= width <= 1.6 * height):
            continue
        widths, centers, runs = [], [], []
        for row in range(2, height - 2):
            ink = np.flatnonzero(labels[y + row, x:x + width] == component)
            if not len(ink):
                break
            widths.append(ink[-1] - ink[0] + 1)
            centers.append((ink[-1] + ink[0]) / 2)
            runs.append(1 + np.count_nonzero(np.diff(ink) > 1))
        if (len(widths) != height - 4 or min(widths) > .5 * width
                or max(widths) < .65 * width or np.ptp(centers) > .2 * width
                or np.mean(np.asarray(runs) == 2) < .4):
            continue
        correlation = float(np.corrcoef(np.arange(len(widths)), widths)[0, 1])
        if abs(correlation) < .9:
            continue
        # Even a small or less regular wedge makes the image ambiguous. A large
        # variable V must never be bound to another operator elsewhere.
        ambiguous_shapes += 1
        if not (height >= max(32, 1.6 * median_height) and .35 * height <= width <= 1.3 * height
                and min(widths) <= .25 * width and max(widths) >= .8 * width
                and np.ptp(centers) <= .1 * width and np.mean(np.asarray(runs) == 2) >= .7
                and abs(correlation) >= .985):
            continue
        bounds_above = bounds_below = False
        for bx, by, bw, bh, ba in stats[1:]:
            if ba < 5 or bh > .75 * height or not x - .5 * width <= bx + bw / 2 <= x + 1.5 * width:
                continue
            if 0 <= y - (by + bh) <= .75 * height:
                bounds_above = True
            if 0 <= by - (y + height) <= .75 * height:
                bounds_below = True
        if bounds_above and bounds_below:
            directions.append(r'\bigvee' if correlation < 0 else r'\bigwedge')
    if len(directions) != 1 or ambiguous_shapes != 1:
        return latex
    return latex[:match.start()] + directions[0] + latex[match.end():]


def prepare_formula_image(image: Image.Image) -> Image.Image:
    """Remove a thin contrasting screenshot frame without trimming math ink.

    A near-solid outer edge on at least three sides distinguishes a screenshot
    frame from ordinary left/right mathematical delimiters. Background must be
    dominant and removal must remain within a small edge band on every side.
    The model itself handles foreground polarity and internal whitespace.
    """
    pixels = np.asarray(image.convert('L'))
    height, width = pixels.shape
    if min(width, height) < 32:
        return image
    background = float(np.median(pixels))
    if background <= 64:
        mask, contrast = pixels <= 64, pixels >= 192
    elif background >= 192:
        mask, contrast = pixels >= 192, pixels <= 64
    else:
        return image
    edges = (contrast[0, :], contrast[-1, :], contrast[:, 0], contrast[:, -1])
    if mask.mean() < .55 or sum(edge.mean() >= .95 for edge in edges) < 3:
        return image
    rows = np.flatnonzero(mask.mean(axis=1) >= .55)
    columns = np.flatnonzero(mask.mean(axis=0) >= .55)
    if not len(rows) or not len(columns):
        return image
    left, top = int(columns[0]), int(rows[0])
    right, bottom = int(columns[-1]) + 1, int(rows[-1]) + 1
    limit = max(2, min(width, height) // 20)
    if max(left, top, width - right, height - bottom) > limit:
        return image
    return image.crop((left, top, right, bottom))


def pdf_page_image(source: Path, index: int) -> tuple[Image.Image, int]:
    import pymupdf
    with pymupdf.open(source) as document:
        if document.needs_pass:
            raise ValueError('PDF 有密码保护，请先解密并另存。')
        if index < 0 or index >= len(document):
            raise ValueError('PDF 页码超出范围。')
        page = document[index]
        scale = min(2.0, 2400 / max(page.rect.width, page.rect.height))
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        return Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples), len(document)
