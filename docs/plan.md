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

สถานะ 21 ต.ค.: D1 ✓ (benchmark: gemma4:26b) · D2 ✓ (ingest docx) · D3 ✓ (ingest pdf, BRD M2/M3) · D4 ✓ (gateway + extract 3 ส่วน, BRD M4/M5) · D5 ✓ (5 เล่ม, golden sheet, HRIS A/B) · D6 ✓ (demo.sh, summary) · **C ✓** (21 ต.ค.: REST API + worker + เว็บ Next.js 3 หน้า + deploy compose บน server ผ่าน end-to-end) · ทุก commit CI เขียว · R1 ส่วนที่ 9 Mapping 4.1 ✓ (parser, 5 เล่ม, แก้ในเว็บได้) · R1 ส่วนที่ 1 ข้อมูลหลัก+หมวด 1 ✓ (21 ต.ค.: 35 ฟิลด์ + วิชาเอก/ความร่วมมือ/อาชีพ, parser ล้วนได้ 30–34 ฟิลด์/เล่ม, อนุมาน 7 ฟิลด์ติดธง, LLM เติมเฉพาะที่ว่าง, validator 6 ข้อ, md `1-program_info.md`, golden §1, ฟอร์มในเว็บ) · R1 ส่วนที่ 5 KSEC ✓ + Mapping 4.2 ✓ (21 ต.ค.: ตาราง PLO×ด้าน K/S/E/C หมวด 3 → รายการรหัสต่อ PLO รองรับหลายแผน/วิชาเอก, ตาราง 4.2 รายวิชา×KSEC ถอดรหัสจากตัวเลขในช่อง, validator ข้ามส่วน 6 ข้อ, md `4b-ksec.md` + หัวข้อ 4.2 ใน mapping md, golden §3b/§4c, editor ในเว็บ) · R1 ส่วนที่ 10 มติอนุมัติ ✓ (21 ต.ค.: ข้อ 13 → สถานภาพ/ฉบับเดิม/เริ่มใช้ + แถวมติต่อระดับ ครั้งที่ วันที่ (BE→ISO) มติ, แถวที่เล่มเว้นว่าง = pending, ระดับที่ฟอร์มต้องมี+อว. รับทราบ = missing, validator 5 ข้อ, md `7-approval.md`, golden §1b, editor ในเว็บ) · R1 ส่วนที่ 2 อาจารย์ ✓ (21 ต.ค.: ตารางข้อ 11–12 → รายชื่อ+ตำแหน่ง+ดร.+ผู้รับผิดชอบ(*)+วิชาเอก, คุณวุฒิตัดที่ปีจบ, สถาบันจัดคู่ตามจำนวนวุฒิ (รองรับชื่อห่อบรรทัด/PDF ไม่มีขึ้นบรรทัด/ชื่อติดกัน), validator 6 ข้อ (จำนวนผู้รับผิดชอบตามเกณฑ์ [สมมติ], วุฒิ, 11 vs 12, ชื่อซ้ำ), md `8-teachers.md`, golden §1a, editor ในเว็บ) · R1 ส่วนที่ 3 แผนรับนิสิต+รูปแบบการสอน ✓ (21 ต.ค.: ตารางชั้นปี×ปีการศึกษา หมวด 2 ข้อ 4 รวมแบบแยกต่อแผน/วิชาเอก และแบบสองแผนในตารางเดียว (ศศ.ม.), รูปแบบการสอน On-site/Online/Hybrid/WIL อนุมานจากหมวด 1/4 ติดธง, วิธีการสอนต่อ PLO จากหมวด 5 ข้อ 1, validator 5 ข้อ, md `9-admission_plan.md`, golden §1c, editor ตารางตัวเลขในเว็บ) · R1 ส่วนที่ 7 ชุดวิชา ✓ (21 ต.ค.: หัวข้อ "n.n.n.n ชุดวิชา…" ในหมวด 4 ข้อ 3 → ชื่อไทย/อังกฤษ หน่วยกิต/ไม่นับ กลุ่ม คำอธิบายไทย+อังกฤษ รหัสรายวิชาในชุด + บรรทัดกลุ่ม "กำหนดให้เรียน จำนวน n ชุดวิชา รวม m หน่วยกิต" ใช้ตรวจ, validator 6 ข้อ, md `3b-modules.md`, golden §4a, editor ในเว็บ) · **การนำเข้าครบ 10/10 ส่วน** (parser ล้วน + LLM เฉพาะรายวิชา/ข้อมูลหลักที่ว่าง) · checks คำนวณใหม่หลังแก้ร่าง ✓ (21 ต.ค.: `JobStore.recompute` รัน validator จากข้อมูลที่แก้แล้วทุกครั้งที่บันทึก เขียน edits/checks.json + เรนเดอร์ md ของส่วนที่แก้ใหม่ที่ edits/md/ และ API เสิร์ฟแทนของเดิม หน้าเว็บโหลด checks ใหม่ทันทีหลังบันทึกพร้อมป้ายเวลา) · DB ✓ (21 ต.ค.: psycopg 3 + SQL migration ในโค้ด, ตาราง import_jobs/import_parts/import_checks/curriculum_drafts, `PgJobStore` สลับด้วย DATABASE_URL (ว่าง = ไฟล์เหมือนเดิม) ไฟล์หนักยังอยู่บน volume, worker copy ผลสกัดเข้า db, edits/history/checks เป็นแถว, finalize เขียน curriculum_drafts, compose เพิ่ม service db (postgres:16 ไม่เปิดพอร์ต) + CI มี postgres service, test ใช้ pgserver ฝังตัวเมื่อไม่มี DATABASE_URL) · Neon dev ต่อแล้ว ✓ (21 ต.ค.: project ap-southeast-1 Postgres 18, direct URL ใน .env, migrate ผ่าน, flow เต็มผ่าน API: สกัด 5 s / บันทึก 3 s / finalize 3 s หลังเปลี่ยนเป็น 1 connection ต่อ request-worker (ก่อนแก้ 24/15/11 s เพราะ connect ต่อคำสั่ง ~0.35 s), test DB รันกับ Neon ใน schema ชั่วคราวผ่านและ drop ทิ้ง) · **deploy บน server ครบ 8 commit (22 ต.ค. 09:30)**: 5 services (เพิ่ม db postgres:16.15 healthy ไม่เปิดพอร์ต) health database=postgres, migration ลงแล้ว, end-to-end ผ่าน worker แยก process: parser 0.3 s, แก้/ยืนยัน/finalize 0.05 s, งาน LLM จริง gemma4:26b เล่มภูมิอากาศ 57 s (courses 47 s + info 9 s, 3 คำขอ 10.8k/4.9k tokens) ครบ 10 ส่วน, gemma4:12b ยัง pin อยู่ · **auth ✓ (22 ต.ค.)**: Auth.js v5 ใน Next.js (Google @g.swu.ac.th เมื่อมี OAuth client + Buasri ID/รหัสผ่านจากตาราง users) · เบราว์เซอร์เรียก API ผ่าน proxy /api/ocl ที่เซ็น JWT HS256 (AUTH_SECRET ร่วมกัน) ใส่ sub/name/roles · FastAPI ตรวจ token ทุก endpoint (ไม่มี AUTH_SECRET = ปิด auth สำหรับ dev/test) · สิทธิ์เมนูนำเข้า: write = admin/central/curator · read = +faculty · อื่น ๆ 403 + หน้า 'ไม่มีสิทธิ์' · users table + `ocl users add/list/set/disable` · ประวัติการแก้บันทึกอีเมลผู้ login · ทดสอบ: login/upload/แก้/finalize ผ่าน proxy + faculty 403 upload + teacher 403 + anonymous 401/redirect · **Google SSO บน server ต้องมีชื่อโดเมน** (Google ไม่รับ redirect URI เป็น IP) → ใช้ Tailscale MagicDNS + HTTPS หรือโดเมนจากลูกค้า · **workflow คู่มือหลักสูตร ✓ (22 ต.ค.)**: migration 003 (curriculum_drafts.status/faculty_checked/review_due_at + ตาราง curriculum_events, 1 ร่างต่อ job) · state machine ตาม BRD 01 §2: ร่างนำเข้า →(ส่งให้คณะตรวจสอบ: admin/central/curator, กำหนด 5 วันทำการ)→ คณะตรวจสอบ →(faculty ติ๊กหมวด 3+4 ครบแล้วกด ตรวจสอบสำเร็จ / ส่งคืนพร้อมเหตุผล)→ ตรวจสอบสำเร็จ (ล็อกทุกบทบาท 409, แก้ผ่าน สมอ.08 ใน R2) →(admin/central เปิด/ปิด)→ เผยแพร่ · ระหว่างคณะตรวจสอบ faculty แก้ได้เฉพาะ plo/ksec/mapping · ทุกขั้นเป็นแถว event (ใคร เมื่อไร จากสถานะ→สถานะ หมายเหตุ) และ snapshot ข้อมูลล่าสุดลง curriculum_drafts · API `/api/curricula` (list+ตัวนับ, by-job, detail+events, transition) · เว็บ /curricula (KPI 4 สถานะ + ตาราง) และ /curricula/[id] (stepper, ปุ่มตามบทบาท/สถานะ, checklist หมวด 3–4, snapshot, ประวัติ) · หน้า done มีปุ่ม 'เปิดคู่มือหลักสูตร' · หน้าตรวจมีกล่องล็อก/ระหว่างคณะตรวจ · test 3 ข้อ (66 ผ่าน) · ทดสอบจริงกับ Neon ผ่านเบราว์เซอร์ครบวง · test-script เพิ่มหมวด K 10 ข้อ · **Gemini provider ✓ (22 ต.ค.)**: `LLMGateway._gemini_chat` เรียก REST `generateContent` v1beta ด้วย httpx เดิม (ไม่เพิ่ม dependency) key ส่งใน header `x-goog-api-key`, JSON mode + responseSchema (ตัด key ที่ Gemini ไม่รับ เช่น additionalProperties/$schema, type list → nullable), temperature 0, MAX_TOKENS → LLMTruncated เหมือน Ollama, usage จาก usageMetadata · ตั้งค่า GEMINI_API_KEY (+ GEMINI_MODEL ค่าเริ่มต้น alias `gemini-flash-latest`) ปุ่ม Cloud AI ในเว็บเปิดเอง · test 4 ข้อด้วย MockTransport (70 ผ่าน) · **ยิงจริงบน server ผ่าน (22 ต.ค. บ่าย)**: เล่มภูมิอากาศ 82 หน้า ครบ 10 ส่วน ผลเท่ากับรอบ Gemma (courses 57, PLO 5, info 30) · 5 คำขอ 17.8k/3.6k tokens 80 s (courses 72 s) ≈ 0.03 USD/เล่ม · Gemini API เป็น Prepay ต้องซื้อเครดิตใน AI Studio ก่อน (402 เมื่อหมด) · gateway ตรวจ key ที่มีช่องว่าง/ไม่ใช่ ASCII แล้วฟ้องเป็นไทย · **thinking ปิดเป็นค่าเริ่มต้น** (`GEMINI_THINKING_BUDGET=0`): alias ชี้ gemini-3.8-flash ซึ่งคิดก่อนตอบ 189 thought tokens แม้คำถามสั้น และ thoughts นับรวมใน maxOutputTokens จึงถูกตัด (MAX_TOKENS) ที่ 1024/4096 ใน bench ทั้งที่รอบเว็บตอนเช้าผ่าน · thoughtsTokenCount นับเป็น output ในค่าใช้จ่าย · **OCR หน้าสแกน ✓ (22 ต.ค.)**: PdfReader ตรวจหน้าที่ไม่มี text layer (< 30 ตัวอักษร ไม่มีตาราง) → เรนเดอร์ PNG ให้ผู้ตรวจ + OCR ด้วย Tesseract ที่ฝังใน MuPDF (`get_textpage_ocr` tha+eng 200 dpi ไม่เพิ่ม dependency Python ใช้แค่ tessdata) · บรรทัด OCR ภาษาไทยถูก Tesseract หั่นตามสระบน/วรรณยุกต์ จึง regroup ตามแถวก่อนเข้า logic ย่อหน้าเดิม · ตัด noise ("a y a") · หัวข้อหมวดที่เสียวรรณยุกต์ ("หมวดที1") จับได้เมื่ออยู่กึ่งกลางบรรทัด ส่วนบรรทัดสารบัญที่ OCR เพี้ยนไม่ถูกนับเป็นหมวด · Paragraph.ocr=True, Document.scanned_pages/ocr_pages, counts.ingest + หน้า done แสดง 'หน้าสแกน n (OCR m)' · health `ocr: tha+eng` เมื่อมี tessdata · Docker image เพิ่ม tesseract-ocr-tha/eng (+TESSDATA_PREFIX) CI ติดตั้งด้วย · ผล: หน้าเล่มอาหารที่เรนเดอร์เป็นภาพ 14 หน้า OCR 2.8 s/หน้า ความคล้ายข้อความ 95% จับหมวด 1–2 ถูก (เล่ม 186 หน้าสแกนทั้งเล่ม ≈ 9 นาที) · test 5 ข้อ (75 ผ่าน; ข้อ OCR จริง skip เมื่อไม่มี tessdata) · ยังไม่มีไฟล์สแกนจริงจากลูกค้า (A6) และยังไม่มี LLM แก้คำ OCR (`ocr_fixes`) · ถัดไป R1: การจับคู่ HURIS/รายวิชากลาง (ระบบหลัก), ฟอร์มคู่มือหลักสูตรหมวด 0–4, สมอ.08, LLM แก้คำ OCR

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

### R1-E การประเมิน Gemini vs Gemma (แทรกก่อนฟอร์มหมวด 0–4 · ตกลง 22 ต.ค. 2569)

ลูกค้าต้องการตัวเลขความแม่นยำเทียบกันและ infographic สถาปัตยกรรม 4 แกน (privacy · ความแม่นยำ · ค่าใช้จ่าย · ความเร็ว) ผลจะกำหนดว่า R1 ที่เหลือเป็น on-prem / cloud / ผสม

| ขั้น | งาน | ผลลัพธ์ | สถานะ |
|---|---|---|---|
| E1 | โหมด `EXTRACT_MODE=llm_only` (ปิด parser ในส่วนที่มี LLM: ข้อมูลหลัก, โครงสร้าง, PLO, รายวิชา) + `tools/bench.py` รัน เล่ม × provider × โหมด แล้วเทียบกับ reference (ผล parser จากเล่มดิจิทัลที่ตรวจด้วยมือแล้ว) → CSV/JSON/summary.md | เครื่องมือวัดที่รันซ้ำได้ | |
| E1 ผล pilot (เล่มภูมิอากาศ, 22 ต.ค. ค่ำ, `docs/eval/pilot-2026-10-22`) | ระบบจริง (parser_first): ทั้งสองโมเดลตรง reference 100% ทุกส่วน · โมเดลล้วน (llm_only): Gemini ข้อมูลหลัก 10/10, PLO/โครงสร้าง 100%, รายวิชา recall 75% (chunk ที่ 2 ตอบ 1 จาก 15 วิชา ไม่แต่งเพิ่ม) · Gemma ข้อมูลหลัก 6/10 (ฟิลด์ตัวเลข 4 ตัวตอบ null) รายวิชา 57/57 · เวลา LLM: Gemini 27 s / 60 s, Gemma 57 s / 75 s · Gemini ≈ 0.02–0.04 USD/เล่ม (ปิด thinking; เปิดจะถูกตัด MAX_TOKENS) · ต้องรันซ้ำ ≥ 2 ครั้ง (`--repeat 2`) ดูความแปรปรวนของ Gemini | ผลนำร่อง | ✓ |
| E2 | รันบน server: 5 เล่ม + สแกน 14 หน้า × ollama/gemini × parser_first/llm_only (Gemma นอก 02:30–04:00 · Gemini ≈ 1–10 บาท/เล่ม) | ตารางผลดิบใน `docs/eval/` | |
| E3 | Admin spot-check 20 ฟิลด์/เล่ม จาก CSV (ลูกค้า คู่ขนาน) + คำตอบ C5 เล่มไหนห้ามขึ้น cloud | ตัวเลขที่ลูกค้ารับรอง | รอลูกค้า |
| E4 | `docs/eval/gemini-vs-gemma.md` + infographic 1 หน้า (HTML artifact แชร์ได้ + PNG) ตัวเลขดึงจาก CSV | ของนำเสนอ | |

ตัวชี้วัดต่อเล่ม/โมเดล/โหมด: field accuracy (ข้อมูลหลัก 15 ฟิลด์ที่ LLM เติมได้), precision/recall ของรายการ (PLO, โหนดโครงสร้าง, รายวิชา) + ความถูกต้องของฟิลด์ในรายการที่จับคู่ได้ (ชื่อไทย/อังกฤษ/หน่วยกิต), hallucination = รายการที่ไม่มีใน reference, เวลา, token, ค่าใช้จ่าย (ราคา Gemini จากหน้า pricing วันที่วัด; Gemma = 0 เงินสด แต่ใช้ GPU ร่วม HRIS), จำนวน retry/ล้ม · ความแม่นยำ "ระบบ" (parser_first) กับ "โมเดล" (llm_only) รายงานแยกกันเสมอ · 6 ส่วนที่เป็น parser ล้วน (อาจารย์, แผนรับ, KSEC, ชุดวิชา, mapping, มติ) ไม่ขึ้นกับโมเดล จึงอยู่นอกการเทียบ

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
