# Datasheets

The PDFs this design was transcribed from are **not committed** — they are
Quectel's and Qualcomm's documents, not mine to redistribute. Fetch them:

```bash
python3 tools/fetch_datasheets.py
```

| File | Document | Used for |
|---|---|---|
| `LC29H_Hardware_Design_V1.3.pdf` | Quectel LC29H Series Hardware Design, V1.3 (2024-07-30) | Table 6 pin description, Figure 4 pin assignment, Figure 17 active-antenna reference, Figure 19 land pattern, section 3.2 decoupling |
| `SAW_B39162B8389P810.pdf` | Qualcomm RF360 B8389 SAW RF Filter, V2.1 (2022-11-15) | section 4 pin configuration, section 5 matching circuit (50 Ω ∥ 5.1 nH), section 6 pass bands, Figure 2 land pattern |

Everything transcribed from them is cited in place — see
`tools/bootstrap/gen_custom_symbols.py` and `tools/bootstrap/gen_footprints.py`.
