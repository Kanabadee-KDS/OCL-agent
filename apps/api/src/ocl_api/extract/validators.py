"""Deterministic consistency checks over extracted parts (never the LLM's opinion)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ocl_api.extract.base import Check


def _sum_children(nodes: list[dict[str, Any]]) -> int:
    return sum(int(n.get("credits") or 0) for n in nodes)


def _squash(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()


def _info_checks(info: dict[str, Any], st: dict[str, Any]) -> list[Check]:
    out: list[Check] = []
    v = info.get("values") or {}
    metas = info.get("meta") or {}
    labels = {f["key"]: f["label"] for f in info.get("fields") or []}
    missing = info.get("missing_required") or []
    out.append(
        Check(
            "info_required",
            "warn" if missing else "pass",
            "ฟิลด์บังคับที่ยังว่าง: " + ", ".join(labels.get(k, k) for k in missing)
            if missing
            else "ฟิลด์บังคับของข้อมูลหลักครบ (ชื่อ ระดับ ปริญญา หน่วยกิต ปีที่เริ่มใช้)",
            "info",
        )
    )
    code = v.get("program_code")
    if code is None:
        out.append(Check("program_code_format", "warn", "เล่มยังไม่ระบุรหัสหลักสูตร สกอ.", "info"))
    elif re.fullmatch(r"\d{14}", str(code)):
        out.append(
            Check("program_code_format", "pass", f"รหัสหลักสูตร สกอ. {code} ครบ 14 หลัก", "info")
        )
    else:
        out.append(
            Check("program_code_format", "fail", f"รหัสหลักสูตร '{code}' ไม่ใช่ตัวเลข 14 หลัก", "info")
        )
    total_info, total_st = v.get("total_credits"), st.get("total_credits")
    if total_info is not None and total_st is not None:
        same = int(total_info) == int(total_st)
        out.append(
            Check(
                "info_credits_match",
                "pass" if same else "fail",
                f"หน่วยกิตหมวดที่ 1 ข้อ 4 ({total_info}) "
                + ("= " if same else "≠ ")
                + f"โครงสร้างหมวดที่ 4 ({total_st})",
                "info",
            )
        )
    field, deg_th, deg_en, name_en = (
        v.get("field_of_study"),
        v.get("degree_full_th"),
        v.get("degree_full_en"),
        v.get("name_en"),
    )
    if field and deg_th:
        ok_th = _squash(field) in _squash(deg_th)
        m = re.search(r"\((.+?)\)", deg_en or "")
        ok_en = not (m and name_en) or _squash(m.group(1)) in _squash(name_en)
        out.append(
            Check(
                "name_consistent",
                "pass" if ok_th and ok_en else "warn",
                "สาขาวิชาในชื่อหลักสูตรตรงกับชื่อปริญญา (ไทย/อังกฤษ)"
                if ok_th and ok_en
                else "สาขาวิชาในชื่อหลักสูตรไม่ตรงกับชื่อปริญญา: "
                + (f"ไทย '{field}' ∉ '{deg_th}'" if not ok_th else "")
                + (" · " if not ok_th and not ok_en else "")
                + (f"อังกฤษ '{m.group(1)}' ∉ '{name_en}'" if not ok_en and m else ""),
                "info",
            )
        )
    if v.get("start_year"):
        out.append(
            Check(
                "next_revision",
                "info",
                f"เริ่มใช้ปีการศึกษา {v['start_year']} → "
                f"ครบรอบปรับปรุงหลักสูตร พ.ศ. {int(v['start_year']) + 5}",
                "info",
            )
        )
    inferred = [
        labels.get(k, k) for k, m in metas.items() if m.get("inferred") and v.get(k) is not None
    ]
    if inferred:
        out.append(
            Check(
                "info_inferred",
                "info",
                f"ระบบอนุมานเอง {len(inferred)} ฟิลด์ ต้องให้คนยืนยัน: " + ", ".join(inferred),
                "info",
            )
        )
    return out


def _ksec_checks(ks: dict[str, Any], plos: list[dict[str, Any]]) -> list[Check]:
    out: list[Check] = []
    kplos = ks.get("plos") or []
    n = ks.get("count") or 0
    out.append(
        Check(
            "ksec_present",
            "pass" if n else "fail",
            f"พบ KSEC {n} รายการใน {len(kplos)} PLO"
            + (f" ({len(ks.get('plans') or [])} แผน)" if ks.get("plans") else "")
            if n
            else "ไม่พบตาราง PLO × ด้าน K/S/E/C ในหมวดที่ 3",
            "ksec",
        )
    )
    if n and plos:
        have = {p["code"] for p in kplos}
        missing = [
            p["code"]
            for p in plos
            if not any(h == p["code"] or h.startswith(p["code"] + ".") for h in have)
        ]
        out.append(
            Check(
                "ksec_vs_plo",
                "warn" if missing else "pass",
                f"PLO ที่ไม่มีแถวในตาราง KSEC: {', '.join(missing)}"
                if missing
                else "ทุก PLO ของหมวดที่ 3 มีรายการ KSEC",
                "ksec",
            )
        )
    cross = [
        f"{it['code']}@{p['code']}"
        for p in kplos
        for it in p.get("items") or []
        if re.match(r"[KSEC](\d+)", it["code"])
        and re.match(r"[KSEC](\d+)", it["code"]).group(1)
        != re.sub(r"\D", "", p["code"].split(".")[0])
    ]
    if cross:
        out.append(
            Check(
                "ksec_cross_plo",
                "info",
                f"รหัสที่อ้างข้าม PLO {len(cross)} รายการ (เล่มใช้ซ้ำได้) เช่น {', '.join(cross[:6])}",
                "ksec",
            )
        )
    odd = [
        it["code"]
        for p in kplos
        for it in p.get("items") or []
        if (it.get("meta") or {}).get("note")
    ]
    if odd:
        out.append(
            Check(
                "ksec_column_mismatch",
                "warn",
                f"รหัสอยู่ผิดคอลัมน์ด้าน {len(odd)} รายการ: {', '.join(odd[:8])}",
                "ksec",
            )
        )
    return out


def _mapping42_checks(mp: dict[str, Any], ks: dict[str, Any]) -> list[Check]:
    out: list[Check] = []
    krows = mp.get("ksec_rows") or []
    rows41 = {r["course_code"]: set(r.get("plos") or []) for r in mp.get("rows") or []}
    known = set(ks.get("codes") or [])
    if known:
        used = {c for r in krows for c in r.get("ksec_codes") or []}
        unknown = sorted(used - known)
        out.append(
            Check(
                "mapping_ksec_unknown",
                "warn" if unknown else "pass",
                f"รหัสใน Mapping 4.2 ที่ไม่มีในตาราง KSEC หมวดที่ 3 ({len(unknown)}): "
                + ", ".join(unknown[:10])
                if unknown
                else f"รหัส KSEC ใน Mapping 4.2 ทั้ง {len(used)} รหัสมีในหมวดที่ 3",
                "mapping",
            )
        )
    if rows41:
        c42 = {r["course_code"] for r in krows}
        only41 = sorted(set(rows41) - c42)
        only42 = sorted(c42 - set(rows41))
        out.append(
            Check(
                "ksec_unmapped",
                "warn" if (only41 or only42) else "pass",
                (f"อยู่ใน 4.1 แต่ไม่อยู่ใน 4.2 {len(only41)}: {', '.join(only41[:6])}" if only41 else "")
                + (" · " if only41 and only42 else "")
                + (
                    f"อยู่ใน 4.2 แต่ไม่อยู่ใน 4.1 {len(only42)}: {', '.join(only42[:6])}"
                    if only42
                    else ""
                )
                or "รายวิชาใน Mapping 4.1 และ 4.2 ตรงกัน",
                "mapping",
            )
        )
        diff = [
            r["course_code"]
            for r in krows
            if r["course_code"] in rows41 and set(r.get("plos") or []) != rows41[r["course_code"]]
        ]
        out.append(
            Check(
                "mapping_42_vs_41",
                "warn" if diff else "pass",
                f"PLO ที่รายวิชารับผิดชอบใน 4.2 ไม่ตรงกับจุด ● ใน 4.1 {len(diff)} วิชา: "
                + ", ".join(diff[:8])
                if diff
                else "PLO ของทุกรายวิชาใน 4.2 ตรงกับจุด ● ใน 4.1",
                "mapping",
            )
        )
    return out


def _approval_checks(ap: dict[str, Any], info: dict[str, Any]) -> list[Check]:
    out: list[Check] = []
    rows = ap.get("approvals") or []
    done = [a for a in rows if not a.get("pending")]
    if not rows:
        out.append(Check("approval_present", "fail", "ไม่พบบรรทัด 'ได้รับอนุมัติ/เห็นชอบ' ในข้อ 13", "appr"))
        return out
    out.append(
        Check(
            "approval_present",
            "pass",
            f"พบมติอนุมัติ {len(done)} ระดับ (ฟอร์มมี {len(rows)} บรรทัด)",
            "appr",
        )
    )
    missing = ap.get("missing_levels") or []
    blank = [a["level"] for a in rows if a.get("pending")]
    no_date = [a["level"] for a in done if not a.get("date")]
    if missing or no_date:
        out.append(
            Check(
                "approval_complete",
                "warn",
                (f"ยังไม่มีมติ: {', '.join(missing)}" if missing else "")
                + (" · " if missing and no_date else "")
                + (f"มีครั้งที่แต่อ่านวันที่ไม่ได้: {', '.join(no_date)}" if no_date else "")
                + (f" (เล่มเว้นว่าง: {', '.join(blank)})" if blank else ""),
                "appr",
            )
        )
    else:
        out.append(Check("approval_complete", "pass", "มติครบทุกระดับที่ฟอร์มกำหนด", "appr"))
    order = ["committee", "academic_council", "university_council"]
    dated = [(a["level_key"], a["date"]["iso"]) for a in done if a.get("date")]
    seq = [iso for key in order for k, iso in dated if k == key or k.startswith(key + "_")]
    if len(seq) >= 2:
        ok = all(a <= b for a, b in zip(seq, seq[1:], strict=False))
        out.append(
            Check(
                "approval_order",
                "pass" if ok else "warn",
                "วันที่ประชุมเรียงตามลำดับ คณะกรรมการ → สภาวิชาการ → สภามหาวิทยาลัย"
                if ok
                else "วันที่ประชุมไม่เรียงตามลำดับระดับ: " + " → ".join(seq),
                "appr",
            )
        )
    uni = next((a for a in done if a["level_key"] == "university_council" and a.get("date")), None)
    if uni and ap.get("start_year"):
        sem = ap.get("start_semester") or 1
        start_iso = f"{int(ap['start_year']) - 543:04d}-{'08' if sem == 1 else '01'}-01"
        late = uni["date"]["iso"] > start_iso
        out.append(
            Check(
                "approval_vs_start",
                "warn" if late else "pass",
                f"สภามหาวิทยาลัยอนุมัติ {uni['date']['text']} "
                + ("หลัง" if late else "ก่อน")
                + f"เริ่มใช้ภาค {sem}/{ap['start_year']}",
                "appr",
            )
        )
    iv = info.get("values") or {}
    if iv.get("start_year") and ap.get("start_year") and iv["start_year"] != ap["start_year"]:
        out.append(
            Check(
                "approval_vs_info",
                "warn",
                f"ปีที่เริ่มใช้ในข้อ 13 ({ap['start_year']}) ≠ ข้อมูลหลัก ({iv['start_year']})",
                "appr",
            )
        )
    return out


def _teacher_checks(tc: dict[str, Any], info: dict[str, Any]) -> list[Check]:
    out: list[Check] = []
    rows = tc.get("teachers") or []
    if not rows:
        out.append(Check("teachers_present", "fail", "ไม่พบตารางอาจารย์ในข้อ 11–12", "teachers"))
        return out
    resp = [t for t in rows if t.get("responsible")]
    out.append(
        Check(
            "teachers_present",
            "pass",
            f"อาจารย์ประจำหลักสูตร {len(rows)} คน · ผู้รับผิดชอบ {len(resp)} คน",
            "teachers",
        )
    )
    level = (info.get("values") or {}).get("level")
    grad = level in ("ป.โท", "ป.เอก", "ป.บัณฑิต", "ป.บัณฑิตชั้นสูง")
    groups = tc.get("groups") or []
    if groups:
        need = 3
        per = {g: sum(1 for t in resp if t.get("group") == g) for g in groups}
        short = [f"{g} {n}" for g, n in per.items() if n < need]
        msg = "ผู้รับผิดชอบต่อวิชาเอก: " + ", ".join(f"{g} {n}" for g, n in per.items())
    else:
        need = 3 if grad else 5
        short = [] if len(resp) >= need else [f"มี {len(resp)}"]
        msg = f"ผู้รับผิดชอบ {len(resp)} คน"
    out.append(
        Check(
            "teacher_count",
            "warn" if short else "pass",
            msg
            + f" (เกณฑ์ ≥ {need}{' ต่อวิชาเอก' if groups else ''} [สมมติ ตามเกณฑ์ อว. 2565])"
            + (f" · ไม่ครบ: {', '.join(short)}" if short else ""),
            "teachers",
        )
    )
    if grad:
        weak = [
            t["name"]
            for t in resp
            if t.get("highest_level") != "เอก" and (t.get("rank") or "") not in ("รศ.", "ศ.")
        ]
    else:
        weak = [t["name"] for t in resp if t.get("highest_level") == "ตรี"]
    out.append(
        Check(
            "teacher_qualification",
            "warn" if weak else "pass",
            ("ผู้รับผิดชอบที่ไม่มีวุฒิเอกและไม่ใช่ รศ./ศ.: " if grad else "ผู้รับผิดชอบที่มีวุฒิสูงสุดระดับตรี: ")
            + ", ".join(weak)
            if weak
            else ("ผู้รับผิดชอบทุกคนมีวุฒิเอกหรือเป็น รศ./ศ." if grad else "ผู้รับผิดชอบทุกคนมีวุฒิโทขึ้นไป")
            + " [สมมติ]",
            "teachers",
        )
    )
    only11 = tc.get("responsible_only_in_11") or []
    if only11:
        out.append(
            Check(
                "teacher_11_vs_12",
                "warn",
                "ชื่อในข้อ 11 ที่ไม่พบในข้อ 12: " + ", ".join(only11),
                "teachers",
            )
        )
    names = [re.sub(r"\s+", "", t["name"]) for t in rows]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        out.append(Check("teacher_duplicate", "warn", "ชื่อซ้ำในตาราง: " + ", ".join(dup), "teachers"))
    odd = [t["name"] for t in rows if (t.get("meta") or {}).get("note")]
    if odd:
        out.append(
            Check(
                "teacher_fields",
                "info",
                f"แยกวุฒิ/สถาบันได้ไม่ครบ {len(odd)} คน (ตรวจในชีท): " + ", ".join(odd[:5]),
                "teachers",
            )
        )
    return out


def _plan_checks(pl: dict[str, Any], info: dict[str, Any]) -> list[Check]:
    out: list[Check] = []
    plans = pl.get("plans") or []
    if not plans:
        out.append(Check("plan_present", "fail", "ไม่พบตารางแผนการรับนิสิตในหมวดที่ 2 ข้อ 4", "plan"))
        return out
    out.append(
        Check(
            "plan_present",
            "pass",
            f"แผนการรับนิสิต {len(plans)} ตาราง · รับปีละ {pl.get('intake_per_year')} คน · "
            f"ปี {plans[0]['years'][0]}–{plans[0]['years'][-1]}",
            "plan",
        )
    )
    bad = []
    for p in plans:
        if not p.get("total"):
            continue
        for k, y in enumerate(p["years"]):
            s = sum(r["values"][k] for r in p["rows"])
            if s != p["total"][k]:
                bad.append(f"{p.get('name') or 'แผน'} ปี {y}: {s} ≠ รวม {p['total'][k]}")
    out.append(
        Check(
            "plan_totals",
            "warn" if bad else "pass",
            "; ".join(bad[:4]) if bad else "แถวรวมตรงกับผลบวกของชั้นปีทุกปี",
            "plan",
        )
    )
    iv = info.get("values") or {}
    if iv.get("start_year") and plans[0]["years"]:
        same = str(iv["start_year"]) == str(plans[0]["years"][0])
        out.append(
            Check(
                "plan_vs_start",
                "pass" if same else "warn",
                f"ปีแรกของแผนรับ {plans[0]['years'][0]} "
                + ("= " if same else "≠ ")
                + f"ปีที่เริ่มใช้หลักสูตร {iv['start_year']}",
                "plan",
            )
        )
    if iv.get("duration_years") and pl.get("duration_years"):
        same = int(iv["duration_years"]) == int(pl["duration_years"])
        out.append(
            Check(
                "plan_vs_duration",
                "pass" if same else "warn",
                f"จำนวนชั้นปีในแผนรับ {pl['duration_years']} "
                + ("= " if same else "≠ ")
                + f"ระยะเวลาหลักสูตร {iv['duration_years']} ปี",
                "plan",
            )
        )
    m = (pl.get("meta") or {}).get("teaching_modes") or {}
    if m.get("inferred"):
        out.append(
            Check(
                "teaching_modes_inferred",
                "info",
                "รูปแบบการสอน "
                + " · ".join(pl.get("teaching_modes") or [])
                + " อนุมานโดยระบบ ต้องให้คนยืนยัน",
                "plan",
            )
        )
    return out


def _module_checks(md: dict[str, Any], crs: dict[str, Any]) -> list[Check]:
    out: list[Check] = []
    mods = md.get("modules") or []
    if not mods:
        out.append(Check("modules_present", "fail", "ไม่พบชุดวิชาในหมวดที่ 4 ข้อ 2–3", "modules"))
        return out
    out.append(Check("modules_present", "pass", f"พบชุดวิชา {len(mods)} ชุด", "modules"))
    bad = []
    checked = 0
    for g in md.get("groups") or []:
        if not g.get("declared_modules") or "เลือก" in g["name"]:
            continue  # an elective group declares how many to choose, not how many it lists
        majors = sorted({m.get("major") for m in mods if m.get("group") == g["name"]}, key=str)
        for mj in majors:
            n = sum(1 for m in mods if m.get("group") == g["name"] and m.get("major") == mj)
            checked += 1
            if n != g["declared_modules"]:
                label = g["name"] + (f" ({mj})" if mj else "")
                bad.append(f"{label}: พบ {n} ≠ ระบุ {g['declared_modules']}")
    if checked:
        out.append(
            Check(
                "modules_vs_declared",
                "warn" if bad else "pass",
                "; ".join(bad) if bad else "จำนวนชุดวิชาบังคับตรงกับที่กลุ่มระบุ",
                "modules",
            )
        )
    no_desc = [m["name_th"] for m in mods if not m.get("description_th")]
    no_codes = [m["name_th"] for m in mods if not m.get("course_codes")]
    out.append(
        Check(
            "modules_fields",
            "warn" if (no_desc or no_codes) else "pass",
            (f"ไม่มีคำอธิบาย {len(no_desc)} ชุด: {', '.join(no_desc[:3])}" if no_desc else "")
            + (" · " if no_desc and no_codes else "")
            + (f"ไม่มีรายวิชา {len(no_codes)} ชุด: {', '.join(no_codes[:3])}" if no_codes else "")
            or "ทุกชุดวิชามีคำอธิบายและรายวิชา",
            "modules",
        )
    )
    courses = crs.get("courses") or []
    if courses:
        known = {c.get("code_th") for c in courses}
        in_mods = [c for m in mods for c in m.get("course_codes") or []]
        unknown = sorted({c for c in in_mods if c not in known})
        dup = sorted({c for c in in_mods if in_mods.count(c) > 1})
        out.append(
            Check(
                "modules_vs_courses",
                "warn" if (unknown or dup) else "pass",
                (f"รหัสในชุดวิชาที่ไม่อยู่ในรายวิชา: {', '.join(unknown[:6])}" if unknown else "")
                + (" · " if unknown and dup else "")
                + (f"รหัสอยู่ในหลายชุดวิชา: {', '.join(dup[:6])}" if dup else "")
                or f"รายวิชาในชุดวิชา {len(set(in_mods))} รหัส อยู่ในรายการรายวิชาทั้งหมด",
                "modules",
            )
        )
        credit_bad = []
        by_code = {c.get("code_th"): c.get("credits") or 0 for c in courses}
        for m in mods:
            if m.get("credits") and m.get("course_codes"):
                s = sum(by_code.get(c, 0) for c in m["course_codes"])
                if s != m["credits"]:
                    credit_bad.append(f"{m['name_th'][:30]}: รายวิชารวม {s} ≠ {m['credits']}")
        if any(m.get("credits") for m in mods):
            out.append(
                Check(
                    "modules_credits",
                    "warn" if credit_bad else "pass",
                    "; ".join(credit_bad[:4]) if credit_bad else "หน่วยกิตชุดวิชาตรงกับผลรวมรายวิชา",
                    "modules",
                )
            )
    listed = md.get("listed_in_item2") or []
    if listed and len(listed) != len(mods):
        out.append(
            Check(
                "modules_2_vs_3",
                "info",
                f"ชุดวิชาในข้อ 2 มี {len(listed)} ชุด แต่ข้อ 3 มี {len(mods)} ชุด",
                "modules",
            )
        )
    return out


def run_checks(parts: dict[str, dict[str, Any]]) -> list[Check]:
    checks: list[Check] = []
    st = parts.get("structure") or {}
    plo = parts.get("plo") or {}
    crs = parts.get("courses") or {}
    info = parts.get("info") or {}
    if info:
        checks += _info_checks(info, st)
    ap = parts.get("appr") or {}
    if ap:
        checks += _approval_checks(ap, info)
    tc = parts.get("teachers") or {}
    if tc:
        checks += _teacher_checks(tc, info)
    pl = parts.get("plan") or {}
    if pl:
        checks += _plan_checks(pl, info)
    md = parts.get("modules") or {}
    if md:
        checks += _module_checks(md, parts.get("courses") or {})

    tree = st.get("tree") or []
    total = st.get("total_credits")
    if tree:
        plans = [n for n in tree if n.get("plan")]
        top = min(int(n.get("credits") or 0) for n in plans) if plans else _sum_children(tree)
        if total is None:
            checks.append(Check("credits_total", "warn", "ไม่พบหน่วยกิตตลอดหลักสูตร", "structure"))
        elif top == total:
            checks.append(
                Check(
                    "credits_total",
                    "pass",
                    f"ผลรวมหมวดวิชา {top} = หน่วยกิตตลอดหลักสูตร {total}",
                    "structure",
                )
            )
        else:
            checks.append(
                Check(
                    "credits_total",
                    "fail",
                    f"ผลรวมหมวดวิชา {top} ≠ หน่วยกิตตลอดหลักสูตร {total} (เล่มอาจระบุ 'ไม่น้อยกว่า')",
                    "structure",
                )
            )
        bad = []
        for n in _walk(tree):
            kids_with_credits = [c for c in n["children"] if c.get("credits") is not None]
            if kids_with_credits and n.get("credits") is not None and not n.get("plan"):
                s = _sum_children(n["children"])
                if s != n["credits"]:
                    bad.append(f"{n['number']} {n['name']}: ลูกรวม {s} ≠ {n['credits']}")
        checks.append(
            Check(
                "credits_sub",
                "warn" if bad else "pass",
                "; ".join(bad) if bad else "หน่วยกิตกลุ่มย่อยรวมตรงกับหมวดทุกหมวด",
                "structure",
            )
        )
    else:
        checks.append(Check("credits_total", "fail", "ไม่พบโครงสร้างหลักสูตร", "structure"))

    plos = plo.get("plos") or []
    ks = parts.get("ksec") or {}
    if ks:
        checks += _ksec_checks(ks, plos)
    checks.append(
        Check(
            "plo_present",
            "pass" if plos else "fail",
            f"พบ PLO {len(plos)} ข้อ" if plos else "ไม่พบ PLO ในหมวดที่ 3",
            "plo",
        )
    )

    courses = crs.get("courses") or []
    mp = parts.get("mapping") or {}
    mrows = mp.get("rows") or []
    if mrows:
        plo_codes = mp.get("plo_codes") or []
        covered = {p for r in mrows for p in r.get("plos", [])}
        missing = [p for p in plo_codes if p not in covered]
        checks.append(
            Check(
                "plo_covered",
                "warn" if missing else "pass",
                f"PLO ที่ไม่มีรายวิชารองรับ: {', '.join(missing)}"
                if missing
                else f"ทุก PLO ({len(plo_codes)}) มีรายวิชารองรับใน Mapping",
                "mapping",
            )
        )
        declared = [p.get("code") for p in (plo.get("plos") or [])]
        absent = [p for p in declared if p and p not in plo_codes]
        if declared:
            checks.append(
                Check(
                    "mapping_has_all_plos",
                    "warn" if absent else "pass",
                    f"PLO ในหมวดที่ 3 ที่ไม่มีคอลัมน์ใน Mapping: {', '.join(absent)}"
                    if absent
                    else "คอลัมน์ Mapping ครบทุก PLO ของหมวดที่ 3",
                    "mapping",
                )
            )
        if mp.get("ksec_rows"):
            checks += _mapping42_checks(mp, ks)
        unmapped = mp.get("unmapped_courses") or []
        checks.append(
            Check(
                "courses_unmapped",
                "warn" if unmapped else "pass",
                f"รายวิชาใน Mapping ที่ไม่มี PLO เลย: {', '.join(unmapped[:8])}"
                if unmapped
                else "ทุกรายวิชาใน Mapping มีอย่างน้อย 1 PLO",
                "mapping",
            )
        )
        if courses:
            listed = {c.get("code_th") for c in courses}
            mapped = {r["course_code"] for r in mrows}
            only_list = sorted(listed - mapped)
            only_map = sorted(mapped - listed)
            checks.append(
                Check(
                    "mapping_vs_courses",
                    "warn" if (only_list or only_map) else "pass",
                    (
                        f"อยู่ในรายวิชาแต่ไม่อยู่ใน Mapping {len(only_list)}: {', '.join(only_list[:6])}"
                        if only_list
                        else ""
                    )
                    + (" · " if only_list and only_map else "")
                    + (
                        f"อยู่ใน Mapping แต่ไม่อยู่ในรายวิชา {len(only_map)}: {', '.join(only_map[:6])}"
                        if only_map
                        else ""
                    )
                    or "รายวิชาใน Mapping ตรงกับรายการรายวิชา",
                    "mapping",
                )
            )
    codes = Counter(c.get("code_th") for c in courses)
    dup = [c for c, n in codes.items() if n > 1]
    checks.append(
        Check(
            "course_code_unique",
            "fail" if dup else "pass",
            f"รหัสซ้ำ: {', '.join(dup)}" if dup else f"รหัสรายวิชาไม่ซ้ำ ({len(courses)} วิชา)",
            "courses",
        )
    )
    no_credit = [c["code_th"] for c in courses if not c.get("credit_text")]
    no_desc = [c["code_th"] for c in courses if not c.get("description_th")]
    low = [c["code_th"] for c in courses if (c.get("meta") or {}).get("confidence") == "low"]
    checks.append(
        Check(
            "course_fields",
            "warn" if (no_credit or no_desc) else "pass",
            f"ไม่มีหน่วยกิต {len(no_credit)} วิชา · ไม่มีคำอธิบาย {len(no_desc)} วิชา"
            + (f" (เช่น {', '.join((no_credit + no_desc)[:5])})" if (no_credit or no_desc) else ""),
            "courses",
        )
    )
    if low:
        checks.append(
            Check(
                "course_conflicts",
                "warn",
                f"parser กับ LLM ไม่ตรงกัน {len(low)} วิชา: {', '.join(low[:8])}",
                "courses",
            )
        )
    if courses and tree:
        total_course_credits = sum(int(c.get("credits") or 0) for c in courses)
        checks.append(
            Check(
                "courses_vs_structure",
                "info",
                f"รายวิชา {len(courses)} วิชา · หน่วยกิตรวมของรายวิชาที่พบ {total_course_credits}",
                "courses",
            )
        )
    return checks


def _walk(nodes: list[dict[str, Any]]):
    for n in nodes:
        yield n
        yield from _walk(n.get("children") or [])
