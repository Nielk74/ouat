"""Local, attributed brand artwork; inline only the marks selected by a report."""

from html import escape
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


ASSETS = Path(__file__).resolve().parents[1] / "assets"
CATALOG = json.loads((ASSETS / "brands/catalog.json").read_text(encoding="utf-8"))
BRANDS = {item["id"]: item for item in CATALOG["icons"]}
BRAND_SURFACES = {"dark": "#141517", "light": "#f4f4f4"}


def luminance(color):
    channels = [int(color[offset:offset+2], 16)/255 for offset in (1, 3, 5)]
    channels = [value/12.92 if value <= .04045 else ((value+.055)/1.055)**2.4 for value in channels]
    return sum(value*weight for value, weight in zip(channels, (.2126, .7152, .0722)))


def contrast_ratio(foreground, background):
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light+.05)/(dark+.05)


def brand_surface(brand):
    item = BRANDS[brand]
    # Multicolor official artwork has a curated surface; a single metadata hex
    # cannot represent the logo's actual colors (e.g. TeamCity's black TC plate).
    if item["provider"] != "Simple Icons":
        return item["surface"]
    return max(BRAND_SURFACES, key=lambda surface: contrast_ratio(item["color"], BRAND_SURFACES[surface]))


SVG_TAGS = {"svg", "g", "defs", "path", "rect", "circle", "ellipse", "line", "polyline",
            "polygon", "linearGradient", "radialGradient", "stop", "clipPath", "mask"}
SVG_ATTRIBUTES = {"id", "d", "x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "r", "rx",
                  "ry", "width", "height", "points", "fill", "fill-rule", "fill-opacity",
                  "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-opacity",
                  "stroke-miterlimit", "stroke-dasharray", "clip-rule", "clip-path", "clipPathUnits",
                  "mask", "maskUnits", "transform", "opacity", "viewBox", "preserveAspectRatio",
                  "gradientUnits", "gradientTransform", "offset", "stop-color", "stop-opacity"}


def symbol(brand):
    """Preserve vector geometry/colors, discard editor metadata, namespace IDs.

    Imported markup is not treated as report text. Whitelisting excludes scripts,
    event handlers, foreign content, remote links, and active CSS from the output.
    """
    item = BRANDS[brand]
    root = ET.fromstring((ASSETS / "brands" / item["file"]).read_text(encoding="utf-8"))
    ids = {node.attrib["id"]: f'brand-{brand}-{node.attrib["id"]}'
           for node in root.iter() if "id" in node.attrib}

    def clean(node):
        tag = node.tag.rsplit("}", 1)[-1]
        if tag not in SVG_TAGS:
            return None
        attributes = dict(node.attrib)
        # The Jenkins source uses inline presentation styles, not style sheets.
        for declaration in attributes.pop("style", "").split(";"):
            key, separator, value = declaration.partition(":")
            if separator and key.strip() in SVG_ATTRIBUTES:
                attributes[key.strip()] = value.strip()
        result = ET.Element(tag)
        for key, value in attributes.items():
            if key not in SVG_ATTRIBUTES:
                continue
            if key == "id":
                value = ids[value]
            if "url(" in value.lower():
                references = re.findall(r"url\(\s*#([^\s)]+)\s*\)", value)
                if not references or any(ref not in ids for ref in references):
                    raise ValueError(f"Unsafe or unresolved SVG reference in {brand}.")
                for ref in references:
                    value = value.replace(f"#{ref}", f"#{ids[ref]}")
                if re.sub(r"url\(\s*#[^\s)]+\s*\)", "", value).strip():
                    raise ValueError(f"Unsupported SVG paint fallback in {brand}.")
            result.set(key, value)
        for child in node:
            cleaned = clean(child)
            if cleaned is not None:
                result.append(cleaned)
        return result

    result = clean(root)
    result.tag = "symbol"
    result.set("id", f"brand-{brand}")
    if "viewBox" not in result.attrib:
        result.set("viewBox", f'0 0 {root.attrib["width"]} {root.attrib["height"]}')
    result.attrib.pop("width", None)
    result.attrib.pop("height", None)
    if item["provider"] == "Simple Icons":
        result.set("fill", item["color"])
    return ET.tostring(result, encoding="unicode")


def selected(data):
    brands = set()
    if isinstance(data, dict):
        if "brand" in data:
            brands.add(data["brand"])
        for value in data.values():
            brands.update(selected(value))
    elif isinstance(data, list):
        for value in data:
            brands.update(selected(value))
    return brands


def sprite(brands):
    if not brands:
        return ""
    symbols = "".join(symbol(brand) for brand in sorted(brands))
    return f'<svg class="brand-sprite" xmlns="http://www.w3.org/2000/svg" width="0" height="0" aria-hidden="true" focusable="false"><defs>{symbols}</defs></svg>'


def credits(brands):
    if not brands:
        return ""
    links = []
    for brand in sorted(brands):
        item = BRANDS[brand]
        source = item.get("attribution", {"label": item["title"], "url": item["source"]})
        label = escape(source["label"])
        link = f'<a href="{escape(source["url"], quote=True)}">{label}</a>'
        if item["license"].get("url"):
            link += f' (<a href="{escape(item["license"]["url"], quote=True)}">{escape(item["license"]["type"])}</a>)'
        if item["provider"] == "Simple Icons":
            link += ' via <a href="https://simpleicons.org/">Simple Icons</a>'
        if item.get("editionNote"):
            link += " · archived mark"
        links.append(link)
    return '<div class="brand-credits">Brand artwork: ' + "; ".join(links) + '. Identification only; no endorsement.</div>'


def catalog_page(entities, ui, kinds):
    cards = []
    for kind, title in kinds.items():
        cards.append(f'<div class="icon-card"><span class="icon-tile"><svg viewBox="0 0 64 64" aria-hidden="true"><use href="#entity-{kind}"/></svg></span><h3>{escape(title)}</h3><code>kind: "{kind}"</code></div>')
    sections = ['<section><h2>Generic components</h2><p>Use a role icon when the product is unknown.</p><div class="icon-grid">' + "".join(cards) + '</div></section>']
    categories = dict.fromkeys(item["category"] for item in CATALOG["icons"])
    for category in categories:
        cards = []
        for item in CATALOG["icons"]:
            if item["category"] != category:
                continue
            brand = item["id"]
            archived = '<span class="archived-mark">Archived mark</span>' if item.get("editionNote") else ""
            cards.append(f'<div class="icon-card"><span class="icon-tile brand-surface-{brand_surface(brand)}"><svg viewBox="0 0 64 64" aria-hidden="true"><use href="#brand-{brand}" x="4" y="4" width="56" height="56"/></svg></span><h3>{escape(item["title"])}</h3><code>brand: "{brand}"</code>{archived}<a href="{escape(item["source"], quote=True)}">Source / brand terms</a></div>')
        sections.append(f'<section><h2>{escape(category)}</h2><div class="icon-grid">' + "".join(cards) + '</div></section>')
    body = entities + ui + sprite(BRANDS)
    body += '<main class="icon-library" id="report"><header><div class="eyebrow">REVIEW REPORT / LOCAL ASSETS</div><h1>Component &amp; brand icons</h1>'
    body += f'<p>{len(BRANDS)} brand marks + {len(kinds)} generic components. Select by name; generated reports embed only the brands they use.</p>'
    body += '<pre><code>{ "kind": "ci-worker", "brand": "teamcity", "label": "Build agent", "status": "changed" }</code></pre>'
    body += '<p class="catalog-note">A logo identifies a product; it does not establish ownership or prove that the project uses it. Preserve source geometry and colors. Some marks are archived; consult the linked brand terms before public reuse. Status stays on the component border, not the logo.</p></header>'
    body += "".join(sections) + credits(BRANDS) + '</main>'
    styles = (ASSETS / "report.css").read_text(encoding="utf-8") + "\n" + (ASSETS / "modern.css").read_text(encoding="utf-8")
    page = (ASSETS / "page.html").read_text(encoding="utf-8")
    values = {"TITLE": "Review report icon library", "STYLE": styles, "BODY": body}
    return re.sub(r"\{\{(TITLE|STYLE|BODY)\}\}", lambda match: values[match[1]], page)
