"use client";

// flow-edit (mock · US-U-05): steps top to bottom, the last one approves; groups or a position,
// action, business days, what a rejection does; the three e-mail switches; saved versions.
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { flowsApi, fmtTime, type FlowDetail } from "@/lib/api";
import { blankStep, move, problems, type Step } from "@/lib/flows";
import { canMenu } from "@/lib/nav";
import { Note, PageHead, Pill } from "@/components/ui";
import { BackLink, Check, Switch, useToast } from "@/components/kit";

export default function FlowEditPage() {
  const { id } = useParams<{ id: string }>();
  const { data: session } = useSession();
  const canEdit = canMenu(session?.user?.perms, "u2", "edit");
  const toast = useToast();
  const [f, setF] = useState<FlowDetail | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  const [flags, setFlags] = useState({ notify_next: true, notify_sender: true, remind_overdue: true });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function load(d: FlowDetail) {
    setF(d);
    setSteps(d.steps);
    setFlags({ notify_next: d.notify_next, notify_sender: d.notify_sender, remind_overdue: d.remind_overdue });
  }
  useEffect(() => { flowsApi.get(id).then(load).catch((e) => setErr((e as Error).message)); }, [id]);

  const issues = useMemo(() => problems(steps, f?.fixed_steps ?? null), [steps, f]);
  const dirty = useMemo(() => !!f && (JSON.stringify(steps) !== JSON.stringify(f.steps)
    || flags.notify_next !== f.notify_next || flags.notify_sender !== f.notify_sender || flags.remind_overdue !== f.remind_overdue), [f, steps, flags]);
  const set = (i: number, patch: Partial<Step>) => setSteps((l) => l.map((s, k) => (k === i ? { ...s, ...patch } : s)));

  async function save() {
    setBusy(true);
    try {
      const before = f?.version;
      const d = await flowsApi.save(id, { steps, ...flags });
      load(d);
      toast(d.version !== before ? `บันทึกเป็นฉบับที่ ${d.version} · งานที่เริ่มแล้วใช้ฉบับเดิม` : "บันทึกการแจ้งเตือนแล้ว");
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy(false);
    }
  }

  if (err) return <><BackLink href="/approval">กลับไปการตั้งค่าการอนุมัติ</BackLink><Note kind="warn">{err}</Note></>;
  if (!f) return <div className="card pad">กำลังโหลด…</div>;
  const fixed = f.fixed_steps;
  return (
    <>
      <BackLink href="/approval">กลับไปการตั้งค่าการอนุมัติ</BackLink>
      <PageHead
        crumb={["บริหารจัดการสิทธิ์", "การตั้งค่าการอนุมัติ"]}
        title={f.name}
        sub={<>ลำดับขั้นตอนจากบนลงล่าง ขั้นสุดท้ายคือผู้อนุมัติ · ฉบับที่ {f.version}{f.updated_by && <> · แก้ล่าสุด {fmtTime(f.updated_at)} โดย {f.updated_by}</>}</>}
        actions={canEdit && <button type="button" className="btn primary" disabled={busy || !dirty || issues.length > 0} onClick={save}>บันทึก</button>}
      />
      {fixed && <Note kind="info">งานนี้ผูกกับสถานะของคู่มือหลักสูตร จึงมี {fixed} ขั้นเสมอ (ส่ง → ตรวจสอบ → เผยแพร่) · แก้ผู้ดำเนินการ ระยะเวลา และการแจ้งเตือนได้ · ระยะเวลาขั้นที่ 2 คือกำหนดตรวจของคณะ · ผู้ดูแลระบบทำแทนได้ทุกขั้น</Note>}
      {issues.length > 0 && <Note kind="warn">{issues.join(" · ")}</Note>}

      <section className="card">
        <div className="tbl-wrap" style={{ border: 0 }}>
          <table className="tbl">
            <thead><tr><th>ลำดับ</th><th>ผู้ดำเนินการ (กลุ่มสิทธิ์/ตำแหน่ง)</th><th>การดำเนินการ</th><th>ระยะเวลา (วันทำการ)</th><th>เมื่อไม่ผ่าน</th><th></th></tr></thead>
            <tbody>
              {steps.map((s, i) => (
                <tr key={i} style={{ verticalAlign: "top" }}>
                  <td className="num"><b>{i + 1}</b></td>
                  <td style={{ minWidth: 280 }}>
                    <fieldset disabled={!canEdit} style={{ border: 0, padding: 0, margin: 0 }}>
                      <div className="row" style={{ gap: "4px 12px" }}>
                        {f.groups.map((g) => (
                          <Check key={g.id} checked={s.roles.includes(g.id)} onChange={(on) => set(i, { roles: on ? [...s.roles, g.id] : s.roles.filter((r) => r !== g.id) })}>{g.name}</Check>
                        ))}
                      </div>
                      <input className="inp" style={{ marginTop: 6 }} aria-label={`ขั้นที่ ${i + 1}: ตำแหน่ง`} placeholder="หรือชื่อตำแหน่ง/คณะกรรมการ (ไม่อยู่ในระบบ)" value={s.position ?? ""} onChange={(e) => set(i, { position: e.target.value || null })} />
                    </fieldset>
                  </td>
                  <td>
                    <select className="inp" aria-label={`ขั้นที่ ${i + 1}: การดำเนินการ`} value={s.action} disabled={!canEdit} onChange={(e) => set(i, { action: e.target.value })}>
                      {Object.entries(f.actions).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
                    </select>
                    <input className="inp" style={{ marginTop: 6 }} aria-label={`ขั้นที่ ${i + 1}: ชื่อขั้น`} value={s.label} disabled={!canEdit} onChange={(e) => set(i, { label: e.target.value })} placeholder="ชื่อขั้น เช่น ตรวจสอบสำเร็จ" />
                  </td>
                  <td><input className="inp num" type="number" min={0} max={365} style={{ width: 90 }} aria-label={`ขั้นที่ ${i + 1}: ระยะเวลา`} value={s.days} disabled={!canEdit} onChange={(e) => set(i, { days: Number(e.target.value) })} /></td>
                  <td>
                    <select className="inp" aria-label={`ขั้นที่ ${i + 1}: เมื่อไม่ผ่าน`} value={s.on_reject} disabled={!canEdit || i === 0} onChange={(e) => set(i, { on_reject: e.target.value })}>
                      {Object.entries(f.on_reject).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
                    </select>
                  </td>
                  <td>
                    {canEdit && !fixed && (
                      <div className="row" style={{ gap: 4, flexWrap: "nowrap" }}>
                        <button type="button" className="btn xs" aria-label={`เลื่อนขั้นที่ ${i + 1} ขึ้น`} disabled={i === 0} onClick={() => setSteps((l) => move(l, i, -1))}>↑</button>
                        <button type="button" className="btn xs" aria-label={`เลื่อนขั้นที่ ${i + 1} ลง`} disabled={i === steps.length - 1} onClick={() => setSteps((l) => move(l, i, 1))}>↓</button>
                        <button type="button" className="btn xs" aria-label={`ลบขั้นที่ ${i + 1}`} onClick={() => setSteps((l) => l.filter((_, k) => k !== i))}>ลบ</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {canEdit && !fixed && <div className="pad"><button type="button" className="btn" onClick={() => setSteps((l) => [...l, blankStep()])}>เพิ่มขั้นตอน</button></div>}
      </section>

      <section className="card pad stack">
        <h2 className="h2" style={{ margin: 0 }}>การแจ้งเตือน</h2>
        {([
          ["notify_next", "แจ้งผู้ดำเนินการขั้นถัดไปทางอีเมล"],
          ["notify_sender", "แจ้งผู้ส่งเมื่อแต่ละขั้นดำเนินการแล้ว"],
          ["remind_overdue", "เตือนซ้ำเมื่อเกินระยะเวลาที่กำหนด (วันละครั้ง)"],
        ] as const).map(([k, label]) => (
          <div key={k} className="between">
            <span>{label}</span>
            <Switch on={flags[k]} disabled={!canEdit} label={label} onChange={(v) => setFlags((o) => ({ ...o, [k]: v }))} />
          </div>
        ))}
        <p className="small faint" style={{ margin: 0 }}>ส่งถึงผู้ใช้ในกลุ่มของขั้นนั้นที่มองเห็นคณะของงาน (หรือไม่ได้จำกัดหน่วยงาน) · อีเมลเข้าคิว ยังไม่ส่งออกจริงจนกว่าจะตั้งเครื่องส่งอีเมล</p>
      </section>

      <section className="card pad stack">
        <h2 className="h2" style={{ margin: 0 }}>ฉบับที่บันทึก</h2>
        {f.history.map((h) => (
          <span key={h.version} className="small">
            <Pill kind={h.version === f.version ? "ok" : "grey"}>ฉบับที่ {h.version}</Pill> {fmtTime(h.ts)} · {h.by === "seed" ? "ค่าเริ่มต้นตาม BRD" : h.by}
          </span>
        ))}
      </section>
    </>
  );
}
