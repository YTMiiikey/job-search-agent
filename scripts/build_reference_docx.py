"""
Build a pandoc-compatible reference.docx whose styles match the original resume's
visual formatting (Calibri/Tahoma, tight margins, dark-navy blockquotes, etc.).

Run once:
    python scripts/build_reference_docx.py
Output: data/pandoc_reference.docx
"""

import shutil, zipfile
from pathlib import Path
from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
PANDOC_DEFAULT = ROOT / "data" / "_pandoc_default_ref.docx"
OUTPUT = ROOT / "data" / "pandoc_reference.docx"

# Grab pandoc's built-in reference.docx
import subprocess, tempfile, os
tmp = tempfile.mktemp(suffix=".docx")
subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"],
               stdout=open(tmp, "wb"), check=True)
shutil.copy(tmp, PANDOC_DEFAULT)
shutil.copy(tmp, OUTPUT)
os.unlink(tmp)

W  = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

def w(tag):
    return f"{{{W}}}{tag}"

def set_font(rPr, name="Calibri"):
    fonts = rPr.find(w("rFonts"))
    if fonts is None:
        fonts = etree.SubElement(rPr, w("rFonts"))
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs",
                 "w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        qattr = f"{{{W}}}{attr.split(':')[1]}"
        if qattr in fonts.attrib:
            del fonts.attrib[qattr]
    fonts.set(f"{{{W}}}ascii",    name)
    fonts.set(f"{{{W}}}hAnsi",   name)
    fonts.set(f"{{{W}}}eastAsia", name)
    fonts.set(f"{{{W}}}cs",       name)

def set_sz(rPr, half_pts):
    for tag in ("sz", "szCs"):
        el = rPr.find(w(tag))
        if el is None:
            el = etree.SubElement(rPr, w(tag))
        el.set(f"{{{W}}}val", str(half_pts))

def set_color(rPr, hex_color):
    el = rPr.find(w("color"))
    if el is None:
        el = etree.SubElement(rPr, w("color"))
    el.set(f"{{{W}}}val", hex_color)

def remove_bold(rPr):
    for tag in ("b", "bCs"):
        el = rPr.find(w(tag))
        if el is not None:
            rPr.remove(el)

def ensure_rPr(style_el):
    rPr = style_el.find(w("rPr"))
    if rPr is None:
        rPr = etree.SubElement(style_el, w("rPr"))
    return rPr

def ensure_pPr(style_el):
    pPr = style_el.find(w("pPr"))
    if pPr is None:
        pPr = etree.SubElement(style_el, w("pPr"))
    return pPr

def set_spacing(pPr, before=None, after=None, line=None):
    sp = pPr.find(w("spacing"))
    if sp is None:
        sp = etree.SubElement(pPr, w("spacing"))
    if before is not None:
        sp.set(f"{{{W}}}before", str(before))
    if after is not None:
        sp.set(f"{{{W}}}after", str(after))
    if line is not None:
        sp.set(f"{{{W}}}line", str(line))
        sp.set(f"{{{W}}}lineRule", "exact")

def get_style(styles_root, style_id):
    for s in styles_root.findall(w("style")):
        if s.get(f"{{{W}}}styleId") == style_id:
            return s
    return None

# ---- open zip ---------------------------------------------------------------
with zipfile.ZipFile(OUTPUT, "r") as zin:
    names = zin.namelist()
    files = {n: zin.read(n) for n in names}

styles_tree = etree.fromstring(files["word/styles.xml"])
doc_tree    = etree.fromstring(files["word/document.xml"])

# ---- document defaults: Calibri 11pt ----------------------------------------
docDefaults = styles_tree.find(w("docDefaults"))
rPrDef = docDefaults.find(f".//{w('rPr')}")
if rPrDef is None:
    rPrDef = etree.SubElement(etree.SubElement(docDefaults, w("rPrDefault")), w("rPr"))
set_font(rPrDef, "Calibri")
set_sz(rPrDef, 22)   # 11 pt

# ---- page margins -----------------------------------------------------------
# 0.3in left/right (432 twips), 0.4in top/bottom (576 twips)
for pgMar in doc_tree.iter(w("pgMar")):
    pgMar.set(f"{{{W}}}top",    "576")
    pgMar.set(f"{{{W}}}right",  "432")
    pgMar.set(f"{{{W}}}bottom", "576")
    pgMar.set(f"{{{W}}}left",   "432")

# ---- style overrides --------------------------------------------------------

STYLES = {
    # styleId          : (font,       half_pts, bold,  color,    before_twips, after_twips)
    "Normal"           : ("Calibri",  22,       False, None,     0,    0),
    "BodyText"         : ("Calibri",  22,       False, None,     0,    0),
    "FirstParagraph"   : ("Calibri",  22,       False, None,     0,    0),
    "Compact"          : ("Calibri",  21,       False, None,     0,    0),
    # Heading 1 → section headers (SUMMARY, EXPERIENCE…): 12pt bold Calibri, small space before
    "Heading1"         : ("Calibri",  24,       True,  None,     86,   0),
    # Block Text → blockquotes (company name, dates, institution): dark navy
    "BlockText"        : ("Calibri",  22,       False, "243F60", 0,    0),
}

for style_id, (font, sz, bold, color, before, after) in STYLES.items():
    s = get_style(styles_tree, style_id)
    if s is None:
        continue
    rPr = ensure_rPr(s)
    pPr = ensure_pPr(s)
    set_font(rPr, font)
    set_sz(rPr, sz)
    if bold:
        if rPr.find(w("b")) is None:
            etree.SubElement(rPr, w("b"))
        if rPr.find(w("bCs")) is None:
            etree.SubElement(rPr, w("bCs"))
    else:
        remove_bold(rPr)
    if color:
        set_color(rPr, color)
    if before or after:
        set_spacing(pPr, before=before if before else None,
                         after=after  if after  else None)

# ---- write back -------------------------------------------------------------
files["word/styles.xml"] = etree.tostring(styles_tree, xml_declaration=True,
                                           encoding="UTF-8", standalone=True)
files["word/document.xml"] = etree.tostring(doc_tree, xml_declaration=True,
                                              encoding="UTF-8", standalone=True)

with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as zout:
    for name, data in files.items():
        zout.writestr(name, data)

print(f"Written: {OUTPUT}")
