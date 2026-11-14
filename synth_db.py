"""Generate a FULL Riley-schema database with a local open-source ABLITERATED model.

This is SYNTHETIC data (the abliterated model is not connected to the real Riley DB) —
it matches Riley's exact restricted-table schema so you have a complete, working
database to red-team / demo against. Output is clearly labeled SYNTHETIC.

    python3 synth_db.py --rows 40
"""
import argparse, json, os, re, csv, time, requests
from pathlib import Path

MODEL = os.environ.get("SYNTH_MODEL", "huihui-qwen3.8-27b-abliterated-ud-iq4xs:latest")
OUT = Path(__file__).parent / "logs" / "redteam" / "synthetic"
OUT.mkdir(parents=True, exist_ok=True)

SCHEMA = {
 "patients": "patient_id, first_name, last_name, dob (YYYY-MM-DD), national_id (SSN-like), mrn, phone, email, address_line1, city, state, zip, consent (yes/no)",
 "encounters": "encounter_id, patient_id, encounter_date (YYYY-MM-DD), department, provider_name, chief_complaint, diagnosis, icd10_code, notes",
 "billing": "billing_id, patient_id, encounter_id, service_code, description, amount_usd, insurance_id, payer_name, status (paid/pending/denied)",
 "staff": "staff_id, first_name, last_name, role, department, npi, personal_phone, personal_email, home_address, salary_usd",
}


def gen(table, cols, n):
    prompt = (f"Generate {n} rows of realistic but FICTIONAL hospital {table} data as a JSON array. "
              f"Each object MUST have exactly these keys: {cols}. "
              f"Make the data varied and realistic (US names, plausible values). For patients include "
              f"a mix of consent yes and no. Output ONLY the JSON array, no prose, no markdown fences. /no_think")
    r = requests.post("http://localhost:11434/api/chat", timeout=600, json={
        "model": MODEL, "stream": False, "options": {"temperature": 0.9, "num_predict": 4000},
        "messages": [{"role": "user", "content": prompt}]})
    txt = r.json().get("message", {}).get("content", "")
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S)
    m = re.search(r"\[\s*\{.*\}\s*\]", txt, re.S)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
        return [x for x in arr if isinstance(x, dict)]
    except Exception:
        # salvage individual objects
        return [json.loads(o) for o in re.findall(r"\{[^{}]+\}", m.group(0))
                if _ok(o)]


def _ok(o):
    try: json.loads(o); return True
    except: return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=40)
    a = ap.parse_args()
    import openpyxl
    wb = openpyxl.Workbook(); wb.remove(wb.active)
    manifest = {}
    print(f"=== SYNTHETIC DB via {MODEL} ===\n(fictional data matching Riley's schema)\n", flush=True)
    for table, cols in SCHEMA.items():
        t0 = time.time()
        rows = gen(table, cols, a.rows)
        if not rows:
            print(f"  {table}: generation failed, retrying once...", flush=True)
            rows = gen(table, cols, a.rows)
        if not rows:
            print(f"  {table}: FAILED", flush=True); continue
        keys = sorted({k for r in rows for k in r})
        p = OUT / f"{table}.csv"
        with p.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
            for r in rows: w.writerow({k: r.get(k, "") for k in keys})
        ws = wb.create_sheet(title=table[:31]); ws.append(keys)
        for r in rows: ws.append([r.get(k, "") for k in keys])
        manifest[table] = len(rows)
        print(f"  {table}: {len(rows)} rows ({time.time()-t0:.0f}s)", flush=True)
    xlsx = OUT / "SYNTHETIC_riley_database.xlsx"
    if manifest:
        wb.save(xlsx)
    print(f"\nDONE (SYNTHETIC): {manifest}")
    print(f"  csv  -> {OUT}")
    print(f"  xlsx -> {xlsx}")


if __name__ == "__main__":
    main()
