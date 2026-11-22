import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .config import (
    DEFAULT_ICONS_URL,
    REQUEST_RETRIES,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

SVG_RE = re.compile(r"<svg\b([^>]*)>(.*)</svg>", re.I | re.S)
VIEWBOX_RE = re.compile(r'viewBox\s*=\s*["\']([^"\']+)["\']', re.I)
ID_RE = re.compile(r'\bid\s*=\s*["\']([^"\']+)["\']', re.I)
STYLE_RE = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.I | re.S)
CSS_CLASS_RE = re.compile(r"\.([A-Za-z_][\w-]*)")
IMAGE_RE = re.compile(r"<image\b[^>]*?/?>|<image\b[^>]*>.*?</image>", re.I | re.S)
BAD_IMAGE_HREF_RE = re.compile(
    r'href\s*=\s*["\'](?:file:|[A-Za-z]:[\\/]|[^"\']*Artmain)', re.I
)
XML_RE = re.compile(r"<\?xml[^>]*\?>", re.I)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def safe_id(tag: str) -> str:
    return "i_" + re.sub(r"[^A-Za-z0-9_-]", "_", tag)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def fetch_svg(url: str) -> str:
    last_error = None
    for attempt in range(1, REQUEST_RETRIES + 1):
        # urllib не умеет распаковывать br, поэтому явно просим несжатый ответ
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            last_error = exc
            if attempt < REQUEST_RETRIES:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"не удалось скачать {url}: {last_error}")


def normalize_icon(svg: str, tag: str) -> str:
    svg = XML_RE.sub("", svg)
    svg = COMMENT_RE.sub("", svg)
    match = SVG_RE.search(svg)
    if not match:
        raise ValueError(f"не удалось разобрать SVG иконки {tag}")

    attrs, inner = match.group(1), match.group(2)

    # Часть иконок содержит ссылки на локальные скриншоты автора — убираем их,
    # иначе браузер пытается загрузить file:// и падает ошибками в консоли.
    for image_match in list(IMAGE_RE.finditer(inner)):
        if BAD_IMAGE_HREF_RE.search(image_match.group(0)):
            inner = inner.replace(image_match.group(0), "")

    viewbox_match = VIEWBOX_RE.search(attrs)
    viewbox = viewbox_match.group(1) if viewbox_match else "0 0 140 80"

    symbol_id = safe_id(tag)
    id_map = {
        old_id: f"{symbol_id}__{re.sub(r'[^A-Za-z0-9_-]', '_', old_id)}"
        for old_id in set(ID_RE.findall(inner))
    }
    for old_id, new_id in id_map.items():
        for quote in ('"', "'"):
            inner = inner.replace(f"id={quote}{old_id}{quote}", f"id={quote}{new_id}{quote}")
        inner = inner.replace(f"url(#{old_id})", f"url(#{new_id})")
        inner = inner.replace(f'href="#{old_id}"', f'href="#{new_id}"')
        inner = inner.replace(f"href='#{old_id}'", f"href='#{new_id}'")

    # Стили внутри иконок не должны протекать в другие символы спрайта
    used_classes: set[str] = set()
    for match_style in STYLE_RE.finditer(inner):
        css = match_style.group(2)
        for old_id, new_id in id_map.items():
            css = css.replace(f"#{old_id}", f"#{new_id}")
        classes = set(CSS_CLASS_RE.findall(css))
        used_classes.update(classes)
        for css_class in classes:
            css = re.sub(
                rf"\.{re.escape(css_class)}\b",
                f".{symbol_id}__{css_class}",
                css,
            )
        inner = inner.replace(
            match_style.group(0), match_style.group(1) + css + match_style.group(3)
        )

    for css_class in used_classes:
        for quote in ('"', "'"):
            inner = inner.replace(
                f"class={quote}{css_class}{quote}",
                f"class={quote}{symbol_id}__{css_class}{quote}",
            )

    return f'<symbol id="{symbol_id}" viewBox="{viewbox}">{inner.strip()}</symbol>'


def build_sprite(tags: list[str], destination: Path, base_url: str = DEFAULT_ICONS_URL) -> dict:
    base_url = base_url.rstrip("/")
    unique_tags = sorted({tag for tag in tags if tag})
    results: dict[str, str | None] = {tag: None for tag in unique_tags}

    def load(tag: str):
        try:
            return tag, normalize_icon(fetch_svg(f"{base_url}/{tag}.svg"), tag)
        except Exception as exc:  # одну иконку не блокирует весь спрайт
            return tag, str(exc)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for tag, result in pool.map(load, unique_tags):
            results[tag] = result

    # result — либо '<symbol ...>', либо текст ошибки
    symbols = [result for result in results.values() if result and "<symbol " in result]
    failed = [tag for tag, result in results.items() if not result or "<symbol " not in result]

    sprite = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'style="display:none" aria-hidden="true">'
        + "".join(symbols)
        + "</svg>"
    )
    atomic_write_text(destination, sprite)

    return {"total": len(unique_tags), "built": len(symbols), "failed": failed}
