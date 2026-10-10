"""일반 TXT → EPUB 2.0. 실행: streamlit run app.py (Python 3.10+)."""
from __future__ import annotations

import hashlib
import html
import io
import json
import posixpath
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET


STYLES = {"normal": "일반 본문", "system": "시스템창", "game": "게임 채팅", "chat": "메신저",
          "post": "게시글", "reply": "댓글", "letter": "편지·기록", "quote": "인용문"}
PRESETS = {"블루": ("#f0f6fc", "#1a4f8a", "#4a90e2", "#007aff"),
           "다크": ("#252934", "#f2f4f8", "#8a9ab8", "#536dba"),
           "세피아": ("#f7f0e4", "#594736", "#b19a76", "#876d52"),
           "미니멀": ("#f5f5f5", "#303030", "#a0a0a0", "#525252")}
TOC_PRESETS = {"제1화 / 제 1장": r"^\s*(?:(?:외전|특별편)\s*)?제?\s*\d+\s*[화장편](?:\s*[.．:：\-–—].*|\s+.*)?$",
               "숫자만 (1, 01)": r"^\s*\d+\s*$", "숫자와 점 (1. 제목)": r"^\s*\d+\.\s*.*$",
               "#001": r"^\s*#\s*\d+.*$", "Chapter 1": r"^\s*Chapter\s+\d+.*$"}
XML_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def esc(text):
    return html.escape(XML_BAD.sub("", str(text)), quote=True)


@dataclass
class Paragraph:
    id: int
    text: str
    source_line: int
    blank_before: int = 0
    image: str = ""


@dataclass
class Chapter:
    title: str
    subtitle: str = ""
    paragraphs: list[Paragraph] = field(default_factory=list)


@dataclass
class Document:
    chapters: list[Chapter]
    assets: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    cover: bytes | None = None
    warnings: list[str] = field(default_factory=list)
    encoding: str = ""


def decode_txt(data, encoding="자동"):
    if encoding != "자동":
        return data.decode(encoding), encoding
    # UTF-16을 CP949보다 먼저 확인: BOM 파일이 다른 인코딩으로 잘못 읽히지 않게 한다.
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    for name in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return data.decode(name), name
        except UnicodeDecodeError:
            pass
    raise ValueError("텍스트 인코딩을 읽을 수 없습니다. 인코딩을 직접 선택해 주세요.")


def parse_txt(data, title, pattern, *, encoding="자동", paragraph_mode="줄마다", blank_policy="제한 없이",
              blank_toc=False, clean_title=True, remove_title=True, subtitle=False):
    text, detected = decode_txt(data, encoding)
    matcher = re.compile(pattern, re.I) if pattern else None
    lines = text.splitlines()
    chapters, current = [], Chapter("프롤로그")
    pending_blank, next_id, waiting_sub = 0, 1, False
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            pending_blank += 1
            continue
        if remove_title and title and re.sub(r"\s+", "", line).casefold() == re.sub(r"\s+", "", title).casefold():
            continue
        match = matcher.search(line) if matcher else None
        if match and blank_toc:
            # 이름에 맞게 위 AND 아래 모두 빈 줄이어야 한다. 파일 경계는 빈 줄로 본다.
            match = match if (i == 0 or not lines[i-1].strip()) and (i == len(lines)-1 or not lines[i+1].strip()) else None
        if match:
            if current.paragraphs or current.subtitle or current.title != "프롤로그":
                chapters.append(current)
            heading = line[match.start():].strip() if clean_title else line
            if clean_title and title and heading.startswith(title):
                heading = heading[len(title):].lstrip(" -:：.") or heading
            current = Chapter(heading)
            pending_blank, waiting_sub = 0, subtitle
            continue
        if waiting_sub:
            current.subtitle, waiting_sub = line, False
            pending_blank = 0
            continue
        blanks = 0 if blank_policy == "제거" else min(pending_blank, 2) if blank_policy == "최대 2줄" else pending_blank
        if paragraph_mode == "빈 줄마다" and not pending_blank and current.paragraphs:
            current.paragraphs[-1].text += "\n" + line
        else:
            current.paragraphs.append(Paragraph(next_id, line, i+1, blanks))
            next_id += 1
        pending_blank = 0
    if current.paragraphs or current.subtitle or current.title != "프롤로그":
        chapters.append(current)
    if not chapters:
        raise ValueError("변환할 본문이나 목차가 없습니다.")
    warnings = []
    if XML_BAD.search(text):
        warnings.append("XML에서 사용할 수 없는 제어 문자는 EPUB 출력 때 제거됩니다.")
    return Document(chapters, warnings=warnings, encoding=detected)


def normalized_image(data):
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image)
        out = io.BytesIO()
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            image.convert("RGBA").save(out, "PNG")
            return out.getvalue(), "png", "image/png"
        image.convert("RGB").save(out, "JPEG", quality=90)
        return out.getvalue(), "jpg", "image/jpeg"


def parse_epub(data):
    """spine 순서로 본문과 이미지를 추출한다. 복잡한 원본 HTML의 완전 보존용은 아니다."""
    from bs4 import BeautifulSoup, NavigableString
    chapters, assets, warnings = [], {}, ["EPUB은 본문·제목·이미지를 추출해 재구성합니다. 표, 각주 링크, 루비, 원본 레이아웃은 완전히 보존되지 않습니다."]
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(x.file_size for x in z.infolist()) > 300 * 1024 * 1024:
            raise ValueError("EPUB 압축 해제 크기가 300MB를 넘습니다.")
        container = ET.fromstring(z.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile")
        if rootfile is None:
            raise ValueError("EPUB 패키지 파일을 찾을 수 없습니다.")
        opf_path = rootfile.attrib["full-path"]
        base = posixpath.dirname(opf_path)
        opf = ET.fromstring(z.read(opf_path))
        def local_path(href, parent=base):
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc:
                return ""
            return posixpath.normpath(posixpath.join(parent, unquote(parsed.path)))
        manifest = {x.attrib["id"]: x for x in opf.findall(".//{*}manifest/{*}item")}
        spine = opf.findall(".//{*}spine/{*}itemref")
        cover_id = next((m.attrib.get("content") for m in opf.findall(".//{*}meta") if m.attrib.get("name") == "cover"), None)
        cover_item = manifest.get(cover_id) if cover_id else next((x for x in manifest.values() if "cover-image" in x.attrib.get("properties", "").split()), None)
        cover_path = local_path(cover_item.attrib["href"]) if cover_item is not None else ""
        cover = z.read(cover_path) if cover_path else None
        cover_pages = {local_path(x.attrib["href"]) for x in opf.findall(".//{*}guide/{*}reference") if x.attrib.get("type") == "cover"}
        labels = {}
        ncx_item = next((x for x in manifest.values() if x.attrib.get("media-type") == "application/x-dtbncx+xml"), None)
        if ncx_item is not None:
            ncx_path = local_path(ncx_item.attrib["href"])
            ncx = ET.fromstring(z.read(ncx_path))
            for point in ncx.findall(".//{*}navPoint"):
                content, label = point.find("{*}content"), point.find("{*}navLabel/{*}text")
                if content is not None and label is not None:
                    labels.setdefault(local_path(content.attrib.get("src", ""), posixpath.dirname(ncx_path)), label.text or "본문")
        image_map, next_id = {}, 1
        for ref in spine:
            item = manifest.get(ref.attrib.get("idref"))
            if item is None or ref.attrib.get("linear") == "no" or "nav" in item.attrib.get("properties", "").split():
                continue
            path = local_path(item.attrib["href"])
            soup = BeautifulSoup(z.read(path), "html.parser")
            body = soup.body or soup
            for unwanted in body.find_all(["script", "style"]):
                unwanted.decompose()
            heading = body.find(["h1", "h2", "h3", "h4", "h5", "h6"])
            ch_title = heading.get_text(" ", strip=True) if heading else labels.get(path, f"본문 {len(chapters)+1}")
            chapter = Chapter(ch_title)
            buffer, blanks = [], 0
            def flush():
                nonlocal next_id, blanks
                value = "".join(buffer).strip()
                buffer.clear()
                if value:
                    chapter.paragraphs.append(Paragraph(next_id, value, next_id, blanks))
                    next_id += 1
                    blanks = 0
            def walk(node):
                nonlocal next_id, blanks
                if node is heading:
                    return
                if isinstance(node, NavigableString):
                    value = str(node)
                    if value.strip() or buffer:
                        buffer.append(value)
                    return
                name = getattr(node, "name", "")
                if name in ("img", "image"):
                    flush()
                    src = node.get("src") or node.get("xlink:href") or node.get("href") or ""
                    image_path = local_path(src, posixpath.dirname(path))
                    if image_path:
                        try:
                            if image_path not in image_map:
                                payload, ext, media = normalized_image(z.read(image_path))
                                target = f"images/image_{len(image_map)+1}.{ext}"
                                assets[target] = (payload, media)
                                image_map[image_path] = target
                            chapter.paragraphs.append(Paragraph(next_id, "", next_id, blanks, image_map[image_path]))
                            next_id += 1
                            blanks = 0
                        except (KeyError, OSError, ValueError):
                            warnings.append(f"이미지를 읽지 못했습니다: {src}")
                    else:
                        warnings.append("외부 이미지 주소는 EPUB에 포함하지 않았습니다.")
                    return
                if name == "br":
                    buffer.append("\n")
                    return
                block = name in ("p", "div", "section", "article", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "tr")
                if block:
                    flush()
                for child in node.children:
                    walk(child)
                if block:
                    had_text = bool("".join(buffer).strip())
                    flush()
                    if name == "p" and not had_text and not node.find("img"):
                        blanks += 1
            walk(body)
            flush()
            if chapter.paragraphs:
                # 표지만 있는 페이지는 뒤에서 새 표지를 만들므로 중복시키지 않는다.
                if cover_item is not None and len(chapter.paragraphs) == 1 and chapter.paragraphs[0].image and (path in cover_pages or chapter.paragraphs[0].image == image_map.get(cover_path)):
                    continue
                chapters.append(chapter)
    if not chapters:
        raise ValueError("EPUB의 spine에서 읽을 수 있는 본문을 찾지 못했습니다.")
    return Document(chapters, assets, cover, list(dict.fromkeys(warnings)))


def auto_candidates(chapter):
    """강한 패턴만 후보로 제공. 후보는 사용자가 승인하기 전에는 적용되지 않는다."""
    result, ps, i = {}, chapter.paragraphs, 0
    stat = re.compile(r"^(?:이름|레벨|직업|종족|칭호|체력|마력|힘|민첩|지능|상태|HP|MP|LV)\s*[:：]\s*\S", re.I)
    game = re.compile(r"^\s*\{?\[(?:길드|파티|귓속말|귓|팀|친구|친|전체|공지)\]")
    chat = re.compile(r"^[^\n:：]{1,16}[:：]\s*\S")
    while i < len(ps):
        p = ps[i]
        if p.image:
            i += 1
            continue
        group, style, reason, j = [], "", "", i+1
        if re.fullmatch(r"[\[<【]?\s*(?:상태창|캐릭터 정보|능력치)\s*[\]>】]?", p.text):
            while j < len(ps) and not ps[j].image and stat.match(ps[j].text):
                j += 1
            if j - i >= 3:
                group, style, reason = ps[i:j], "system", "상태창 제목과 능력치 2줄 이상"
        elif game.match(p.text):
            while j < len(ps) and not ps[j].image and game.match(ps[j].text):
                j += 1
            group, style, reason = ps[i:j], "game", "[길드]·[파티] 등 채널 표시"
        elif chat.match(p.text) and not stat.match(p.text):
            while j < len(ps) and not ps[j].image and chat.match(ps[j].text) and not stat.match(ps[j].text):
                j += 1
            if j - i >= 3:
                group, style, reason = ps[i:j], "chat", "이름: 메시지 형태가 3줄 이상 연속"
        elif re.fullmatch(r"\[(?:레벨|스킬|퀘스트|알림|시스템|보상|경험치)[^\n]*\]", p.text):
            group, style, reason = [p], "system", "알림 키워드와 대괄호"
        if group:
            gid = f"auto-{group[0].id}"
            for entry in group:
                result[entry.id] = {"style": style, "group": gid, "reason": reason}
            i = j
        else:
            i += 1
    return result


def match_rule(p, rules):
    for index, rule in enumerate(rules):
        if not rule.get("enabled", True):
            continue
        mode, a, b = rule["mode"], rule.get("start", ""), rule.get("end", "")
        matched = False
        if mode == "시작·끝 기호":
            matched = bool(a and b and len(p.text) >= len(a)+len(b) and p.text.startswith(a) and p.text.endswith(b))
        elif mode == "포함 단어":
            matched = bool(a and a in p.text)
        elif mode == "정규식":
            matched = bool(a and re.search(a, p.text))
        if matched:
            # 먼저 원문에서 기호를 자른 뒤 이스케이프한다. < > & 같은 기호도 길이가 정확하다.
            text = p.text[len(a):-len(b)].strip() if mode == "시작·끝 기호" and rule.get("strip") else p.text
            return {"style": rule["style"], "text": text, "group": f"rule-{index}"}
    return {"style": "normal", "text": p.text, "group": ""}


def resolved(p, rules, overrides):
    if p.id in overrides:
        override = overrides[p.id]
        return {"text": p.text, "group": "", **override}
    return match_rule(p, rules)


def make_css(preset="블루", indent=1.0, body_size=1.0, heading_size=1.2, align="justify", palette=None):
    bg, fg, border, accent = palette or PRESETS[preset]
    return f"""@page {{ margin: 5%; }}
body {{ font-family: sans-serif; line-height:1.6; font-size:{body_size}em; }}
h2 {{ text-align:center; font-size:{heading_size}em; margin:3.2em 0 1.8em; font-weight:bold; }}
p {{ text-indent:{indent}em; margin:0 0 .6em; text-align:{align}; }}
.subtitle {{ text-align:center; text-indent:0; font-size:1.05em; margin:-1.2em 0 2em; }}
.blank {{ text-indent:0; margin:0; line-height:1.6; }}
.scene {{ text-align:center; text-indent:0; margin:1.6em 0; }}
.image {{ text-indent:0; text-align:center; }}
img {{ max-width:100%; height:auto; }}
.special {{ text-indent:0; margin:1em .4em; padding:.8em; border:1px solid {border}; }}
.special p {{ text-indent:0; text-align:left; margin:.3em 0; }}
.special .blank {{ margin:0; }}
.system {{ background-color:{bg}; color:{fg}; }}
.system p {{ text-align:center; }}
.game {{ background-color:#1c1c1e; color:#fff; border-left:4px solid {border}; font-family:monospace; font-size:.95em; }}
.guild {{ color:#78e08f; }} .party {{ color:#82ccdd; }} .whisper {{ color:#f8a5c2; }}
.notice {{ color:#fad390; }} .team {{ color:#ff9f43; }} .friend {{ color:#feed6d; }}
.chat {{ border:0; padding:0; }}
.chat .mine {{ text-align:right; }}
.bubble {{ display:inline-block; max-width:75%; background-color:#e9e9eb; color:#111; padding:.5em .8em; border-radius:1em; text-align:left; }}
.mine .bubble {{ background-color:{accent}; color:#fff; }}
.sender {{ display:block; font-size:.8em; color:#686868; margin-bottom:.2em; }}
.post {{ background-color:#fbfbfb; color:#333; }}
.post-title {{ font-weight:bold; border-bottom:1px solid #ddd; padding-bottom:.6em; }}
.reply {{ background-color:#f6f8fa; color:#333; }}
.reply p {{ border-bottom:1px solid #ddd; padding:.3em 0; }}
.letter {{ background-color:{bg}; color:{fg}; font-family:serif; }}
.quote {{ border:0; border-left:3px solid {border}; color:{fg}; background-color:{bg}; }}
.cover {{ text-align:center; }}
"""


def render_chapter(chapter, rules, overrides, *, preserve_blank=True, dialogue_spacing=True, join_subtitle=False):
    title = chapter.title + (" " + chapter.subtitle if join_subtitle and chapter.subtitle else "")
    parts = [f"<h2>{esc(title)}</h2>"]
    if chapter.subtitle and not join_subtitle:
        parts.append(f'<p class="subtitle">{esc(chapter.subtitle)}</p>')
    block, block_key, previous_dialogue = [], None, None
    def flush():
        nonlocal block, block_key
        if not block:
            return
        style = block_key[0]
        chunks = []
        for index, (p, applied) in enumerate(block):
            if index and preserve_blank and p.blank_before:
                chunks.extend(['<p class="blank">&#160;</p>'] * p.blank_before)
            content = esc(applied["text"]).replace("\n", "<br />")
            if style == "chat":
                raw = applied["text"]
                match = re.match(r"^([^\n:：]{1,30})[:：]\s*(.*)$", raw, re.S)
                if match:
                    chunks.append(f'<p><span class="sender">{esc(match[1])}</span><span class="bubble">{esc(match[2]).replace(chr(10), "<br />")}</span></p>')
                else:
                    chunks.append(f'<p class="mine"><span class="bubble">{content}</span></p>')
            elif style == "reply":
                match = re.match(r"^([^\n:：]{1,30})[:：]\s*(.*)$", applied["text"], re.S)
                chunks.append(f'<p><strong>{esc(match[1])}</strong>: {esc(match[2]).replace(chr(10), "<br />")}</p>' if match else f"<p>{content}</p>")
            elif style == "post":
                chunks.append(f'<p class="post-title">{content}</p>' if index == 0 else f"<p>{content}</p>")
            elif style == "game":
                raw = applied["text"].lstrip("{")
                cls = next((v for k, v in {"[길드]":"guild", "[파티]":"party", "[귓":"whisper", "[공지]":"notice", "[시스템]":"notice", "[팀]":"team", "[친":"friend"}.items() if raw.startswith(k)), "")
                chunks.append(f'<p class="{cls}">{content}</p>')
            else:
                chunks.append(f"<p>{content}</p>")
        parts.append(f'<div class="special {style}">{"".join(chunks)}</div>')
        block, block_key = [], None
    for p in chapter.paragraphs:
        applied = resolved(p, rules, overrides)
        style = applied["style"]
        key = (style, applied.get("group", ""))
        if p.image:
            flush()
            parts.append(f'<p class="image"><img src="{esc(p.image)}" alt="본문 이미지" /></p>')
            previous_dialogue = None
            continue
        if style != "normal":
            if block_key != key:
                flush()
                if preserve_blank and p.blank_before:
                    parts.extend(['<p class="blank">&#160;</p>'] * p.blank_before)
                block_key = key
            block.append((p, applied))
            previous_dialogue = None
            continue
        flush()
        content = esc(applied["text"]).replace("\n", "<br />")
        if re.fullmatch(r"\*\s*\*\s*\*", p.text):
            parts.append(f'<p class="scene">{content}</p>')
            previous_dialogue = None
            continue
        dialogue = p.text.startswith(("“", "”", '"', "‘", "’", "'", "-"))
        blanks = p.blank_before if preserve_blank else 0
        if dialogue_spacing and previous_dialogue is not None and previous_dialogue != dialogue:
            blanks = max(blanks, 1)
        parts.extend(['<p class="blank">&#160;</p>'] * blanks)
        parts.append(f"<p>{content}</p>")
        previous_dialogue = dialogue
    flush()
    return "".join(parts)


def xhtml(title, body):
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ko" lang="ko"><head>'
            f'<title>{esc(title)}</title><link href="style.css" rel="stylesheet" type="text/css" />'
            f'</head><body>{body}</body></html>').encode("utf-8")


def build_epub(document, title, author, css, rules, overrides, *, cover_data=None, **render_options):
    identifier = "urn:uuid:" + str(uuid.uuid4())
    files = {"OEBPS/style.css": css.encode("utf-8")}
    manifest = ['<item id="css" href="style.css" media-type="text/css" />', '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />', '<item id="toc" href="toc.xhtml" media-type="application/xhtml+xml" />']
    spine, nav, toc_rows, guide = [], [], [], '<reference type="toc" title="목차" href="toc.xhtml" />'
    cover = cover_data if cover_data is not None else document.cover
    cover_meta = ""
    if cover:
        payload, ext, media = normalized_image(cover)
        cover_name = f"images/cover.{ext}"
        files["OEBPS/"+cover_name] = payload
        files["OEBPS/cover.xhtml"] = xhtml("표지", f'<div class="cover"><img src="{cover_name}" alt="표지" /></div>')
        manifest += [f'<item id="cover-image" href="{cover_name}" media-type="{media}" />', '<item id="cover-page" href="cover.xhtml" media-type="application/xhtml+xml" />']
        spine.append('<itemref idref="cover-page" />')
        cover_meta = '<meta name="cover" content="cover-image" />'
        guide += '<reference type="cover" title="표지" href="cover.xhtml" />'
    for i, (name, (payload, media)) in enumerate(document.assets.items()):
        files["OEBPS/"+name] = payload
        manifest.append(f'<item id="asset-{i}" href="{esc(name)}" media-type="{esc(media)}" />')
    for i, chapter in enumerate(document.chapters, 1):
        display = chapter.title + (" " + chapter.subtitle if render_options.get("join_subtitle") and chapter.subtitle else "")
        filename = f"chapter_{i:04d}.xhtml"
        files["OEBPS/"+filename] = xhtml(display, render_chapter(chapter, rules, overrides, **render_options))
        manifest.append(f'<item id="ch-{i}" href="{filename}" media-type="application/xhtml+xml" />')
        spine.append(f'<itemref idref="ch-{i}" />')
        nav.append(f'<navPoint id="nav-{i}" playOrder="{i}"><navLabel><text>{esc(display)}</text></navLabel><content src="{filename}" /></navPoint>')
        toc_rows.append(f'<li><a href="{filename}">{esc(display)}</a></li>')
    files["OEBPS/toc.xhtml"] = xhtml("목차", '<h2>목차</h2><ol>' + "".join(toc_rows) + '</ol>')
    files["OEBPS/toc.ncx"] = (f'<?xml version="1.0" encoding="UTF-8"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head><meta name="dtb:uid" content="{identifier}" /><meta name="dtb:depth" content="1" /><meta name="dtb:totalPageCount" content="0" /><meta name="dtb:maxPageNumber" content="0" /></head><docTitle><text>{esc(title)}</text></docTitle><navMap>{"".join(nav)}</navMap></ncx>').encode()
    date = datetime.now(timezone.utc).date().isoformat()
    files["OEBPS/content.opf"] = (f'<?xml version="1.0" encoding="UTF-8"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="book-id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="book-id">{identifier}</dc:identifier><dc:title>{esc(title)}</dc:title><dc:language>ko</dc:language><dc:creator>{esc(author)}</dc:creator><dc:date>{date}</dc:date>{cover_meta}</metadata><manifest>{"".join(manifest)}</manifest><spine toc="ncx">{"".join(spine)}</spine><guide>{guide}</guide></package>').encode()
    files["META-INF/container.xml"] = b'<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml" /></rootfiles></container>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("mimetype", b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, payload in files.items():
            z.writestr(name, payload, compress_type=zipfile.ZIP_DEFLATED)
    validate_epub(out.getvalue())
    return out.getvalue()


def validate_epub(data):
    """ZIP/XML/manifest/spine/본문 참조 검사. EPUBCheck 전체 검사를 대체하지 않는다."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        first = z.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
        assert z.read("mimetype") == b"application/epub+zip"
        assert z.testzip() is None
        names = set(z.namelist())
        for name in names:
            if name.endswith((".xml", ".xhtml", ".opf", ".ncx")):
                root = ET.fromstring(z.read(name))
                for node in root.iter():
                    for attr in ("src", "href"):
                        href = node.attrib.get(attr)
                        if href and not urlsplit(href).scheme:
                            target = posixpath.normpath(posixpath.join(posixpath.dirname(name), urlsplit(href).path))
                            assert target in names, f"참조 누락: {name} → {href}"
        opf = ET.fromstring(z.read("OEBPS/content.opf"))
        assert opf.attrib["version"] == "2.0"
        ids = {x.attrib["id"] for x in opf.findall("{*}manifest/{*}item")}
        assert all(x.attrib["idref"] in ids for x in opf.findall("{*}spine/{*}itemref"))


def main():
    import streamlit as st
    st.set_page_config(page_title="TXT EPUB 스타일 제작기", layout="wide")
    st.title("TXT → EPUB 스타일 제작기")
    st.caption("원문을 고치지 않고 문단·범위에 디자인을 적용합니다. EPUB 2.0 출력.")
    uploaded = st.file_uploader("TXT / EPUB 파일", type=["txt", "epub"])
    demo = st.checkbox("예제 텍스트로 먼저 사용해 보기", value=False)
    demo_data = ('제1화. 새로운 시작\n\n그는 창을 바라보았다.\n\n[상태창]\n이름: 김철수\n레벨: 15\n직업: 검사\n\n“이게 내 상태라고?”\n\n[길드] 철수: 출발하자.\n[길드] 영희: 좋아.\n\n철수: 어디야?\n영희: 집이야.\n철수: 곧 갈게.\n\n이 편지를 읽을 때쯤 나는 떠났을 것이다.\n다시 만날 날을 기다리며.\n\n제2화. 약속\n\n그는 길을 나섰다.\n<영희: 조심해!>\n<곧 연락할게.>\n').encode()
    if uploaded:
        data, filename = uploaded.getvalue(), uploaded.name
    elif demo:
        data, filename = demo_data, "예제.txt"
    else:
        st.info("파일을 올리거나 예제 텍스트를 선택해 주세요.")
        return
    source_hash = hashlib.sha256(data).hexdigest()
    is_epub = filename.lower().endswith(".epub")
    # 업로드 교체 시 제목 기본값 갱신. widget 생성 전에만 상태를 바꾼다.
    if st.session_state.get("source_hash") != source_hash:
        st.session_state.source_hash = source_hash
        st.session_state.book_title = Path(filename).stem
        st.session_state.overrides = {}
        st.session_state.revision = 0
    with st.expander("1. 도서 정보와 텍스트 분석", expanded=True):
        title = st.text_input("도서명", key="book_title")
        author = st.text_input("작가명", value="작자미상")
        cover_file = st.file_uploader("표지 이미지 (선택)", type=["jpg", "jpeg", "png", "webp"])
        encoding, mode, blank_policy = "자동", "줄마다", "최대 2줄"
        pattern, blank_toc, clean, remove, sub = None, False, True, True, False
        if not is_epub:
            encoding = st.selectbox("인코딩", ["자동", "utf-8", "utf-8-sig", "cp949", "euc-kr", "utf-16", "utf-16-le", "utf-16-be"])
            mode = st.selectbox("문단 구분", ["줄마다", "빈 줄마다"], help="기본값은 줄마다: 빈 줄 유무가 섞여 있어도 서로 다른 줄을 합치지 않습니다. 빈 줄마다 모드는 같은 문단 안의 줄바꿈을 유지합니다.")
            blank_policy = st.selectbox("원문 빈 줄", ["최대 2줄", "제한 없이", "제거"])
            toc_choice = st.selectbox("목차 인식", list(TOC_PRESETS) + ["기준 단어", "직접 정규식", "분리하지 않음"])
            if toc_choice == "기준 단어":
                word = st.text_input("숫자 뒤 기준 단어", value="화")
                pattern = rf"^(?:(?:외전|특별편)\s*)?(?:제\s*)?\d+\s*{re.escape(word)}(?:\s*[.．:：\-–—].*|\s*$)" if word else None
            elif toc_choice == "직접 정규식":
                pattern = st.text_input("목차 정규식", value=r"^제\s*\d+화.*$")
            else:
                pattern = TOC_PRESETS.get(toc_choice)
            blank_toc = st.checkbox("목차 위와 아래가 모두 빈 줄인 경우에만 인정", value=False)
            clean = st.checkbox("목차에서 일치 지점 앞 공통 제목 제거", value=True)
            remove = st.checkbox("도서명과 같은 줄 제거", value=True)
            sub = st.checkbox("목차 다음 비어 있지 않은 줄을 소제목으로 사용", value=False)
            if sub:
                st.caption("첫 본문 문장을 소제목으로 가져갈 수 있으므로 미리보기에서 확인해 주세요.")
    parse_key = hashlib.sha256(json.dumps([source_hash, is_epub, title if not is_epub else "", encoding, mode, blank_policy, pattern, blank_toc, clean, remove, sub], ensure_ascii=False).encode()).hexdigest()
    try:
        if st.session_state.get("parse_key") != parse_key:
            document = parse_epub(data) if is_epub else parse_txt(data, title, pattern, encoding=encoding, paragraph_mode=mode, blank_policy=blank_policy, blank_toc=blank_toc, clean_title=clean, remove_title=remove, subtitle=sub)
            st.session_state.document = document
            st.session_state.parse_key = parse_key
            st.session_state.overrides = {}
            st.session_state.revision += 1
            st.session_state.pop("epub_result", None)
        document = st.session_state.document
    except (ValueError, re.error, KeyError, OSError, zipfile.BadZipFile, ET.ParseError, UnicodeError) as e:
        st.error(f"파일 분석 실패: {e}")
        return
    st.caption(f"{len(document.chapters)}개 화 · {sum(len(c.paragraphs) for c in document.chapters):,}개 문단" + (f" · {document.encoding}" if document.encoding else ""))
    for warning in document.warnings:
        st.warning(warning)
    with st.expander("2. 디자인과 기호·단어 규칙", expanded=False):
        preset = st.selectbox("전체 디자인 프리셋", list(PRESETS))
        customize = st.checkbox("색상 직접 지정", value=False)
        palette = None
        if customize:
            columns = st.columns(4)
            palette = tuple(columns[i].color_picker(label, value=PRESETS[preset][i], key=f"color-{preset}-{i}") for i, label in enumerate(["상자 배경", "상자 글자", "테두리", "내 메시지 배경"]))
        indent = st.slider("본문 들여쓰기 (em)", 0.0, 2.0, 1.0, 0.1)
        body_size = st.slider("본문 글자 크기 (em)", 0.8, 1.4, 1.0, 0.05)
        heading_size = st.slider("화수 제목 크기 (em)", 1.0, 1.6, 1.2, 0.05)
        align = st.selectbox("본문 정렬", ["justify", "left"], format_func=lambda x: "양쪽 정렬" if x == "justify" else "왼쪽 정렬")
        dialogue = st.checkbox("대사와 서술 전환 시 빈 줄 1줄", value=True)
        join_sub = st.checkbox("목차에 소제목 이어 붙이기", value=False, disabled=not sub)
        st.markdown("**기존 기호 방식 / 포함 단어 / 정규식**")
        st.caption("체크한 규칙은 바로 적용됩니다. 위 규칙이 우선이며, 직접 지정한 문단은 규칙보다 우선합니다. 기호는 원문에서 제거한 후 HTML로 변환합니다.")
        default_rules = [dict(enabled=False, style=s, mode="시작·끝 기호", start=a, end=b, strip=s!="system") for s, a, b in [("system", "[", "]"), ("game", "{", "}"), ("chat", "<", ">"), ("post", "~", "~"), ("reply", "|", "|")]]
        raw_rules = st.data_editor(default_rules, num_rows="dynamic", hide_index=True, key="rules_editor", column_config={
            "enabled": st.column_config.CheckboxColumn("사용"), "style": st.column_config.SelectboxColumn("스타일", options=list(STYLES)),
            "mode": st.column_config.SelectboxColumn("인식 방식", options=["시작·끝 기호", "포함 단어", "정규식"]),
            "start": st.column_config.TextColumn("시작 기호 / 단어 / 정규식"), "end": st.column_config.TextColumn("끝 기호"), "strip": st.column_config.CheckboxColumn("기호 숨기기")})
        st.caption("스타일 코드: " + " / ".join(f"{key}={value}" for key, value in STYLES.items()))
    rules = []
    rule_error = False
    for row in raw_rules:
        if not row.get("enabled"):
            continue
        if row.get("style") not in STYLES or row.get("mode") not in ("시작·끝 기호", "포함 단어", "정규식"):
            st.error("사용할 규칙의 스타일과 인식 방식을 선택해 주세요.")
            rule_error = True
            continue
        row = {**row, "start": row.get("start") or "", "end": row.get("end") or ""}
        if not row["start"] or (row["mode"] == "시작·끝 기호" and not row["end"]):
            st.error("사용할 규칙의 기호나 조건이 비어 있습니다.")
            rule_error = True
            continue
        if row["mode"] == "정규식":
            try:
                re.compile(row["start"])
            except re.error as e:
                st.error(f"정규식 오류: {e}")
                rule_error = True
                continue
        rules.append(row)
    if rule_error:
        return
    css = make_css(preset, indent, body_size, heading_size, align, palette)
    st.subheader("3. 문단 선택과 자동 인식 검토")
    ci = st.selectbox("작업할 화", range(len(document.chapters)), format_func=lambda n: f"{n+1}. {document.chapters[n].title}")
    chapter = document.chapters[ci]
    candidates = auto_candidates(chapter)
    overrides = st.session_state.overrides
    search = st.text_input("본문 검색 (현재 화)", placeholder="꾸밀 문장을 찾아보세요")
    filtered = [p for p in chapter.paragraphs if not search or search.casefold() in p.text.casefold()]
    pages = max(1, (len(filtered)+79)//80)
    page = st.number_input("문단 목록 페이지 (80개씩)", 1, pages, 1, key=f"page-{ci}-{hashlib.sha256(search.encode()).hexdigest()[:8]}")
    shown = filtered[(page-1)*80:page*80]
    st.dataframe([{"번호": p.id, "원본 줄": p.source_line if not is_epub else "—", "빈 줄": p.blank_before,
                   "현재 스타일": STYLES[resolved(p, rules, overrides)["style"]], "자동 후보": STYLES[candidates[p.id]["style"]] if p.id in candidates else "",
                   "본문": p.text if not p.image else "[이미지]"} for p in shown], hide_index=True, width="stretch")
    with st.form("manual_style"):
        choice = st.radio("선택 방법", ["목록에서 여러 문단 선택", "문단 번호 범위"], horizontal=True)
        selected = st.multiselect("문단 선택 (현재 목록)", [p.id for p in shown if not p.image], format_func=lambda n: f"{n}: " + next(p.text[:70] for p in shown if p.id == n))
        c1, c2 = st.columns(2)
        lo = c1.number_input("시작 번호", min_value=1, value=chapter.paragraphs[0].id if chapter.paragraphs else 1)
        hi = c2.number_input("끝 번호", min_value=1, value=chapter.paragraphs[0].id if chapter.paragraphs else 1)
        style = st.selectbox("적용할 디자인", list(STYLES) + ["reset"], format_func=lambda x: "직접 지정 취소 (규칙으로 복귀)" if x == "reset" else STYLES[x])
        submit = st.form_submit_button("선택 부분에 적용")
    if submit:
        ids = selected if choice == "목록에서 여러 문단 선택" else [p.id for p in chapter.paragraphs if lo <= p.id <= hi and not p.image]
        if not ids:
            st.warning("현재 화에서 적용할 문단을 선택해 주세요.")
        else:
            st.session_state.revision += 1
            for pid in ids:
                if style == "reset":
                    overrides.pop(pid, None)
                else:
                    overrides[pid] = {"style": style, "group": f"manual-{st.session_state.revision}"}
            st.rerun()
    with st.expander(f"자동 인식 후보 검토 ({len(candidates)}개 문단)"):
        st.caption("추측이므로 자동 적용하지 않습니다. 각 후보는 원문과 함께 확인한 후 묶음 단위로 선택해 주세요.")
        groups = {}
        for p in chapter.paragraphs:
            if p.id in candidates:
                groups.setdefault(candidates[p.id]["group"], []).append(p)
        group_ids = list(groups)
        for gid in group_ids[:40]:
            ps = groups[gid]
            st.text(f"{ps[0].id}–{ps[-1].id} / {STYLES[candidates[ps[0].id]['style']]} / {candidates[ps[0].id]['reason']}\n" + "\n".join(p.text for p in ps))
        chosen = st.multiselect("적용할 후보 묶음", group_ids, format_func=lambda gid: f"{groups[gid][0].id}–{groups[gid][-1].id}: {groups[gid][0].text[:55]}")
        if len(group_ids) > 40:
            st.caption("본문 표에서는 모든 후보를 확인할 수 있습니다. 이 설명에는 앞 40개 묶음만 표시합니다.")
        if st.button("선택한 자동 후보 적용", disabled=not chosen):
            for gid in chosen:
                for p in groups[gid]:
                    overrides[p.id] = {k: v for k, v in candidates[p.id].items() if k != "reason"}
            st.session_state.revision += 1
            st.rerun()
        if st.button("현재 화의 직접 지정 모두 취소"):
            for p in chapter.paragraphs:
                overrides.pop(p.id, None)
            st.session_state.revision += 1
            st.rerun()
    # 작업 내보내기: 같은 원본과 분석 옵션일 때만 번호 매핑을 복원한다.
    with st.expander("작업 저장 / 불러오기"):
        state = {"version": 1, "source_hash": source_hash, "parse_key": parse_key, "overrides": overrides}
        st.download_button("문단 스타일 작업 저장 (JSON)", json.dumps(state, ensure_ascii=False, indent=2), "epub_style_work.json", "application/json")
        restored = st.file_uploader("저장한 작업 JSON", type=["json"])
        if st.button("작업 불러오기", disabled=restored is None):
            try:
                payload = json.loads(restored.getvalue())
                if payload.get("version") != 1 or payload.get("source_hash") != source_hash or payload.get("parse_key") != parse_key:
                    raise ValueError("원본 파일과 도서명·분석 옵션이 저장할 때와 같아야 합니다.")
                valid_ids = {p.id for c in document.chapters for p in c.paragraphs if not p.image}
                loaded = {}
                for pid, value in payload["overrides"].items():
                    pid = int(pid)
                    if pid not in valid_ids or value.get("style") not in STYLES or not isinstance(value.get("group", ""), str):
                        raise ValueError("작업 파일에 잘못된 문단 또는 스타일이 있습니다.")
                    loaded[pid] = {"style": value["style"], "group": value.get("group", "")}
                st.session_state.overrides = loaded
                st.session_state.revision += 1
                st.rerun()
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                st.error(f"작업 불러오기 실패: {e}")
        st.caption("JSON에는 문단별 지정 결과가 저장됩니다. 디자인·규칙 설정은 다시 선택해 주세요. 분석 옵션을 바꾸면 문단 번호가 바뀌므로 지정 결과는 초기화됩니다.")
    st.subheader("4. 미리보기와 EPUB 다운로드")
    st.caption("현재 목록 페이지에 해당하는 최대 80개 문단을 표시합니다. 브라우저와 실제 전자책 뷰어의 CSS 표현은 다를 수 있습니다.")
    options = dict(preserve_blank=blank_policy!="제거", dialogue_spacing=dialogue, join_subtitle=join_sub)
    preview_chapter = Chapter(chapter.title, chapter.subtitle, shown)
    preview_body = render_chapter(preview_chapter, rules, overrides, **options)
    # 이미지 미리보기에는 파일 대신 data URL을 사용. EPUB 본문에는 원래 파일 참조를 유지한다.
    import base64
    for name, (payload, media) in document.assets.items():
        preview_body = preview_body.replace(f'src="{esc(name)}"', f'src="data:{media};base64,{base64.b64encode(payload).decode()}"')
    st.iframe(f'<!doctype html><html lang="ko"><head><meta charset="utf-8" /><style>{css}</style></head><body>{preview_body}</body></html>', height=650)
    cover_bytes = cover_file.getvalue() if cover_file else None
    output_key = hashlib.sha256(json.dumps([parse_key, title, author, css, rules, overrides, options, hashlib.sha256(cover_bytes).hexdigest() if cover_bytes else None], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if st.button("EPUB 2.0 생성", type="primary", disabled=not title.strip() or not author.strip()):
        try:
            with st.spinner("전체 화를 변환하고 파일 구조를 검사합니다…"):
                epub_data = build_epub(document, title.strip(), author.strip(), css, rules, overrides, cover_data=cover_bytes, **options)
            st.session_state.epub_result = (output_key, epub_data)
        except (ValueError, OSError, AssertionError, ET.ParseError) as e:
            st.error(f"EPUB 생성 실패: {e}")
    result = st.session_state.get("epub_result")
    if result and result[0] == output_key:
        st.success("EPUB 2.0 생성 완료 · ZIP/XML/본문 참조 검사 통과")
        safe_name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", title).strip(". ") or "book"
        st.download_button("EPUB 다운로드", result[1], f"{safe_name}.epub", "application/epub+zip")
    elif result:
        st.info("설정이 바뀌었습니다. EPUB을 다시 생성해 주세요.")


if __name__ == "__main__":
    main()
