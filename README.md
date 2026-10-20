# OCL Agent

ระบบบริหารจัดการหลักสูตรและการรับรองสมรรถนะดิจิทัล (Skill Transcript) · หัวใจคือ **OCL Agent** ผู้ช่วย AI
ที่อ่านเล่มหลักสูตร (.docx / .pdf) แล้วสกัดเป็น Markdown ทั้งเล่ม + ข้อมูลโครงสร้างลงฟิลด์คู่มือหลักสูตร
พร้อมความมั่นใจและเลขหน้าต้นฉบับ สลับได้ระหว่าง Local AI (Gemma ผ่าน Ollama on-prem) และ Cloud AI (Gemini)

| เอกสาร | เนื้อหา |
|---|---|
| [docs/plan.md](docs/plan.md) | แผนงานปัจจุบัน (sprint 1 = BRD + POC) และ release plan |
| [docs/developer-prompt.md](docs/developer-prompt.md) | spec ต้นฉบับของโมดูล AI |
| [docs/server-constraints.md](docs/server-constraints.md) | **ข้อห้ามบน server ที่ใช้ร่วมกับ HRIS อ่านก่อนแตะ Ollama/docker ทุกครั้ง** |
| [CONTRIBUTING.md](CONTRIBUTING.md) | วิธีทำงานร่วมกัน branch / PR / commit |
| `docs/brd/` | Business requirement (sprint 1) |

## โครงสร้าง repo

```
apps/api/      FastAPI + worker (Python 3.12, uv)      ← กำลังทำ
apps/web/      Next.js ตาม UI design ของลูกค้า         ← R1
deploy/        docker-compose (name: ocl) + Caddy        ← R1
tools/         สคริปต์ปฏิบัติการ เช่น ollama_bench.py
docs/          แผน spec BRD ข้อจำกัด
samples/       เล่มตัวอย่างและ UI mock (ไม่เข้า git แชร์แยก)
```

## เริ่มต้น (dev บน Mac/Linux)

ต้องมี [uv](https://docs.astral.sh/uv/) (`brew install uv`) · uv จะดาวน์โหลด Python 3.12 ให้เองตาม `.python-version`

```bash
uv sync --all-groups        # สร้าง .venv และติดตั้งทุกอย่าง
cp .env.example .env        # แก้ค่า OLLAMA_BASE_URL ฯลฯ
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

เปิด UI mock ของลูกค้า: `python3 -m http.server 8765 --directory samples` แล้วเปิด `http://127.0.0.1:8765/ui-mock.html`

## Benchmark Ollama บน server (ก่อนตัดสินใจโมเดล)

ดู `tools/ollama_bench.py --help` และข้อห้ามใน `docs/server-constraints.md` ก่อนรันเสมอ
