# Gemini vs Gemma · bench 2026-10-23T16:21:19

ค่าเฉลี่ยต่อ provider/โหมด (เทียบกับ reference = parser จากเล่มดิจิทัล) · รายละเอียดต่อเล่มใน results.csv

| provider | mode | books | info acc | PLO P/R | structure P/R | courses P/R | courses name/credits | LLM s/เล่ม | tokens in/out ต่อเล่ม | USD/เล่ม |
|---|---|---|---|---|---|---|---|---|---|---|
| ollama (gemma4:26b) | parser_first | 12 | 1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 33.934 | 8467.500/3365.167 | 0.000 |

หมายเหตุ: parser_first = ความแม่นยำของระบบจริง · llm_only = ความแม่นยำของโมเดลเอง · reference ยังต้องให้ Admin spot-check (E3)
