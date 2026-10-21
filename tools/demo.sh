#!/usr/bin/env bash
# One-command POC demo: ingest -> extract (LLM) -> golden sheet for one book, then a summary.
# Usage: tools/demo.sh ["samples/curriculum/<book>.docx"] [--no-llm]
# Run from the repo root with the project venv (uv). Never run 02:30-04:00 (HRIS window).
set -euo pipefail
BOOK="${1:-samples/curriculum/วท.บ. วิทยาการการเปลี่ยนแปลงสภาพภูมิอากาศ.docx}"
LLM_FLAG="${2:-}"
STEM="$(basename "$BOOK")"; STEM="${STEM%.*}"
ING="data/ingest/$STEM"

echo "▶ 1/3 ingest (ชั้น A: Markdown ทั้งเล่ม ไม่ใช้ LLM)"
t0=$(date +%s)
uv run ocl ingest "$BOOK" > "$ING.ingest.json"
uv run python - "$ING.ingest.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
print(f"   หน้า {r['pages']} · ย่อหน้า {r['paragraphs']} · หัวข้อ {r['headings']} · ตาราง {r['tables']} (merge จาก {r['tables_merged_from']}) · รูป {r['images']} · หมวด {','.join(r['chapters'])} · ภาคผนวก {','.join(r['appendices']) or '-'} · {r['seconds']} s")
PY
rm -f "$ING.ingest.json"

echo "▶ 2/3 extract (ชั้น B: parser ก่อน LLM ยืนยัน) $LLM_FLAG"
uv run ocl extract "$ING" $LLM_FLAG > "$ING.extract.json"
uv run python - "$ING.extract.json" "$ING" <<'PY'
import json, sys, collections
r = json.load(open(sys.argv[1])); d = sys.argv[2]
cs = json.load(open(f"{d}/extract/courses.json"))["data"]
st = json.load(open(f"{d}/extract/structure.json"))["data"]
plo = json.load(open(f"{d}/extract/plo.json"))["data"]
conf = collections.Counter(c["meta"]["confidence"] for c in cs["courses"])
llm = r["parts"]["courses"]["llm"] or {}
print(f"   โครงสร้าง {st['node_count']} โหนด รวม {st['total_credits']} นก. · PLO {plo['count']} · รายวิชา {cs['count']} (parser {cs.get('parser_count')} / LLM ยืนยัน {cs.get('llm_count', '-')})")
print(f"   ความมั่นใจ: สูง {conf.get('high',0)} กลาง {conf.get('medium',0)} ต่ำ {conf.get('low',0)} · LLM {llm.get('calls',0)} คำขอ {llm.get('prompt_tokens',0)}/{llm.get('completion_tokens',0)} tok {llm.get('seconds',0):.0f} s · provider {r['provider']} {r['model']}")
print(f"   validator: ผ่าน {r['checks']['pass']} · warn {r['checks']['warn']} · fail {r['checks']['fail']}")
for c in r["checks"]["items"]:
    if c["status"] != "pass":
        print(f"     {c['status'].upper():4s} {c['key']}: {c['message'][:110]}")
for c in cs["courses"]:
    if c["meta"]["confidence"] == "low":
        print(f"     LOW  {c['code_th']}: {(c['meta'].get('note') or '')[:120]}")
PY
rm -f "$ING.extract.json"

echo "▶ 3/3 golden sheet (ชีทให้ Admin ตรวจ)"
uv run ocl golden "$ING"
echo "✔ เสร็จใน $(( $(date +%s) - t0 )) s · เปิด: $ING/book.md · $ING/extract/md/3-courses_list.md · data/golden/$STEM.md"
