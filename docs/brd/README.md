# Business Requirement Document (BRD) — ระบบบริหารจัดการหลักสูตรและการรับรองสมรรถนะดิจิทัล (Skill Transcript)

> ร่าง v0.1 · 21 ต.ค. 2569 · ถอดจาก UI mock ที่ลูกค้าส่งมา (`samples/ui-mock.html`, 49 หน้า) และ developer prompt (`docs/developer-prompt.md`)
> สถานะ: **ร่างเพื่อให้ลูกค้ายืนยันทีละหน้า** · ข้อที่ mock ไม่ได้บอก ถูกทำเครื่องหมาย `[สมมติ]` และรวมไว้ใน `99-open-questions.md`

| ไฟล์ | เนื้อหา | สถานะ |
|---|---|---|
| [00-overview.md](00-overview.md) | ภาพรวมระบบ ผู้ใช้ 9 บทบาท สิทธิ์ ระบบภายนอก workflow อนุมัติ ขอบเขต release | ร่าง v0.1 |
| [01-m1-curriculum.md](01-m1-curriculum.md) | M1 บริหารข้อมูลหลักสูตร: คู่มือหลักสูตร · ตรวจสอบโดยคณะ · สมอ.08 · **นำเข้าด้วย AI** · บริหารรายวิชา · บุคคลภายนอก · แดชบอร์ด | ร่าง v0.1 |
| [02-m2-learning-plan.md](02-m2-learning-plan.md) | M2 แผนการจัดการเรียนรู้รายวิชา/ชุดวิชา | ร่าง v0.1 |
| [03-m3-skill-transcript.md](03-m3-skill-transcript.md) | M3 Skill Transcript | ร่าง v0.1 |
| [04-m4-qa.md](04-m4-qa.md) | M4 ประเมินผลหลักสูตรตามเกณฑ์มาตรฐาน | ร่าง v0.1 |
| [05-m5-reports.md](05-m5-reports.md) | M5 รายงาน (R01–R14) | ร่าง v0.1 |
| [90-ai-import-data-dictionary.md](90-ai-import-data-dictionary.md) | Data dictionary 10 ส่วนที่ AI สกัด (ฐานของ JSON schema ใน D4) | ร่าง v0.1 |
| [99-open-questions.md](99-open-questions.md) | ข้อสมมติและคำถามถึงลูกค้า | เปิด |

## วิธีอ่าน

- **US-xx** = user story รูปแบบ "ในฐานะ <บทบาท> ฉันต้องการ <สิ่งที่ทำ> เพื่อ <ผล>"
- **AC** = acceptance criteria ตรวจได้จริงบนระบบ
- **[mock: route]** = หน้าจอใน mock ที่เป็นที่มา เปิดดูได้ที่ `#/<route>` เช่น `#/import-review`
- **TOR x.y** = เลขข้อใน TOR ที่ mock อ้างถึง (ยังไม่เห็นเอกสาร TOR ฉบับจริง)

## หลักการที่ใช้ร่าง

1. mock คือ acceptance spec ของลูกค้า ทุกหน้าจอใน mock ต้องมี user story รองรับ
2. developer prompt คือ technical spec ของโมดูล AI (provider toggle · Markdown + assets · fallback template)
3. ค่าที่เล่มไม่มีแต่ระบบต้องการ ให้ AI "อนุมาน" ได้แต่ต้องติดธงให้ผู้ใช้ยืนยัน
4. ทุกค่าที่ AI สกัดต้องอ้างอิงเลขหน้าต้นฉบับได้
