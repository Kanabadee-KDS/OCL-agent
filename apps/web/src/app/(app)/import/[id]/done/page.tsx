import { Suspense } from "react";
import DoneClient from "./done-client";

export default function DonePage() {
  return (
    <Suspense fallback={<div className="card pad">กำลังโหลด…</div>}>
      <DoneClient />
    </Suspense>
  );
}
