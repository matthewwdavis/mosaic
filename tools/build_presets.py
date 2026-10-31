"""Convert DrawingML's presetShapeDefinitions.xml into figassemble/data/presets.json.

The XML is published with the Office Open XML standard (ECMA-376 Part 1, "DrawingML
geometries"); LibreOffice keeps a copy at oox/source/drawingml/customshapes/. Run:

    python tools/build_presets.py path/to/presetShapeDefinitions.xml

The JSON keeps, for each of the 187 presets, its adjust values (avLst), guide formulas
(gdLst), adjust handles (ahLst), text rectangle and paths; connection sites are dropped.
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "figassemble" / "data" / "presets.json"


def local(tag: str) -> str:
    return tag.split("}")[-1]


def guides(el) -> list:
    return [[g.get("name"), " ".join(g.get("fmla", "val 0").split())] for g in el]


def handle(el) -> dict:
    pos = next(p for p in el.iter() if local(p.tag) == "pos")
    h = {"kind": "xy" if local(el.tag) == "ahXY" else "polar", "pos": [pos.get("x"), pos.get("y")]}
    h.update({k: v for k, v in el.attrib.items()})
    return h


def path(el) -> dict:
    out = {"cmds": []}
    for k in ("w", "h"):
        if el.get(k):
            out[k] = float(el.get(k))
    out["fill"] = el.get("fill", "norm")
    out["stroke"] = el.get("stroke", "true") not in ("false", "0")
    for c in el:
        t = local(c.tag)
        pts = [[p.get("x"), p.get("y")] for p in c if local(p.tag) == "pt"]
        if t == "moveTo":
            out["cmds"].append(["M", *pts[0]])
        elif t == "lnTo":
            out["cmds"].append(["L", *pts[0]])
        elif t == "cubicBezTo":
            out["cmds"].append(["C", *pts[0], *pts[1], *pts[2]])
        elif t == "quadBezTo":
            out["cmds"].append(["Q", *pts[0], *pts[1]])
        elif t == "arcTo":
            out["cmds"].append(["A", c.get("wR"), c.get("hR"), c.get("stAng"), c.get("swAng")])
        elif t == "close":
            out["cmds"].append(["Z"])
        else:
            raise ValueError(f"unknown path command {t}")
    return out


def main(src: str) -> None:
    root = ET.parse(src).getroot()
    presets = {}
    for shape in root:
        d = {"av": [], "gd": [], "ah": [], "paths": []}
        for sec in shape:
            t = local(sec.tag)
            if t == "avLst":
                d["av"] = guides(sec)
            elif t == "gdLst":
                d["gd"] = guides(sec)
            elif t == "ahLst":
                d["ah"] = [handle(a) for a in sec]
            elif t == "rect":
                d["rect"] = [sec.get(k) for k in ("l", "t", "r", "b")]
            elif t == "pathLst":
                d["paths"] = [path(p) for p in sec]
        presets[local(shape.tag)] = d
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(presets, separators=(",", ":"), sort_keys=True) + "\n")
    print(f"{len(presets)} presets -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1])
