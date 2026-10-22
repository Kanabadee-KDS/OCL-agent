import { Suspense } from "react";
import { CurriculumClient } from "./curriculum-client";

export default function CurriculumPage() {
  return (
    <Suspense fallback={<div className="card pad">กำลังโหลด…</div>}>
      <CurriculumClient />
    </Suspense>
  );
}
