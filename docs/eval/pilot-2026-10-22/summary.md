# Gemini vs Gemma · bench 2026-10-22T20:51:50

ค่าเฉลี่ยต่อ provider/โหมด (เทียบกับ reference = parser จากเล่มดิจิทัล) · รายละเอียดต่อเล่มใน results.csv

| provider | mode | books | info acc | PLO P/R | structure P/R | courses P/R | courses name/credits | LLM s/เล่ม | tokens in/out ต่อเล่ม | USD/เล่ม |
|---|---|---|---|---|---|---|---|---|---|---|
| gemini (gemini-flash-latest) | llm_only | 1 | 1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/0.754 | 1.000/0.977 | 59.990 | 14346.000/7287.000 | 0.038 |
| gemini (gemini-flash-latest) | parser_first | 1 | 1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 26.890 | 10781.000/3795.000 | 0.022 |
| ollama (gemma4:26b) | llm_only | 1 | 0.600 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 75.300 | 14431.000/7633.000 | 0.000 |
| ollama (gemma4:26b) | parser_first | 1 | 1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 57.460 | 10832.000/4891.000 | 0.000 |

หมายเหตุ: parser_first = ความแม่นยำของระบบจริง · llm_only = ความแม่นยำของโมเดลเอง · reference ยังต้องให้ Admin spot-check (E3)
