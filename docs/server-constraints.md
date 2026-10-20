# ข้อจำกัดบน server on-prem (ใช้ร่วมกับระบบ HRIS ของลูกค้า)

> ละเมิดข้อห้ามด้านล่างแล้ว HRIS ที่ลูกค้าใช้ทดสอบอยู่ **ล่มทันที** · ตรวจล่าสุด 20 ต.ค. 2569

## เครื่อง

| รายการ | ค่า |
|---|---|
| เครื่อง | ASUS GX10 (`gx10-75cd`) · NVIDIA GB10 · Ubuntu aarch64 · user `arsoft` |
| หน่วยความจำ | 121 GiB unified CPU+GPU (nvidia-smi แสดง memory N/A เป็นปกติ) · available ~91 GiB |
| ดิสก์ | ว่าง 3.2 TB |
| เครือข่าย | Tailscale `100.104.172.122` · มี IP สาธารณะ และ `ufw` ปิดอยู่ → **ทุก service ต้อง bind IP Tailscale เท่านั้น** |
| เครื่องมือ | tmux, jq, docker, python3 (ห้ามใช้รันโค้ดโปรเจก) |

## Ollama ที่ใช้ร่วม

- systemd บน host (ไม่ใช่ docker) เวอร์ชัน 0.34.0 · `OLLAMA_HOST=0.0.0.0` พอร์ต 11434 · ไม่มีการยืนยันตัวตน
- ไม่ได้ตั้ง `OLLAMA_NUM_PARALLEL` / `OLLAMA_MAX_LOADED_MODELS`
- โมเดล: `gemma4:12b` (7.6 GB) · `gemma4:latest` (9.6 GB) · `gemma4:26b` (18 GB, มี vision) · `qwen3.8:latest` (17 GB)
- **HRIS ใช้ `gemma4:12b` ปักถาวร** (โหลด 10 GB, context 262144, `keep_alive=-1`, cron keep-warm ทุก 10 นาที)
- เรียกจาก container บนเครื่องนี้: `extra_hosts: ["host.docker.internal:host-gateway"]` → `http://host.docker.internal:11434`
- เรียกจากเครื่องอื่นใน Tailscale: `http://100.104.172.122:11434`
- gemma4 ต้องปิด thinking (`think: false` ใน `/api/chat` หรือ `reasoning_effort: "none"` ใน `/v1`) ไม่งั้นคำตอบว่าง
- ส่ง `num_ctx` เองทุกคำขอ (ค่าเริ่มต้น 262144 กินหน่วยความจำมาก)

## ข้อห้าม

1. ห้าม pull / delete / create / copy / push โมเดลผ่าน API หรือ CLI โดยไม่ถามเจ้าของโปรเจก โดยเฉพาะ tag `gemma4:12b`
2. ถ้าใช้ `gemma4:12b` ร่วม **ห้ามส่ง `keep_alive`** (คำขอจะเขียนทับค่า -1 ของ HRIS แล้วโมเดลถูกปล่อย) · โมเดลอื่นส่ง `keep_alive` สั้น เช่น `10m`
3. ห้ามแก้ systemd ของ Ollama · ห้าม restart · ห้ามอัปเกรด (มี warning "unit changed on disk" อยู่ ห้ามไป daemon-reload เอง)
4. ห้ามรันงานหนักบน GPU ช่วง **02:30–04:00** (backup HRIS 02:30 · รอบทดสอบโมเดล 03:00 ราว 25 นาที)
5. ห้ามแตะโปรเจกอื่น: HRIS (compose `hrisapp` · `~/hris_obsidian` · พอร์ต 8090 · volume `hrisapp_*`) และ hr_recruit (compose `onprem` · พอร์ต 8080) · network `hrisjev_default` ก็ห้ามแตะ
6. ห้าม `docker system prune` · `docker volume prune` · `docker container prune` ทุกกรณี
7. ทุกคำสั่ง `docker compose` ต้องมี `-f deploy/docker-compose.yml` และไฟล์ประกาศ `name: ocl`
8. service ที่เปิดพอร์ตต้อง bind `100.104.172.122` ไม่ใช่ `0.0.0.0` · ตรวจพอร์ตว่างด้วย `ss -ltnp` ก่อน (พอร์ตของ OCL = **8100**)
9. งานยาว (build · ดาวน์โหลด · ประมวลผลชุดใหญ่) รันใน `tmux`
10. ห้ามรันโค้ดโปรเจกด้วย python3 ของเครื่อง ใช้ `uv run` ใน `/home/arsoft/ocl-agent` หรือ container ของโปรเจก

## งบหน่วยความจำ

HRIS ใช้ ~10 GB ถาวร · โมเดลของ OCL รวมกันไม่ควรเกิน ~40 GB เมื่อโหลด
ตรวจก่อนและหลังโหลดโมเดลทุกครั้ง:

```bash
curl -s http://127.0.0.1:11434/api/ps | jq .
```

ถ้าต้องการรับคำขอพร้อมกันหลายงานต้องตั้ง `OLLAMA_NUM_PARALLEL` ซึ่งกระทบ HRIS → เสนอเจ้าของโปรเจกก่อน

## พอร์ตและ compose ที่มีอยู่ (20 ต.ค. 2569)

พอร์ตใช้แล้ว: 22 · 53 · 631 · 7071 · 11434 · 127.0.0.1:{8080, 11000, 44049} · 100.104.172.122:{443, 8090, 43085} · 43498
compose: `hrisapp` (2 services) · `onprem` (3 services) · network ใหม่ของ `ocl` จะได้ 172.21.x
