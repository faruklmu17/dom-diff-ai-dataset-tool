#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from playwright.sync_api import sync_playwright

SAMPLE_RE = re.compile(r"^sample_(\d{3})$")

# --- Simple regex helpers (fast, no external deps) ---
TITLE_RE = re.compile(r"<title>(?P<t>.*?)</title>", re.I | re.S)
H1_RE = re.compile(r"<h1[^>]*>(?P<t>.*?)</h1>", re.I | re.S)
LABEL_RE = re.compile(r"<label[^>]*for=\"(?P<for>[^\"]+)\"[^>]*>(?P<txt>.*?)</label>", re.I | re.S)
INPUT_RE = re.compile(r"<input(?P<attrs>[^>]*)>", re.I)
BUTTON_RE = re.compile(r"<button(?P<attrs>[^>]*)>(?P<txt>.*?)</button>", re.I | re.S)
A_RE = re.compile(r"<a(?P<attrs>[^>]*)>(?P<txt>.*?)</a>", re.I | re.S)
DIV_RE = re.compile(r"<div(?P<attrs>[^>]*)>(?P<txt>.*?)</div>", re.I | re.S)
ID_ATTR_RE = re.compile(r'\bid\s*=\s*"(?P<id>[^"]+)"', re.I)
FOR_ATTR_RE = re.compile(r'\bfor\s*=\s*"(?P<for>[^"]+)"', re.I)
TYPE_ATTR_RE = re.compile(r'\btype\s*=\s*"(?P<type>[^"]+)"', re.I)
ROLE_ATTR_RE = re.compile(r'\brole\s*=\s*"(?P<role>[^"]+)"', re.I)
STYLE_CARD_HINT_RE = re.compile(r"\.card\s*\{(?P<body>.*?)\}", re.I | re.S)
CSS_VALUE_RE = lambda prop: re.compile(rf"{re.escape(prop)}\s*:\s*([^;]+);", re.I)

# style/layout hints we can extract from embedded CSS (best-effort)
CARD_PROPS = ["padding", "border-radius", "box-shadow", "width"]
BTN_PROPS = ["background-color", "padding", "border-radius"]


def strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_attr(attrs: str, name: str) -> Optional[str]:
    # very small extractor
    m = re.search(rf'\b{name}\s*=\s*"([^"]+)"', attrs, re.I)
    return m.group(1) if m else None


def utc_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def find_highest_sample_number(examples_dir: Path) -> int:
    highest = 0
    if not examples_dir.exists():
        return 0
    for p in examples_dir.iterdir():
        if p.is_dir():
            m = SAMPLE_RE.match(p.name)
            if m:
                highest = max(highest, int(m.group(1)))
    return highest


def require_file(path: Path, label: str) -> None:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


@dataclass
class Change:
    type: str
    description: str
    selector: str


@dataclass
class ChangeSummary:
    text_changes: int = 0
    style_changes: int = 0
    layout_changes: int = 0
    elements_added: int = 0
    elements_removed: int = 0
    attribute_changes: int = 0

    def as_dict(self) -> dict:
        return {
            "text_changes": self.text_changes,
            "style_changes": self.style_changes,
            "layout_changes": self.layout_changes,
            "elements_added": self.elements_added,
            "elements_removed": self.elements_removed,
            "attribute_changes": self.attribute_changes,
        }


def extract_title(html: str) -> Optional[str]:
    m = TITLE_RE.search(html)
    return strip_tags(m.group("t")) if m else None


def extract_h1(html: str) -> Optional[str]:
    m = H1_RE.search(html)
    return strip_tags(m.group("t")) if m else None


def extract_labels(html: str) -> Dict[str, str]:
    labels = {}
    for m in LABEL_RE.finditer(html):
        key = m.group("for")
        labels[key] = strip_tags(m.group("txt"))
    return labels


def extract_inputs_by_id(html: str) -> Dict[str, Dict[str, str]]:
    # Map id -> attrs(dict-ish)
    inputs: Dict[str, Dict[str, str]] = {}
    for m in INPUT_RE.finditer(html):
        attrs = m.group("attrs")
        _id = get_attr(attrs, "id")
        if not _id:
            continue
        inputs[_id] = {
            "type": get_attr(attrs, "type") or "",
            "aria-required": get_attr(attrs, "aria-required") or "",
            "aria-describedby": get_attr(attrs, "aria-describedby") or "",
            "minlength": get_attr(attrs, "minlength") or "",
        }
    return inputs


def extract_button_by_id(html: str) -> Dict[str, Dict[str, str]]:
    buttons: Dict[str, Dict[str, str]] = {}
    for m in BUTTON_RE.finditer(html):
        attrs = m.group("attrs")
        _id = get_attr(attrs, "id")
        if not _id:
            continue
        buttons[_id] = {
            "text": strip_tags(m.group("txt")),
            "aria-label": get_attr(attrs, "aria-label") or "",
        }
    return buttons


def extract_links_texts(html: str) -> List[str]:
    out = []
    for m in A_RE.finditer(html):
        out.append(strip_tags(m.group("txt")))
    return [t for t in out if t]


def find_alert_like_divs(html: str) -> List[Tuple[str, str]]:
    # Returns (id, text) for divs with role="alert"
    out = []
    for m in DIV_RE.finditer(html):
        attrs = m.group("attrs")
        role = get_attr(attrs, "role")
        if (role or "").lower() != "alert":
            continue
        _id = get_attr(attrs, "id") or ""
        out.append((_id, strip_tags(m.group("txt"))))
    return out


def extract_css_block(html: str, selector: str) -> Optional[str]:
    # For this dataset, CSS is embedded in <style>. We'll find the block for `.card { ... }` etc.
    if selector == ".card":
        m = STYLE_CARD_HINT_RE.search(html)
        return m.group("body") if m else None
    return None


def extract_css_prop(block: str, prop: str) -> Optional[str]:
    if not block:
        return None
    m = CSS_VALUE_RE(prop).search(block)
    return m.group(1).strip() if m else None


def draft_changes(before_html: str, after_html: str) -> Tuple[List[Change], ChangeSummary]:
    changes: List[Change] = []
    summary = ChangeSummary()

    # Title
    bt = extract_title(before_html)
    at = extract_title(after_html)
    if bt and at and bt != at:
        changes.append(Change("text_change", f"Page title changed from '{bt}' to '{at}'.", "head > title"))
        summary.text_changes += 1

    # Header h1
    bh = extract_h1(before_html)
    ah = extract_h1(after_html)
    if bh and ah and bh != ah:
        changes.append(Change("text_change", f"Header text changed from '{bh}' to '{ah}'.", "body .card h1"))
        summary.text_changes += 1

    # Labels
    bl = extract_labels(before_html)
    al = extract_labels(after_html)

    # Detect label changes for matching semantics: if exact label text changed for same "for"
    for k in sorted(set(bl.keys()) & set(al.keys())):
        if bl[k] != al[k]:
            changes.append(Change("label_change", f"Label '{bl[k]}' changed to '{al[k]}'.", f"label[for='{k}']"))
            summary.text_changes += 1

    # Detect label "for" moved (like username -> email) when label texts match
    # Very simple: if there is a label text present in both but key differs
    inv_bl = {v: k for k, v in bl.items()}
    inv_al = {v: k for k, v in al.items()}
    for text in set(inv_bl.keys()) & set(inv_al.keys()):
        if inv_bl[text] != inv_al[text]:
            changes.append(
                Change(
                    "label_change",
                    f"Label '{text}' moved from for='{inv_bl[text]}' to for='{inv_al[text]}'.",
                    f"label[for='{inv_bl[text]}'] -> label[for='{inv_al[text]}']",
                )
            )
            summary.text_changes += 1

    # Inputs by id + attribute changes
    bi = extract_inputs_by_id(before_html)
    ai = extract_inputs_by_id(after_html)

    before_ids = set(bi.keys())
    after_ids = set(ai.keys())

    # input id changes (heuristic): if an input disappeared and another appeared and their types are similar
    removed_inputs = list(before_ids - after_ids)
    added_inputs = list(after_ids - before_ids)
    # attempt one pairing only if 1-to-1
    if len(removed_inputs) == 1 and len(added_inputs) == 1:
        rid = removed_inputs[0]
        aid = added_inputs[0]
        # call it an id_change only if both look like typical user field types
        changes.append(Change("id_change", f"Input ID changed from '{rid}' to '{aid}'.", f"#{rid} -> #{aid}"))
        summary.attribute_changes += 1
        # remove from further add/remove counting
        removed_inputs = []
        added_inputs = []

    for _id in added_inputs:
        changes.append(Change("element_addition", f"New input added with id '{_id}'.", f"input#{_id}"))
        summary.elements_added += 1

    for _id in removed_inputs:
        changes.append(Change("element_removal", f"Input with id '{_id}' was removed.", f"input#{_id}"))
        summary.elements_removed += 1

    for _id in sorted(before_ids & after_ids):
        b = bi[_id]
        a = ai[_id]
        for key in ["type", "aria-required", "aria-describedby", "minlength"]:
            if (b.get(key) or "") != (a.get(key) or ""):
                if key == "type":
                    changes.append(
                        Change(
                            "attribute_change",
                            f"Input type changed from '{b.get('type')}' to '{a.get('type')}'.",
                            f"#{_id}",
                        )
                    )
                else:
                    # only report meaningful additions/changes
                    if not b.get(key) and a.get(key):
                        changes.append(
                            Change(
                                "attribute_change",
                                f"Input gained attribute {key}='{a.get(key)}'.",
                                f"#{_id}",
                            )
                        )
                    elif b.get(key) and not a.get(key):
                        changes.append(
                            Change(
                                "attribute_change",
                                f"Input attribute {key} was removed (was '{b.get(key)}').",
                                f"#{_id}",
                            )
                        )
                    else:
                        changes.append(
                            Change(
                                "attribute_change",
                                f"Input attribute {key} changed from '{b.get(key)}' to '{a.get(key)}'.",
                                f"#{_id}",
                            )
                        )
                summary.attribute_changes += 1

    # Buttons by id
    bb = extract_button_by_id(before_html)
    ab = extract_button_by_id(after_html)

    bbtn_ids = set(bb.keys())
    abtn_ids = set(ab.keys())

    removed_btn = list(bbtn_ids - abtn_ids)
    added_btn = list(abtn_ids - bbtn_ids)

    # button id change heuristic (same as sample_001)
    if len(removed_btn) == 1 and len(added_btn) == 1:
        old = removed_btn[0]
        new = added_btn[0]
        changes.append(Change("id_change", f"Button ID changed from '{old}' to '{new}'.", f"button#{old} -> button#{new}"))
        summary.attribute_changes += 1
        removed_btn = []
        added_btn = []

    for _id in added_btn:
        changes.append(Change("element_addition", f"New button added with id '{_id}'.", f"button#{_id}"))
        summary.elements_added += 1

    for _id in removed_btn:
        changes.append(Change("element_removal", f"Button with id '{_id}' was removed.", f"button#{_id}"))
        summary.elements_removed += 1

    for _id in sorted(bbtn_ids & abtn_ids):
        if bb[_id]["text"] != ab[_id]["text"]:
            changes.append(
                Change(
                    "text_change",
                    f"Button text changed from '{bb[_id]['text']}' to '{ab[_id]['text']}'.",
                    "button",
                )
            )
            summary.text_changes += 1
        if (bb[_id].get("aria-label") or "") != (ab[_id].get("aria-label") or ""):
            if not bb[_id].get("aria-label") and ab[_id].get("aria-label"):
                changes.append(
                    Change(
                        "attribute_change",
                        f"Button gained aria-label '{ab[_id]['aria-label']}'.",
                        f"button#{_id}",
                    )
                )
                summary.attribute_changes += 1

    # Added link texts (like "Forgot password?")
    blinks = set(extract_links_texts(before_html))
    alinks = set(extract_links_texts(after_html))
    new_links = sorted(alinks - blinks)
    for t in new_links:
        changes.append(Change("element_addition", f"New link added with text '{t}'.", "a"))
        summary.elements_added += 1

    # Alert divs
    balerts = set(find_alert_like_divs(before_html))
    aalerts = set(find_alert_like_divs(after_html))
    if aalerts and not balerts:
        for _id, txt in aalerts:
            sel = f"#{_id}" if _id else "div[role='alert']"
            changes.append(Change("element_addition", f"New alert message added: '{txt}'.", sel))
            summary.elements_added += 1
            summary.text_changes += 1

    # Style/layout hints from CSS blocks (best-effort)
    bcard = extract_css_block(before_html, ".card") or ""
    acard = extract_css_block(after_html, ".card") or ""
    if bcard and acard:
        # layout-ish
        bp = extract_css_prop(bcard, "padding")
        ap = extract_css_prop(acard, "padding")
        if bp and ap and bp != ap:
            changes.append(Change("layout_change", f"Card padding changed ({bp} → {ap}).", ".card"))
            summary.layout_changes += 1
        br = extract_css_prop(bcard, "border-radius")
        ar = extract_css_prop(acard, "border-radius")
        if br and ar and br != ar:
            changes.append(Change("layout_change", f"Card border-radius changed ({br} → {ar}).", ".card"))
            summary.layout_changes += 1

    # button css hints (very light): just detect if the after has a different literal background-color token in CSS
    # (This is intentionally approximate.)
    if "#4285f4" in before_html.lower() and "#0066ff" in after_html.lower():
        changes.append(Change("style_change", "Button background color changed from #4285F4 to #0066FF.", "button"))
        summary.style_changes += 1

    # Cap to keep drafts readable
    return changes[:30], summary


def draft_test_impact(changes: List[Change]) -> List[str]:
    out: List[str] = []

    # ID changes
    for c in changes:
        if c.type == "id_change" and "Button ID changed" in c.description:
            # example: Button ID changed from 'login-btn' to 'signin-btn'.
            m = re.search(r"from '([^']+)' to '([^']+)'", c.description)
            if m:
                out.append(f"Any test using selector '#{m.group(1)}' will fail because the ID changed to '#{m.group(2)}'.")

    # Title/header text
    if any(c.selector == "head > title" for c in changes):
        out.append("Tests asserting the page title will need to be updated to the new title.")
    if any(c.selector == "body .card h1" for c in changes):
        out.append("Tests asserting the main header text will need to be updated to the new header.")

    # Input type / email semantics
    if any("Input type changed" in c.description for c in changes):
        out.append("Form-field tests may need updates if they rely on input type or assume plain text fields.")
    if any("Label 'Username'" in c.description or "moved from for='username'" in c.description for c in changes):
        out.append("Username-based tests may need to be updated to email-based semantics if the field purpose changed.")

    # Visual changes
    if any(c.type in ("style_change", "layout_change") for c in changes):
        out.append("Visual regression tests may detect updated styling/layout (card spacing, button styling, backgrounds).")

    # Accessibility
    if any("aria-" in c.description or "role" in c.description for c in changes):
        out.append("Accessibility-related checks may need to verify new aria/role attributes and label associations.")

    # Added elements
    if any(c.type == "element_addition" for c in changes):
        out.append("New UI elements may require additional assertions (visibility/clickability) or updated snapshots.")

    # Keep it short and similar tone to sample_001
    return out[:6] if out else ["DOM changes may require selector and assertion updates."]


def draft_new_tests(changes: List[Change]) -> List[str]:
    out: List[str] = []

    if any("Input type changed" in c.description and "email" in c.description.lower() for c in changes):
        out.append("Add test to validate email format in the email input field.")

    if any("alert message" in c.description.lower() or "role='alert'" in c.selector for c in changes):
        out.append("Add test to verify validation error/alert message is visible with correct text.")

    if any("New link added" in c.description for c in changes):
        out.append("Add test to verify the new link is visible and clickable.")

    for c in changes:
        if c.type == "id_change" and "Button ID changed" in c.description:
            m = re.search(r"from '([^']+)' to '([^']+)'", c.description)
            if m:
                out.append(f"Update existing flow test to use '#{m.group(2)}' instead of '#{m.group(1)}'.")

    if any(c.type in ("style_change", "layout_change") for c in changes):
        out.append("Add/Update visual regression test to cover new card and button styling.")

    # Keep consistent length
    return out[:5] if out else ["Update existing tests to match new DOM structure and selectors."]


def generate_screenshots(sample_dir: Path, viewport_w: int, viewport_h: int) -> None:
    before = sample_dir / "before.html"
    after = sample_dir / "after.html"
    require_file(before, f"{sample_dir.name}/before.html")
    require_file(after, f"{sample_dir.name}/after.html")

    before_png = sample_dir / "before.png"
    after_png = sample_dir / "after.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": viewport_w, "height": viewport_h})

        page = context.new_page()
        page.goto(before.resolve().as_uri())
        page.wait_for_timeout(1000)
        page.screenshot(path=str(before_png), full_page=True)
        page.close()

        page = context.new_page()
        page.goto(after.resolve().as_uri())
        page.wait_for_timeout(1000)
        page.screenshot(path=str(after_png), full_page=True)
        page.close()

        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", default="examples", help="Examples directory (default: examples)")
    parser.add_argument("--staging", default="staging", help="Staging directory (default: staging)")
    parser.add_argument("--created-by", default="faruk-hasan", help="Metadata created_by (default: faruk-hasan)")
    parser.add_argument("--page-type", default="unknown", help="Annotation/metadata page_type (default: unknown)")
    parser.add_argument("--dom-before", default="v1", help="Metadata dom_version_before (default: v1)")
    parser.add_argument("--dom-after", default="v2", help="Metadata dom_version_after (default: v2)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite if the next sample folder already exists")
    parser.add_argument("--no-screenshots", action="store_true", help="Skip screenshot generation")
    parser.add_argument("--viewport-w", type=int, default=1280, help="Viewport width (default: 1280)")
    parser.add_argument("--viewport-h", type=int, default=720, help="Viewport height (default: 720)")
    args = parser.parse_args()

    examples_dir = Path(args.examples).expanduser()
    staging_dir = Path(args.staging).expanduser()

    before_src = staging_dir / "before.html"
    after_src = staging_dir / "after.html"
    require_file(before_src, "staging/before.html")
    require_file(after_src, "staging/after.html")

    highest = find_highest_sample_number(examples_dir)
    next_n = highest + 1
    sample_id = f"sample_{next_n:03d}"
    sample_dir = examples_dir / sample_id

    if sample_dir.exists():
        if args.overwrite:
            shutil.rmtree(sample_dir)
        else:
            raise FileExistsError(f"{sample_dir} already exists. Use --overwrite to replace it.")

    sample_dir.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(before_src, sample_dir / "before.html")
    shutil.copyfile(after_src, sample_dir / "after.html")

    before_html = (sample_dir / "before.html").read_text(encoding="utf-8", errors="ignore")
    after_html = (sample_dir / "after.html").read_text(encoding="utf-8", errors="ignore")

    dom_changes, summary = draft_changes(before_html, after_html)

    annotation = {
        "sample_id": sample_id,
        "page_type": args.page_type,
        "dom_changes": [c.__dict__ for c in dom_changes],
        "test_impact_analysis": draft_test_impact(dom_changes),
        "new_tests_recommended": draft_new_tests(dom_changes),
    }

    metadata = {
        "sample_id": sample_id,
        "page_type": args.page_type,
        "source": "custom_demo_app",
        "created_by": args.created_by,
        "created_at_utc": utc_now(),
        "dom_version_before": args.dom_before,
        "dom_version_after": args.dom_after,
        "change_summary": summary.as_dict(),
    }

    (sample_dir / "annotation.json").write_text(json.dumps(annotation, indent=2) + "\n", encoding="utf-8")
    (sample_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    if not args.no_screenshots:
        generate_screenshots(sample_dir, args.viewport_w, args.viewport_h)

    print(f"✅ Highest sample found: sample_{highest:03d}" if highest else "✅ No samples found yet (starting from sample_001)")
    print(f"✅ Created: {sample_dir}")
    print("   + annotation.json (draft-filled in sample_001 format)")
    print("   + metadata.json (with change_summary counts)")
    if not args.no_screenshots:
        print("   + before.png / after.png")


if __name__ == "__main__":
    main()
