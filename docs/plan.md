# OCL Agent — แผนงาน v3 (20 ต.ค. 2569 · อัปเดตสถานะ 21 ต.ค.)

> v3 แทน v2 หลังตัดสินใจ: ขอบเขตทีม = ทั้งระบบ 5 โมดูล · สัปดาห์หน้าส่ง **B = BRD + POC โมดูล AI** · BRD เป็น Markdown ใน repo · DB dev บน Neon, prod บน server · ผลลัพธ์ AI = Markdown ทั้งเล่ม + ข้อมูลโครงสร้าง 10 ส่วน
> spec ต้นฉบับ: `docs/developer-prompt.md` · UI mock ของลูกค้า: `samples/ui-mock.html` (gitignored) · ข้อจำกัด server: `docs/server-constraints.md`

## 0. ภาพรวมระบบและตำแหน่งของ OCL Agent

```
ระบบบริหารจัดการหลักสูตรและการรับรองสมรรถนะดิจิทัล (Skill Transcript) — 5 โมดูล 49 หน้า 9 บทบาท
 ├─ M1 บริหารข้อมูลหลักสูตร  ← คู่มือหลักสูตร (หมวด 0–4) · นำเข้าด้วย AI (OCL Agent) · สมอ.08 · รายวิชา/บุคคลภายนอก
 ├─ M2 แผนการจัดการเรียนรู้   ← ใช้รายวิชา/PLO จาก M1
 ├─ M3 Skill Transcript        ← ใช้รายวิชา/PLO/KSEC จาก M1
 ├─ M4 ประเมินผลหลักสูตร (QA) ← ใช้ข้อมูล M1–M3
 └─ M5 รายงาน                  ← ใช้ทุกโมดูล
ระบบภายนอก: Google SSO @g.swu.ac.th · HURIS (อาจารย์) · SUPREME (ทะเบียนหลักสูตร CUR27) · ฐานข้อมูลรายวิชากลาง
```

OCL Agent = ส่วน "นำเข้าข้อมูลเล่มหลักสูตรด้วย AI" ใน M1 (อัปโหลด → AI อ่าน → ตรวจสอบทีละส่วน → บันทึก) และเป็นต้นน้ำของข้อมูลทุกโมดูล จึงทำก่อน

## 1. ผลลัพธ์ของ OCL Agent (2 ชั้นจาก Document model เดียว)

```
ไฟล์ .docx/.pdf ──ingest──▶ Document model (sections ตาม "หมวดที่ N", tables merge ข้ามหน้า, glyph map, images, page refs)
                                   ├──render──▶ ชั้น A: Markdown ทั้งเล่ม  (หมวด 1–8 + ภาคผนวก, assets/, ไม่พึ่ง LLM)  → อ่าน/ค้นหา/แก้ใน editor/Preview
                                   └──extract─▶ ชั้น B: ข้อมูลโครงสร้าง (v1 = 10 ส่วน หมวด 0–4 + สถานภาพ; ส่วน = plugin: schema + prompt + validator)
                                                   ทุกค่า: value · confidence (สูง/กลาง/ต่ำ) · source {page, snippet} · inferred flag
```

| ชั้น | v1 (sprint 1–R1) | ระยะยาว |
|---|---|---|
| A Markdown | ทั้งเล่ม ตั้งแต่ POC | เพิ่ม OCR หน้าสแกน · แก้คำ OCR ด้วย LLM |
| B โครงสร้าง | POC: 3 ส่วน (โครงสร้างหลักสูตร · PLO · รายวิชา) → R1: ครบ 10 ส่วน | เพิ่ม plugin หมวด 5–8 ตามที่ลูกค้าต้องการ |

หลักการ: LLM สกัด โค้ดตรวจ (validator) · parse ตรงจาก docx ก่อน ใช้ LLM เฉพาะที่ parse ไม่ได้ · เก็บทุกการแก้ของผู้ใช้เป็น few-shot รอบถัดไป · สกัดใหม่ได้ทีละส่วน · audit trail

## 2. Sprint 1 (7 วัน) — ส่งมอบ B: BRD v1 + POC โมดูล AI

สถานะ 21 ต.ค.: D1 ✓ (benchmark: gemma4:26b) · D2 ✓ (ingest docx) · D3 ✓ (ingest pdf, BRD M2/M3) · D4 ✓ (gateway + extract 3 ส่วน, BRD M4/M5) · D5 ✓ (5 เล่ม, golden sheet, HRIS A/B) · D6 ✓ (demo.sh, summary) · **C ✓** (21 ต.ค.: REST API + worker + เว็บ Next.js 3 หน้า + deploy compose บน server ผ่าน end-to-end) · ทุก commit CI เขียว · R1 ส่วนที่ 9 Mapping 4.1 ✓ (parser, 5 เล่ม, แก้ในเว็บได้) · R1 ส่วนที่ 1 ข้อมูลหลัก+หมวด 1 ✓ (21 ต.ค.: 35 ฟิลด์ + วิชาเอก/ความร่วมมือ/อาชีพ, parser ล้วนได้ 30–34 ฟิลด์/เล่ม, อนุมาน 7 ฟิลด์ติดธง, LLM เติมเฉพาะที่ว่าง, validator 6 ข้อ, md `1-program_info.md`, golden §1, ฟอร์มในเว็บ) · POC ครอบคลุม 5/10 ส่วน · ถัดไป R1: ส่วนที่ 5 KSEC, ส่วนที่ 10 มติอนุมัติ (ข้อ 13 อ่านไว้แล้วบางส่วน), ส่วนที่ 2 อาจารย์

เป้าหมายวันส่ง (ลูกค้าเห็น):
1. **BRD v1** `docs/brd/` Markdown: ภาพรวมระบบ · user story ทุกหน้า (49 routes) · permission matrix 9 บทบาท · state machine คู่มือหลักสูตร/นำเข้า/สมอ.08 · data dictionary 10 ส่วน + ฟิลด์ CUR27 ที่ถอดจาก mock · ข้อสมมติ/คำถามถึงลูกค้า · แผน release
2. **POC**: รัน CLI กับเล่ม วท.บ. วิทยาการการเปลี่ยนแปลงสภาพภูมิอากาศ (docx 78 หน้า) และเล่ม PDF → ได้ Markdown ทั้งเล่ม + `assets/` + JSON 3 ส่วน พร้อม confidence/เลขหน้า + รายงาน validator · demo คู่กับหน้า import-review ของ mock · ตาราง benchmark gemma4:26b และเวลา/เล่ม

| วัน | งาน | ผู้ทำ | พิสูจน์อย่างไร |
|---|---|---|---|
| D1 | repo init + โครง monorepo + `apps/api` skeleton (uv, Python 3.12, FastAPI `/health`, pytest, CI) · ย้าย samples · **benchmark gemma4:26b บน server** (`ollama_bench.py`, นอก 02:30–04:00, ตรวจ `/api/ps` ก่อน/หลัง) | Claude เขียน · คุณรัน git/server | CI เขียวบน GitHub · ตาราง tokens/s + `/api/ps` แสดง 12b ยังอยู่ |
| D2 | ingestion docx → Document model → Markdown ทั้งเล่ม + assets (glyph map, ตัดหมวดด้วย pattern) · BRD: ภาพรวม + M1 (คู่มือ + นำเข้า AI) | Claude · คุณตรวจ BRD | รัน 4 เล่ม docx: นับหมวด/ตาราง/รูปตรงกับที่นับมือ · BRD M1 ส่งลูกค้าอ่านได้ |
| D3 | ingestion pdf (Docling) → Markdown · merge ตารางข้ามหน้า · BRD: M2 + M3 | Claude | เล่ม PDF 186 หน้าออก Markdown ครบ 8 หมวด · Mapping p.53–65 เป็นตารางเดียวมี ● |
| D4 | extraction 3 ส่วน (โครงสร้างหลักสูตร · PLO · รายวิชา) → JSON + confidence + source + validator (ผลรวมหน่วยกิต รหัสซ้ำ x(x-x-x)) · BRD: M4 + M5 + permission matrix + state machine | Claude · dev เริ่ม review PR | เล่มภูมิอากาศ: รายวิชาครบ 100% · หน่วยกิตรวมตรงเล่ม · PLO ครบ |
| D5 | รัน POC ครบ 5 เล่ม · golden sample เล่มภูมิอากาศ (Admin/คุณ ตรวจ 2–3 ชม.) · data dictionary 10 ส่วน · วัด HRIS B/C | คุณ + Claude | ตารางผล 5 เล่ม: เวลา/เล่ม · ตาราง ≥95% · HRIS latency ไม่เกินเกณฑ์ที่ตกลง |
| D6 | buffer แก้ของที่พัง · demo script · README วิธีรัน · BRD: ข้อสมมติ/คำถาม/แผน release | Claude · คุณซ้อม demo | demo รันซ้ำได้จากคำสั่งเดียว |
| D7 | สำรอง/ส่งงาน | คุณ | ลูกค้าได้ลิงก์ repo + เอกสาร + ผล POC |

สิ่งที่ POC **ไม่ทำ**: web UI จริง · API · OCR หน้าสแกน · จับคู่ HURIS/SUPREME · Gemini (interface ว่างไว้)

ความเสี่ยงของ sprint: benchmark D1 คือจุดตัดสิน ถ้า gemma4:26b ช้าเกิน (เช่น > 30 นาที/เล่ม 78 หน้า) ให้ตัดสินใจ D2 ว่าใช้ gemma4:12b ร่วมแบบจำกัด (ขอคุณอนุมัติ) หรือเปิด Gemini สำหรับ POC

## 3. Release plan หลัง sprint 1 (ประมาณการ ต้องแตก WBS หลัง BRD)

| Release | ขอบเขต | ขึ้นกับ |
|---|---|---|
| R1 | M1 เต็ม: คู่มือหลักสูตร หมวด 0–4 (ฟอร์ม + workflow ร่าง→คณะตรวจ→สำเร็จ→เผยแพร่) · นำเข้า AI ครบ 10 ส่วน + API + 3 หน้า import ตาม mock · Markdown viewer/editor ตาม developer prompt · auth (NextAuth Google) + 9 บทบาท · deploy on-prem | OAuth client จากลูกค้า · schema CUR27 ยืนยัน |
| R2 | M1 ส่วนที่เหลือ (สมอ.08 · บริหารรายวิชา · บุคคลภายนอก) + M2 แผนการจัดการเรียนรู้ | รายวิชา/PLO จาก R1 |
| R3 | M3 Skill Transcript (ฐาน Skill · กำหนด · ประเมิน · portfolio · ออกเอกสาร) | R1–R2 |
| R4 | M4 ประเมินผลหลักสูตร + M5 รายงาน | R1–R3 |
| ตลอด | OCR หน้าสแกน · plugin หมวด 5–8 · จับคู่ HURIS/SUPREME/รายวิชากลาง เมื่อได้ API | ลูกค้า |

ทีม 3 คน (เสนอ): backend AI 1 · backend ระบบหลัก (auth, workflow, DB) 1 · frontend 1 · คุณ = BRD, ลูกค้า, server, review

## 4. สถาปัตยกรรม (คงจาก v2 ปรับเล็กน้อย)

```
Browser (Tailscale) → caddy 100.104.172.122:8100
   ├─ web    Next.js (R1)  : design tokens/components ถอดจาก mock · NextAuth Google
   └─ api    FastAPI       : auth/roles · imports · parts · markdown files · static assets
        ├─ db      Postgres 16 (prod container `ocl_pgdata`) / Neon (dev)   DATABASE_URL
        ├─ files   volume `ocl_files` → `/server_data/curriculums/{program}_{year}/` (.md, assets/, ต้นฉบับ, ภาพหน้า)
        └─ worker  process แยก concurrency 1 : ingest → render md → extract (plugins) → validate
                     LLM gateway: provider=ollama (gemma4:26b, num_ctx, keep_alive 10m, think off) | gemini (ภายหลัง)
                     adapters: HURIS / SUPREME / course-db = interface + mock จนกว่าจะได้ API
```

compose `name: ocl` · ไม่มี Ollama ใน compose · ข้อห้ามทั้งหมดใน `docs/server-constraints.md`

## 5. ข้อตัดสินใจที่ยังค้าง

| เรื่อง | สถานะ | ค่าเริ่มต้นถ้าไม่ตอบ |
|---|---|---|
| วันส่ง sprint 1 | ยังไม่ระบุ | วางแผนให้พร้อม จ. 27 ต.ค. 2569 สำรองถึง ศ. 31 ต.ค. |
| GitHub A/B/C | ยังไม่ระบุ | C (Free + ข้อตกลงทีม + CI เตือน push ตรง main) เปลี่ยนเป็น A ได้ทุกเมื่อ |
| OAuth client Google ของ มศว | ต้องขอลูกค้า | dev ใช้บัญชีทดสอบ |
| API HURIS/SUPREME/รายวิชากลาง | ต้องขอลูกค้า | mock adapter |
