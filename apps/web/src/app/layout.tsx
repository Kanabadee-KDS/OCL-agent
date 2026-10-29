import type { Metadata } from "next";
import { Anuphan, IBM_Plex_Sans_Thai } from "next/font/google";
import "./design.css";
import "./app.css";

const display = Anuphan({ subsets: ["thai", "latin"], weight: ["400", "500", "600", "700"], variable: "--f-display-next" });
const body = IBM_Plex_Sans_Thai({ subsets: ["thai", "latin"], weight: ["400", "500", "600"], variable: "--f-body-next" });

export const metadata: Metadata = {
  title: "ระบบบริหารจัดการหลักสูตรและการรับรองสมรรถนะดิจิทัล · มศว",
  description: "ระบบบริหารจัดการหลักสูตรและการรับรองสมรรถนะดิจิทัล (Skill Transcript) มหาวิทยาลัยศรีนครินทรวิโรฒ",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="th">
      <body className={`${display.variable} ${body.variable}`}>{children}</body>
    </html>
  );
}
