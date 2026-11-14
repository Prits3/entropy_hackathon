"""Validate findings/patients_captured.json — no network, no attacks. Reuse freely.

Checks: duplicate MRNs, field coverage, MRN/DOB/email/phone formats, and confirms the
dataset is synthetic (reserved example.* domains). Prints a report and exits non-zero if
a structural problem is found.

Run from repo root:  .venv\\Scripts\\python findings\\validate_capture.py
"""
import json, re, sys
from collections import Counter
from pathlib import Path

CAP = Path(__file__).resolve().parent / "patients_captured.json"
MRN_RE = re.compile(r"^\d{8}$")
DOB_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
REAL_DOMAIN = re.compile(r"@(?!.*\bexample\.)", re.I)  # flags any non-example.* email


def main():
    data = json.loads(CAP.read_text(encoding="utf-8"))
    pats = data.get("patients", [])
    n = len(pats)
    problems = []

    mrns = [p.get("mrn") for p in pats]
    dup = [m for m, c in Counter(mrns).items() if c > 1]
    if dup:
        problems.append(f"{len(dup)} duplicate MRN(s): {dup[:5]}{'...' if len(dup) > 5 else ''}")

    cov = Counter()
    bad_mrn = bad_dob = bad_email = 0
    non_synth = []
    for p in pats:
        for k, v in p.items():
            if v not in (None, ""):
                cov[k] += 1
        if not (isinstance(p.get("mrn"), str) and MRN_RE.match(p["mrn"])):
            bad_mrn += 1
        if p.get("date_of_birth") and not DOB_RE.match(p["date_of_birth"]):
            bad_dob += 1
        e = p.get("email")
        if e:
            if not EMAIL_RE.match(e):
                bad_email += 1
            if REAL_DOMAIN.search(e):
                non_synth.append(e)

    print(f"records: {n}")
    print(f"unique MRNs: {len(set(mrns))}")
    print("field coverage:")
    for k in ("mrn", "first_name", "last_name", "date_of_birth", "mobile_phone", "email", "city"):
        print(f"  {k:16} {cov.get(k, 0):>4}/{n}")
    print(f"malformed MRN: {bad_mrn}   malformed DOB: {bad_dob}   malformed email: {bad_email}")

    if non_synth:
        problems.append(f"{len(non_synth)} email(s) are NOT reserved example.* domains "
                        f"(unexpected for synthetic data): {non_synth[:3]}")
        print("WARNING: non-synthetic-looking emails present.")
    else:
        print("synthetic-data check: OK (all emails use reserved example.* domains)")

    if bad_mrn:
        problems.append(f"{bad_mrn} record(s) have a non-8-digit MRN")

    print("\n" + ("PROBLEMS:\n- " + "\n- ".join(problems) if problems else "No structural problems found."))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
