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

## อัปเดตเวอร์ชัน

```bash
cd /home/arsoft/ocl-agent && git pull && docker compose -f deploy/docker-compose.yml build && docker compose -f deploy/docker-compose.yml up -d
```

## ดู log / หยุด

```bash
cd /home/arsoft/ocl-agent && docker compose -f deploy/docker-compose.yml logs -f --tail 100 worker
```

```bash
cd /home/arsoft/ocl-agent && docker compose -f deploy/docker-compose.yml down
```

(`down` ไม่ลบ volume · ห้ามใช้ `-v` และห้าม `docker system prune`)
