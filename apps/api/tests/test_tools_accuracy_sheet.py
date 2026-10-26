"""tools/accuracy_sheet.py: structure rows must pair the same study plan across result sets."""

from __future__ import annotations

import importlib.util
from pathlib import Path

TOOL = Path(__file__).resolve().parents[3] / "tools" / "accuracy_sheet.py"
spec = importlib.util.spec_from_file_location("accuracy_sheet", TOOL)
sheet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sheet)


def node(name, credits=None, children=()):
    return {"name": name, "credits": credits, "children": list(children)}


# ศศ.ม. as the parser reads it: plan → category, with category names repeated per plan
SYSTEM = [
    node("แผน 1 แบบวิชาการ", 36, [node("หมวดวิชาบังคับ", 18), node("หมวดวิชาปริญญานิพนธ์", 12)]),
    node("แผน 2 แบบวิชาชีพ", 36, [node("หมวดวิชาบังคับ", 18), node("หมวดวิชาปริญญานิพนธ์", 3)]),
]


def lookup(model_tree):
    idx = sheet.StructureIndex(sheet.flat_structure(model_tree))
    out = {}
    for key, path, _ in sheet.flat_structure(SYSTEM):
        hit = idx.get(key)
        out[" › ".join(path)] = hit[1]["credits"] if hit else "missing"
    return out


def test_repeated_category_names_keep_their_own_plan() -> None:
    # R1 accuracy test ACC-154: matching by name gave แผน 1's thesis row the 3 of แผน 2
    got = lookup(SYSTEM)
    assert got["แผน 1 แบบวิชาการ › หมวดวิชาปริญญานิพนธ์"] == 12
    assert got["แผน 2 แบบวิชาชีพ › หมวดวิชาปริญญานิพนธ์"] == 3


def test_model_that_nests_category_then_plan_still_pairs() -> None:
    model = [
        node("จำนวนหน่วยกิตตลอดหลักสูตร", 36),
        node("โครงสร้างหลักสูตร", None, [
            node("หมวดวิชาบังคับ", None, [node("แผน 1 แบบวิชาการ", 18), node("แผน 2 แบบวิชาชีพ", 18)]),
            node("หมวดวิชาปริญญานิพนธ์", None, [node("แผน 1 แบบวิชาการ", 12), node("แผน 2 แบบวิชาชีพ", 3)]),
            node("รวมไม่น้อยกว่า", None, [node("แผน 1 แบบวิชาการ", 36), node("แผน 2 แบบวิชาชีพ", 36)]),
        ]),
    ]  # fmt: skip
    got = lookup(model)
    assert got["แผน 1 แบบวิชาการ › หมวดวิชาปริญญานิพนธ์"] == 12
    assert got["แผน 2 แบบวิชาชีพ › หมวดวิชาปริญญานิพนธ์"] == 3
    assert got["แผน 1 แบบวิชาการ"] == 36, "a plan's total pairs with the plan node"


def test_model_without_plans_covers_every_plan_but_not_the_plan_rows() -> None:
    model = [node("จำนวนหน่วยกิตตลอดหลักสูตร", 36), node("หมวดวิชาบังคับ", 18)]
    got = lookup(model)
    assert got["แผน 1 แบบวิชาการ › หมวดวิชาบังคับ"] == 18
    assert got["แผน 2 แบบวิชาชีพ › หมวดวิชาบังคับ"] == 18
    assert got["แผน 1 แบบวิชาการ"] == "missing", "the book total is not a plan's total"
    assert got["แผน 1 แบบวิชาการ › หมวดวิชาปริญญานิพนธ์"] == "missing"
