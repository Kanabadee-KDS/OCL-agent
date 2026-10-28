# Business Requirement Document (BRD) — ระบบบริหารจัดการหลักสูตรและการรับรองสมรรถนะดิจิทัล (Skill Transcript)

> ร่าง v0.2 · 28 ต.ค. 2569 (v0.1 21 ต.ค.) · ถอดจาก UI mock ที่ลูกค้าส่งมา (`samples/ui-mock.html`, 49 หน้า) และ developer prompt (`docs/developer-prompt.md`)
> สถานะ: **ร่างเพื่อให้ลูกค้ายืนยันทีละหน้า** · ข้อที่ mock ไม่ได้บอก ถูกทำเครื่องหมาย `[สมมติ]` และรวมไว้ใน `99-open-questions.md`

| ไฟล์ | เนื้อหา | สถานะ |
|---|---|---|
| [00-overview.md](00-overview.md) | ภาพรวมระบบ ผู้ใช้ 9 บทบาท สิทธิ์ ระบบภายนอก workflow อนุมัติ ขอบเขต release · §9 user story เข้าสู่ระบบ แดชบอร์ด บริหารจัดการสิทธิ์ | ร่าง v0.2 |
| [01-m1-curriculum.md](01-m1-curriculum.md) | M1 บริหารข้อมูลหลักสูตร: คู่มือหลักสูตร · ตรวจสอบโดยคณะ · สมอ.08 · **นำเข้าด้วย AI** · บริหารรายวิชา · บุคคลภายนอก · แดชบอร์ด · ปรับตามที่สร้างจริง 28 ต.ค. | ร่าง v0.2 |
| [02-m2-learning-plan.md](02-m2-learning-plan.md) | M2 แผนการจัดการเรียนรู้รายวิชา/ชุดวิชา | ร่าง v0.1 |
| [03-m3-skill-transcript.md](03-m3-skill-transcript.md) | M3 Skill Transcript | ร่าง v0.1 |
| [04-m4-qa.md](04-m4-qa.md) | M4 ประเมินผลหลักสูตรตามเกณฑ์มาตรฐาน | ร่าง v0.2 |
| [05-m5-reports.md](05-m5-reports.md) | M5 รายงาน (R01–R14) | ร่าง v0.2 |
| [90-ai-import-data-dictionary.md](90-ai-import-data-dictionary.md) | Data dictionary 10 ส่วนที่ AI สกัด (ฐานของ JSON schema ใน D4) | ร่าง v0.1 |
| [99-open-questions.md](99-open-questions.md) | ข้อสมมติและคำถามถึงลูกค้า | เปิด |
| [91-traceability.md](91-traceability.md) | ตารางไล่ความครบ หน้า mock → user story → AC → กรณีทดสอบ (สร้างด้วย `tools/brd_trace.py`) | สร้างอัตโนมัติ |

## วิธีอ่าน

- **US-xx** = user story (US-M1… ตามโมดูล · US-U… เข้าสู่ระบบและบริหารจัดการสิทธิ์ · US-G… หน้ากลาง) รูปแบบ "ในฐานะ <บทบาท> ฉันต้องการ <สิ่งที่ทำ> เพื่อ <ผล>"
- **AC** = acceptance criteria ตรวจได้จริงบนระบบ
- **[mock: route]** = หน้าจอใน mock ที่เป็นที่มา เปิดดูได้ที่ `#/<route>` เช่น `#/import-review`
- **TOR x.y** = เลขข้อใน TOR ที่ mock อ้างถึง (ยังไม่เห็นเอกสาร TOR ฉบับจริง)

## หลักการที่ใช้ร่าง

1. mock คือ acceptance spec ของลูกค้า ทุกหน้าจอใน mock ต้องมี user story รองรับ
2. developer prompt คือ technical spec ของโมดูล AI (provider toggle · Markdown + assets · fallback template)
3. ค่าที่เล่มไม่มีแต่ระบบต้องการ ให้ AI "อนุมาน" ได้แต่ต้องติดธงให้ผู้ใช้ยืนยัน
4. ทุกค่าที่ AI สกัดต้องอ้างอิงเลขหน้าต้นฉบับได้
