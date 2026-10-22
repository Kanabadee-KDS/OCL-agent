import { Suspense } from "react";
import ReviewClient from "./review-client";

export default function ReviewPage() {
  return (
    <Suspense fallback={<div className="card pad">กำลังโหลด…</div>}>
      <ReviewClient />
    </Suspense>
  );
}
