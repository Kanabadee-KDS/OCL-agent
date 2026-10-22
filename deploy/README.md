# Deploy POC บน server (compose project `ocl`)

อ่าน `docs/server-constraints.md` ก่อนทุกครั้ง · ทุกคำสั่งรันที่ `/home/arsoft/ocl-agent` ด้วย user `arsoft` · งาน build รันใน `tmux`

| service | หน้าที่ | พอร์ต |
|---|---|---|
| caddy | reverse proxy เดียวที่เปิดพอร์ต `100.104.172.122:8100` → `/api/*` ไป api, อื่น ๆ ไป web | 8100 (Tailscale เท่านั้น) |
| api | FastAPI (`ocl api`) | ภายใน |
| worker | `ocl worker` ประมวลผลงานทีละงาน เรียก Ollama ของ host ผ่าน `host.docker.internal:11434` | – |
| web | Next.js standalone | ภายใน |

ข้อมูลอยู่ใน volume `ocl_files` (`/server_data/imports/<job>/`) · ไม่มี DB ใน POC

## ครั้งแรก

```bash
cd /home/arsoft/ocl-agent && cp deploy/.env.example deploy/.env
```

แก้ `deploy/.env` ตั้ง `AUTH_SECRET` (openssl rand -hex 32) และ `POSTGRES_PASSWORD` เป็นรหัสยาว ๆ (service `db` ใช้ครั้งแรกตอนสร้าง volume `ocl_pg` ถ้าเปลี่ยนทีหลังต้องลบ volume หรือ ALTER USER ใน psql) · db ไม่เปิดพอร์ตออกนอก compose network (กติกาข้อ 8) · API สร้างตาราง (migration) ให้เองตอนเริ่ม

```bash
cd /home/arsoft/ocl-agent && tmux new -s ocl-build
```

(ใน tmux) build ทั้ง 2 image ราว 5–10 นาที ครั้งแรก

```bash
cd /home/arsoft/ocl-agent && docker compose -f deploy/docker-compose.yml build
```

```bash
cd /home/arsoft/ocl-agent && docker compose -f deploy/docker-compose.yml up -d
```

ตรวจ

```bash
cd /home/arsoft/ocl-agent && docker compose -f deploy/docker-compose.yml ps && curl -s http://100.104.172.122:8100/health
```

เปิดจากเครื่องใน Tailscale: `http://100.104.172.122:8100/import`

## ผู้ใช้และสิทธิ์

ต้องมีผู้ใช้อย่างน้อย 1 คนก่อนจึงเข้าเว็บได้ (ไม่มี Google SSO จนกว่าจะได้ OAuth client และชื่อโดเมน) สร้างผู้ดูแลส่วนกลางคนแรกด้วยบัวศรีไอดี+รหัสผ่าน (พิมพ์รหัสผ่านตอนถาม ไม่ทิ้งไว้ใน history)

```bash
cd /home/arsoft/ocl-agent && docker compose -f deploy/docker-compose.yml exec api ocl users add --email admin@g.swu.ac.th --name "ผู้ดูแลส่วนกลาง" --roles admin,central --buasri admin --ask-password
```

เพิ่มคนอื่นด้วย `--roles` จาก `ocl users roles` (admin central curator faculty evaluator teacher advisor student exec ใส่หลายค่าคั่นด้วย ,) · ดูทั้งหมด `ocl users list` · ระงับ `ocl users disable --email …` · สิทธิ์เมนูนำเข้า: อัปโหลด/แก้/ยืนยัน = admin, central, curator · ดูอย่างเดียว = faculty · บทบาทอื่นเข้าเมนูนี้ไม่ได้ · workflow คู่มือหลักสูตร: ส่งให้คณะตรวจสอบ = admin, central, curator · ติ๊กหมวด 3–4 / ตรวจสอบสำเร็จ / ส่งคืน = faculty (admin ทำแทนได้) · เปิด/ปิดเผยแพร่ = admin, central · ทดสอบให้ครบต้องมีบัญชี faculty อย่างน้อย 1 คน (`--roles faculty`)

## OCR หน้าสแกน

image `ocl-api` ติดตั้ง `tesseract-ocr-tha` และ `tesseract-ocr-eng` ไว้แล้ว (ตัว OCR ฝังอยู่ใน PyMuPDF ใช้แค่ไฟล์ภาษา) ไม่ต้องตั้งค่าเพิ่ม · ตรวจได้จาก `/health` ฟิลด์ `"ocr":"tha+eng"` (เป็น `null` = หาไฟล์ภาษาไม่เจอ ตรวจ `TESSDATA_PREFIX` ใน Dockerfile) · ปิด OCR ได้ด้วย `OCR=false` ใน `deploy/.env` · OCR ใช้ CPU ราว 3 วินาที/หน้า ไม่แตะ GPU

## รัน bench Gemini vs Gemma บน server (R1-E)

คัดลอกเล่มตัวอย่างขึ้น container แล้วรันใน container `api` (ใช้ Ollama บน host และ GEMINI_API_KEY จาก deploy/.env · นอกช่วง 02:30–04:00 · 5 เล่ม × 2 provider × 2 โหมด ราว 20–40 นาที รันใน tmux)

```bash
cd /home/arsoft/ocl-agent && docker compose -f deploy/docker-compose.yml cp samples/curriculum api:/tmp/books && docker compose -f deploy/docker-compose.yml exec api python tools/bench.py --books /tmp/books --out /server_data/eval/run-$(date +%F) --providers ollama,gemini --modes parser_first,llm_only
```

ผลอยู่ใน volume `/server_data/eval/<run>/` ดึงกลับด้วย `docker compose -f deploy/docker-compose.yml cp api:/server_data/eval/<run> ./docs/eval/` · รายละเอียดตัวชี้วัดใน `docs/eval/README.md`

## ฐานข้อมูล

สถานะ/migration (API ทำให้เองตอน start แต่สั่งเองได้)

```bash
cd /home/arsoft/ocl-agent && docker compose -f deploy/docker-compose.yml exec api ocl db status
```

สำรองข้อมูล (ไฟล์ .sql ไว้ที่ home ของ arsoft)

```bash
cd /home/arsoft/ocl-agent && docker compose -f deploy/docker-compose.yml exec -T db pg_dump -U ocl ocl > /home/arsoft/ocl-backup-$(date +%Y%m%d).sql
```

งานนำเข้าที่สร้างก่อนมี db (โฟลเดอร์ใน volume `ocl_files` ที่มี `job.json`) จะไม่ปรากฏในรายการอีก เพราะรายการอ่านจาก Postgres แล้ว ไฟล์ยังอยู่ครบ

## อัปเดตเวอร์ชัน

```bash
cd /home/arsoft/ocl-agent && git pull && docker compose -f deploy/docker-compose.yml build && docker compose -f deploy/docker-compose.yml up -d
```

ถ้า commit นั้นแก้ `deploy/Caddyfile` ต้อง recreate container caddy ด้วย (ไฟล์ถูก bind-mount ทีละไฟล์ git pull เขียนไฟล์ใหม่เป็น inode ใหม่ container เดิมจึงยังเห็นไฟล์เก่า แม้สั่ง `caddy reload` ก็อ่านของเก่า อาการ: `/api/auth/*` หรือ `/api/ocl/*` ตอบ `{"detail":"Not Found"}` จาก FastAPI และ login ไม่ได้)

```bash
cd /home/arsoft/ocl-agent && docker compose -f deploy/docker-compose.yml up -d --force-recreate caddy && sleep 3 && curl -s http://100.104.172.122:8100/api/auth/providers
```
คาดว่าเห็น JSON ที่มี `"buasri"` (ไม่ใช่ `{"detail":"Not Found"}`)

## ดู log / หยุด

```bash
cd /home/arsoft/ocl-agent && docker compose -f deploy/docker-compose.yml logs -f --tail 100 worker
```

```bash
cd /home/arsoft/ocl-agent && docker compose -f deploy/docker-compose.yml down
```

(`down` ไม่ลบ volume · ห้ามใช้ `-v` และห้าม `docker system prune`)
