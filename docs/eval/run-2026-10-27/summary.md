# Gemini vs Gemma · bench 2026-10-27T22:21:15

ค่าเฉลี่ยต่อ provider/โหมด (เทียบกับ reference = parser จากเล่มดิจิทัล) · รายละเอียดต่อเล่มใน results.csv

| provider | mode | books | info acc | PLO P/R | structure P/R | courses P/R | courses name/credits | LLM s/เล่ม | tokens in/out ต่อเล่ม | USD/เล่ม |
|---|---|---|---|---|---|---|---|---|---|---|
| ollama (gemma4:26b) | llm_only | 12 | 1.000 | 1.000/1.000 | 0.854/0.933 | 0.833/0.686 | 0.997/0.997 | 51.093 | 15137.500/5232.417 | 0.000 |
| ollama (gemma4:26b) | parser_first | 12 | 1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 33.192 | 8427.000/3375.000 | 0.000 |

หมายเหตุ: parser_first = ความแม่นยำของระบบจริง · llm_only = ความแม่นยำของโมเดลเอง · reference ยังต้องให้ Admin spot-check (E3)
