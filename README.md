# OCL Agent

ระบบบริหารจัดการหลักสูตรและการรับรองสมรรถนะดิจิทัล (Skill Transcript) · หัวใจคือ **OCL Agent** ผู้ช่วย AI
ที่อ่านเล่มหลักสูตร (.docx / .pdf) แล้วสกัดเป็น Markdown ทั้งเล่ม + ข้อมูลโครงสร้างลงฟิลด์คู่มือหลักสูตร
พร้อมความมั่นใจและเลขหน้าต้นฉบับ สลับได้ระหว่าง Local AI (Gemma ผ่าน Ollama on-prem) และ Cloud AI (Gemini)

| เอกสาร | เนื้อหา |
|---|---|
| [docs/sprint1-summary.md](docs/sprint1-summary.md) | สรุปส่งมอบ sprint 1 (BRD + POC) ตัวเลขจากเล่มจริง 5 เล่ม |
| [docs/plan.md](docs/plan.md) | แผนงานปัจจุบัน (sprint 1 = BRD + POC) และ release plan |
| [docs/developer-prompt.md](docs/developer-prompt.md) | spec ต้นฉบับของโมดูล AI |
| [docs/server-constraints.md](docs/server-constraints.md) | **ข้อห้ามบน server ที่ใช้ร่วมกับ HRIS อ่านก่อนแตะ Ollama/docker ทุกครั้ง** |
| [CONTRIBUTING.md](CONTRIBUTING.md) | วิธีทำงานร่วมกัน branch / PR / commit |
| `docs/brd/` | Business requirement (sprint 1) |

## โครงสร้าง repo

```
apps/api/      FastAPI + worker (Python 3.12, uv)      ← กำลังทำ
apps/web/      Next.js 3 หน้า import ตาม UI design ของลูกค้า (POC)
deploy/        docker-compose (name: ocl) + Caddy สำหรับ server on-prem
tools/         สคริปต์ปฏิบัติการ เช่น ollama_bench.py
docs/          แผน spec BRD ข้อจำกัด
samples/       เล่มตัวอย่างและ UI mock (ไม่เข้า git แชร์แยก)
```

## เริ่มต้น (dev บน Mac/Linux)

ต้องมี [uv](https://docs.astral.sh/uv/) (`brew install uv`) · uv จะดาวน์โหลด Python 3.12 ให้เองตาม `.python-version`

```bash
uv sync --all-groups        # สร้าง .venv และติดตั้งทุกอย่าง
cp .env.example .env        # แก้ค่า OLLAMA_BASE_URL ฯลฯ · DATABASE_URL ว่าง = เก็บงานเป็นไฟล์ใน data/ · ใส่ URL ของ Neon = เก็บใน Postgres (ตารางสร้างให้เองตอน start, ดูด้วย `uv run ocl db status`)
uv run pytest -q            # ต้องผ่านก่อนเปิด PR
uv run uvicorn ocl_api.main:app --reload --port 8000
curl -s http://127.0.0.1:8000/health
```

แปลงเล่มหลักสูตรเป็น Markdown ทั้งเล่ม + รูป + JSON (ชั้น A ไม่ใช้ LLM) ผลอยู่ที่ `data/ingest/<ชื่อไฟล์>/`

```bash
uv run ocl ingest "samples/curriculum/<เล่ม>.docx"
```

สกัดข้อมูลโครงสร้าง (ชั้น B) จากผล ingest: โครงสร้างหลักสูตร · PLO · รายวิชา → `extract/*.json` + `extract/checks.json` + `extract/md/*.md`
ต้องมี `.env` ชี้ Ollama (ดู `.env.example`) หรือใส่ `--no-llm` เพื่อใช้ parser อย่างเดียว

```bash
uv run ocl extract "data/ingest/<เล่ม>"
```

Demo ทั้ง pipeline ด้วยคำสั่งเดียว (ingest → extract → golden sheet, ~1 นาที, ใช้ Ollama) ดู `docs/demo.md`

```bash
tools/demo.sh
```

รัน API + เว็บบน Mac (2 terminal) แล้วเปิด `http://localhost:3000/import`

```bash
uv run ocl api --reload
```

```bash
npm --prefix apps/web install && npm --prefix apps/web run dev
```

Deploy บน server: ดู `deploy/README.md`

เปิด UI mock ของลูกค้า: `python3 -m http.server 8765 --directory samples` แล้วเปิด `http://127.0.0.1:8765/ui-mock.html`

## Benchmark Ollama บน server (ก่อนตัดสินใจโมเดล)

ดู `tools/ollama_bench.py --help` และข้อห้ามใน `docs/server-constraints.md` ก่อนรันเสมอ
