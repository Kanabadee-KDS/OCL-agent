# Gemini vs Gemma · bench 2026-10-23T00:08:08

ค่าเฉลี่ยต่อ provider/โหมด (เทียบกับ reference = parser จากเล่มดิจิทัล) · รายละเอียดต่อเล่มใน results.csv

| provider | mode | books | info acc | PLO P/R | structure P/R | courses P/R | courses name/credits | LLM s/เล่ม | tokens in/out ต่อเล่ม | USD/เล่ม |
|---|---|---|---|---|---|---|---|---|---|---|
| gemini (gemini-flash-latest) | llm_only | 12 | 1.000 | 0.833/0.833 | 0.972/0.917 | 0.833/0.645 | 0.996/0.698 | 41.004 | 13104.750/5379.500 | 0.030 |
| gemini (gemini-flash-latest) | parser_first | 12 | 1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 27.154 | 8699.750/3806.917 | 0.021 |
| ollama (gemma4:26b) | llm_only | 12 | 0.607 | 1.000/1.000 | 0.854/0.933 | 0.833/0.686 | 0.997/0.997 | 52.880 | 12038.167/5221.083 | 0.000 |
| ollama (gemma4:26b) | parser_first | 12 | 1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 | 35.068 | 7876.333/3387.167 | 0.000 |

หมายเหตุ: parser_first = ความแม่นยำของระบบจริง · llm_only = ความแม่นยำของโมเดลเอง · reference ยังต้องให้ Admin spot-check (E3)
