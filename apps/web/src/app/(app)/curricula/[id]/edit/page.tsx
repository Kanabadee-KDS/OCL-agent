"use client";

// cur-edit (mock · US-M1-04): the คู่มือหลักสูตร section by section, with ✓ progress, previous/
// next, save draft. Fields, their order and what is required come from the API's spec
// (ocl_api.curriculum_form); who may change which หมวด now comes with the curriculum.
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { curricula, curriculumForm, STATUS_KIND, type CurriculumDetail, type FormSpec, type SectionData } from "@/lib/api";
import { getPath, setPath } from "@/lib/form";
import { canMenu } from "@/lib/nav";
import { Note, PageHead, Pill } from "@/components/ui";
import { BackLink, useToast } from "@/components/kit";
import { Field, type Ctx } from "./fields";

const ORDER = ["0", "1", "2", "3", "4", "5"];

export default function CurriculumEditPage() {
  const { id } = useParams<{ id: string }>();
  const { data: session } = useSession();
  const toast = useToast();
  const [d, setD] = useState<CurriculumDetail | null>(null);
  const [spec, setSpec] = useState<FormSpec | null>(null);
  const [secs, setSecs] = useState<SectionData | null>(null);
  const [cur, setCur] = useState("0");
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [dd, ss] = await Promise.all([curricula.get(id), curriculumForm.sections(id)]);
    setD(dd);
    setSecs(ss);
    return ss;
  }, [id]);
  useEffect(() => {
    Promise.all([curricula.get(id), curriculumForm.sections(id), curriculumForm.spec()])
      .then(([dd, ss, sp]) => { setD(dd); setSecs(ss); setSpec(sp); setDraft(ss["0"]?.data ?? {}); })
      .catch((e) => setErr((e as Error).message));
  }, [id]);

  const saved = useMemo(() => secs?.[cur]?.data ?? {}, [secs, cur]);
  const dirty = useMemo(() => JSON.stringify(saved) !== JSON.stringify(draft), [saved, draft]);
  const editable = !!d?.editable.includes(cur);

  function go(n: string) {
    if (dirty && !window.confirm("ยังไม่ได้บันทึกการแก้ในหมวดนี้ ออกจากหมวดโดยไม่บันทึก?")) return;
    setCur(n);
    setDraft(secs?.[n]?.data ?? {});
  }

  async function save() {
    setBusy(true);
    try {
      await curriculumForm.save(id, cur, draft);
      const ss = await reload();
      setDraft(ss[cur]?.data ?? {});
      toast("บันทึกร่างแล้ว");
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy(false);
    }
  }

  const ctx: Ctx = {
    draftId: id,
    sections: { ...Object.fromEntries(Object.entries(secs ?? {}).map(([k, v]) => [k, v.data])), [cur]: draft },
    readOnly: !editable,
    canAddOption: canMenu(session?.user?.perms, "u1", "edit"),
    onAddOption: async (key, value) => {
      try { setSpec(await curriculumForm.addOption(key, value)); toast(`เพิ่มตัวเลือก "${value}" แล้ว`); } catch (e) { toast((e as Error).message, "err"); }
    },
    onBook: async (file) => {
      if (dirty) { toast("บันทึกการแก้ในหมวด 0 ก่อนแนบไฟล์", "err"); return; }
      try {
        await curriculumForm.uploadBook(id, file);
        const ss = await reload();
        setDraft(ss["0"]?.data ?? {});
        toast("แนบไฟล์เล่มอนุมัติแล้ว");
      } catch (e) { toast((e as Error).message, "err"); }
    },
  };

  if (err) return <><BackLink href={`/curricula/${id}`}>กลับไปหน้าคู่มือ</BackLink><Note kind="warn">{err}</Note></>;
  if (!d || !spec || !secs) return <div className="card pad">กำลังโหลด…</div>;
  const groups = spec.sections[cur];
  const values = { ...(getPath(ctx.sections["0"], "info.values") as object), ...(getPath(draft, "info.values") as object) } as Record<string, unknown>;
  const idx = ORDER.indexOf(cur);
  const p = d.progress[cur];
  return (
    <>
      <BackLink href={`/curricula/${id}`}>กลับไปหน้าคู่มือ</BackLink>
      <PageHead
        crumb={["บริหารข้อมูลหลักสูตร", "คู่มือหลักสูตร", d.name_th ?? ""]}
        title={d.name_th ?? "คู่มือหลักสูตร"}
        sub={<><Pill kind={STATUS_KIND[d.status]}>{d.status_th}</Pill> · กรอกทีละหมวด ช่องที่มี * จำเป็นก่อนส่งให้คณะตรวจสอบ</>}
        actions={<button type="button" className="btn" disabled title="Preview แบบเล่มและ PDF อยู่ในงาน FS-2d">Preview</button>}
      />
      <div className="grid" style={{ gridTemplateColumns: "240px minmax(0,1fr)", alignItems: "start" }}>
        <nav className="card pad stack" aria-label="หมวดของคู่มือ" style={{ gap: 4, position: "sticky", top: 80 }}>
          {ORDER.map((n) => {
            const pr = d.progress[n];
            const done = pr && pr.done === pr.total;
            return (
              <button key={n} type="button" className={`nav-item ${n === cur ? "active" : ""}`} aria-current={n === cur ? "step" : undefined}
                style={{ color: "inherit", justifyContent: "space-between" }} onClick={() => go(n)}>
                <span>{spec.labels[n]}</span>
                <span className="small">{done ? "✓" : pr ? `${pr.done}/${pr.total}` : ""}</span>
              </button>
            );
          })}
        </nav>
        <div className="stack">
          {!editable && <Note kind="info">หมวดนี้ดูได้อย่างเดียวในสถานะ &ldquo;{d.status_th}&rdquo; สำหรับบทบาทของคุณ</Note>}
          {p && p.missing.length > 0 && <Note kind="warn">ยังขาด {p.missing.length} รายการ: {p.missing.join(" · ")}</Note>}
          {groups ? groups.map((g) => (
            <section key={g.title} className="card pad stack">
              <h2 className="h2" style={{ margin: 0 }}>{g.title}</h2>
              <div className="form-grid">
                {g.fields.map((f) => {
                  const required = f.required || (!!f.required_when && values[f.required_when.key] === f.required_when.equals);
                  return <Field key={f.key} f={f} required={required} ctx={ctx} value={f.path === "-" ? undefined : getPath(draft, f.path)}
                    onChange={(v) => setDraft((x) => setPath(x, f.path, v))} />;
                })}
              </div>
            </section>
          )) : (
            <section className="card pad stack">
              <h2 className="h2" style={{ margin: 0 }}>{spec.labels[cur] ?? `หมวด ${cur}`}</h2>
              <p style={{ margin: 0 }}>ตัวแก้หมวด 3 (PLO · KSEC) และหมวด 4 (โครงสร้าง · รายวิชา · Mapping) เปิดใช้ในงานถัดไป (FS-2c)</p>
              {d.job_id && <p className="small" style={{ margin: 0 }}>ระหว่างนี้แก้ได้ที่ <Link href={`/import/${d.job_id}`}>หน้าตรวจข้อมูลที่นำเข้า</Link> ตามสิทธิ์เดียวกัน</p>}
            </section>
          )}
          <div className="between">
            <button type="button" className="btn" disabled={idx === 0} onClick={() => go(ORDER[idx - 1])}>‹ หมวดก่อนหน้า</button>
            {groups && editable && <button type="button" className="btn primary" disabled={busy || !dirty} onClick={save}>{busy ? "กำลังบันทึก…" : dirty ? "บันทึกร่าง" : "บันทึกแล้ว"}</button>}
            <button type="button" className="btn" disabled={idx === ORDER.length - 1} onClick={() => go(ORDER[idx + 1])}>หมวดถัดไป ›</button>
          </div>
        </div>
      </div>
    </>
  );
}
