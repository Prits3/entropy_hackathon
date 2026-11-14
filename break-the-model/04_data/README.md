# Captured data — SYNTHETIC

`patients_captured.json` holds patient-like rows reached from Riley during the Break the Model
challenge. **This is fictional, synthetic challenge data, not real people's information:**
every email uses a reserved `example.com` / `example.net` / `example.org` domain, and the
hospital, names, MRNs, phones and DOBs are all generated for the exercise.

- `_provenance` block inside the JSON records how/when it was collected.
- 343 unique MRNs; 228 rows fully populated (name + phone + email).
- Validate anytime (no network) with `../03_scripts/validate_capture.py`.

Included here because it is part of the challenge record; it contains no real PII.
