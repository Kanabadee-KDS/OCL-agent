# การประเมิน Gemini vs Gemma (R1-E)

วัดความแม่นยำ ความเร็ว token และค่าใช้จ่ายของสองโมเดลบนเล่มตัวอย่างชุดเดียวกัน เทียบกับ **reference** = ผล parser จากเล่มดิจิทัล (ตรวจด้วยมือแล้วใน sprint 1 และรอ Admin spot-check ใน E3)

## สองโหมดที่ต้องรายงานแยกกันเสมอ

| โหมด | ความหมาย | ตอบคำถาม |
|---|---|---|
| `parser_first` | ระบบจริง: parser อ่านเล่ม โมเดลเติมเฉพาะที่ parser อ่านไม่ได้ (รายวิชาจากคำอธิบาย, ฟิลด์ข้อมูลหลักที่ว่าง) | ผู้ใช้จะเห็นผลต่างกันไหมเมื่อสลับโมเดล |
| `llm_only` | ปิด parser ใน 4 ส่วนที่โมเดลทำได้ (ข้อมูลหลัก 11 ฟิลด์, โครงสร้าง, PLO, รายวิชา) โมเดลอ่านเอง | โมเดลไหนอ่านเล่มได้แม่นกว่า |

อีก 6 ส่วน (อาจารย์, แผนรับ, KSEC, ชุดวิชา, mapping, มติ) เป็น parser ล้วน ไม่ขึ้นกับโมเดล จึงไม่อยู่ในการเทียบ

## วิธีรัน

บน Mac (Ollama ของ server ผ่าน Tailscale + GEMINI_API_KEY ใน `.env`) หรือใน container `api` บน server · **ห้ามรัน leg ollama ช่วง 02:30–04:00**

```bash
uv run python tools/bench.py --books samples/curriculum --out docs/eval/run-$(date +%F) --providers ollama,gemini --modes parser_first,llm_only
```

ตัวเลือก: `--only <ส่วนของชื่อไฟล์>` รันบางเล่ม · `--providers parser` = leg ตรวจสอบตัวเอง (ต้องได้ 1.000 ทุกช่อง) · รันซ้ำจะข้าม leg ที่มี report.json แล้ว (ลบโฟลเดอร์ของ leg นั้นถ้าต้องการรันใหม่)

ผลลัพธ์ใน `<out>/`: `results.csv` (แถวละ เล่ม×provider×โหมด), `results.json`, `summary.md` (ค่าเฉลี่ย), และต่อเล่ม `<book>/{ingest,ref,<provider>-<mode>}/` พร้อม `scores.json` ที่บอกรายการที่หาย/แต่งเอง (`missed`, `hallucinated`) และฟิลด์ที่ผิด (`wrong`) เพื่อให้ Admin ตรวจได้

## ตัวชี้วัด (ต่อเล่ม)

| ส่วน | ตัวชี้วัด |
|---|---|
| ข้อมูลหลัก | `info_accuracy` = ฟิลด์ที่ตรง / ฟิลด์ที่ reference มีค่า (ข้อความเทียบหลัง normalize ความคล้าย ≥ 0.85, ตัวเลขต้องเท่ากัน) |
| PLO | precision/recall ของรหัส PLO + `plo_text` ความถูกต้องของข้อความที่จับคู่ได้ |
| โครงสร้าง | precision/recall ของโหนดตามชื่อหมวด/กลุ่มวิชา + `structure_credits` หน่วยกิตตรง |
| รายวิชา | precision/recall ของรหัสวิชา + `courses_name_th` / `courses_credits` ของรายการที่จับคู่ได้ |
| ต้นทุน | `llm_seconds`, `llm_calls`, `llm_retries`, `prompt_tokens`, `completion_tokens`, `cost_usd` (ราคา Gemini ใน `ocl_api/evaluate.py` ปรับตามวันที่วัด; Gemma = 0 เงินสด แต่ใช้ GPU ร่วม HRIS) |

hallucination = 1 − precision (รายการที่โมเดลให้มาแต่ reference ไม่มี)

## ข้อจำกัดที่ต้องบอกคู่กับตัวเลข

- reference มาจาก parser จึงถูกเท่าที่ parser ถูก ส่วนที่ parser เองยัง warn (เช่น ตารางโครงสร้างแบบหลายแผน) ต้องให้ Admin ตัดสิน
- `gemini-flash-latest` เป็น alias ที่ Google เปลี่ยนรุ่นได้ ผลบันทึกรุ่นจริงที่ตอบ (`model` ใน results.csv) และวันที่รัน
- เล่มสแกนทดสอบสร้างจาก PDF ดิจิทัล ไม่ใช่สแกนจริง (คำถามเปิด A6)
- privacy ไม่ใช่ตัวเลขที่วัดได้ในชุดนี้: Gemma ข้อมูลอยู่ใน server มศว · Gemini ส่งเล่มไป Google (paid tier) ต้องตอบ C5 ว่าเล่มไหนห้ามขึ้น cloud
