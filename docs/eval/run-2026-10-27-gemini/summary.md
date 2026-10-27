# Gemini vs Gemma · bench 2026-10-27T22:32:09

ค่าเฉลี่ยต่อ provider/โหมด (เทียบกับ reference = parser จากเล่มดิจิทัล) · รายละเอียดต่อเล่มใน results.csv

| provider | mode | books | info acc | PLO P/R | structure P/R | courses P/R | courses name/credits | LLM s/เล่ม | tokens in/out ต่อเล่ม | USD/เล่ม |
|---|---|---|---|---|---|---|---|---|---|---|
| gemini (gemini-flash-latest) | llm_only | 2 | 1.000 | 1.000/1.000 | 0.900/0.900 | 0.000/0.000 | –/– | 32.680 | 7582.000/3706.500 | 0.020 |
| gemini (gemini-flash-latest) | parser_first | 2 | 1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 5.710 | 3501.000/609.000 | 0.005 |

หมายเหตุ: parser_first = ความแม่นยำของระบบจริง · llm_only = ความแม่นยำของโมเดลเอง · reference ยังต้องให้ Admin spot-check (E3)
