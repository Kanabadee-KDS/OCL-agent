"use client";

// Preview of the report, printable to A4.
import { DocPrint } from "@/components/m2doc";

export default function Page() {
  return <DocPrint doc="report" />;
}
