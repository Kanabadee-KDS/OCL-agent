# วิธีทำงานร่วมกัน

## กติกาที่บังคับใช้ด้วยข้อตกลง (repo private บน GitHub Free ไม่มี branch protection)

1. **ห้าม push ตรงเข้า `main`** ทุกการเปลี่ยนแปลงผ่าน Pull Request และต้องมี reviewer อย่างน้อย 1 คน
2. **ห้าม `git push --force`** ทุก branch ที่มีคนอื่นใช้ร่วม
3. **ห้าม `git add -A` / `git add .`** ระบุไฟล์ที่ต้องการ commit เสมอ เพื่อไม่ให้เอกสารลูกค้าหรือ `.env` หลุด
4. CI ต้องเขียวก่อน merge (`ruff` + `pytest`)
5. ของที่แตะ server / Ollama / docker / `.github` ต้องให้เจ้าของโปรเจก (`@Kanabadee-KDS`) review ตาม `CODEOWNERS`
6. ก่อนรันอะไรบน server อ่าน `docs/server-constraints.md` ทุกครั้ง

## Branch

- `main` = ของที่ใช้งานได้เสมอ
- งานใหม่แตกจาก `main`: `feat/<เรื่อง>` · `fix/<เรื่อง>` · `docs/<เรื่อง>` · `chore/<เรื่อง>`
- merge แบบ **squash** เพื่อให้ประวัติบน `main` อ่านได้ 1 บรรทัดต่อ 1 PR

## Commit message

- subject ภาษาอังกฤษแบบ Conventional Commits: `feat: …` `fix: …` `docs: …` `chore: …` `test: …`
- body (ภาษาไทยได้) ต้องบอก **"ทำไม"** ไม่ใช่แค่ "ทำอะไร"

ตัวอย่าง

```
feat: reject keep_alive when sharing the HRIS model

keep_alive ในคำขอจะเขียนทับค่า -1 ของ HRIS ทำให้ gemma4:12b ถูกปล่อยออกจากหน่วยความจำ
จึงให้ Settings ล้มตั้งแต่ตอนเริ่ม แทนที่จะพังตอน runtime
```

## Pull Request

ใช้ template ที่ขึ้นมาอัตโนมัติ: ทำไม · ทำอะไร · พิสูจน์อย่างไร · แตะ server หรือไม่

## โค้ด

- Python 3.12 · จัดรูปแบบและตรวจด้วย `uv run ruff check .` (`uv run ruff format .` ก่อน commit)
- ชื่อตัวแปร ฟังก์ชัน comment ในโค้ดเป็นภาษาอังกฤษ · เอกสารใน `docs/` ภาษาไทยได้
- ทดสอบด้วย `uv run pytest -q` · tests ต้องไม่พึ่งไฟล์ใน `samples/` (ใช้ fixture ที่สร้างในโค้ด)
- ห้ามรันโค้ดโปรเจกด้วย python3 ของเครื่อง ใช้ `uv run …` เสมอ
