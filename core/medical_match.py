"""Auto-map an uploaded medical document to a requirement by its filename.

Ported from the original Flask build's MEDICAL_FILENAME_KEYWORDS table: the
filename is lowercased and matched against substring keywords, so e.g.
"cbc_report.pdf" -> "CBC", "chest-xray.jpg" -> "X-Ray Chest ...".
"""

# (keyword substring, requirement_name) — order matters; first match wins.
MEDICAL_FILENAME_KEYWORDS = [
    ("cbc", "CBC"),
    ("esr", "ESR"),
    ("lft", "LFTs"),
    ("rft", "RFTs (eGFR included)"),
    ("egfr", "RFTs (eGFR included)"),
    ("hba1c", "HbA1C"),
    ("lipid", "Lipid Profile (Fasting)"),
    ("hbsag", "HBsAg"),
    ("hcv", "Anti HCV"),
    ("urine", "Urine C/E"),
    ("xray", "X-Ray Chest (with Radiologist Report)"),
    ("x-ray", "X-Ray Chest (with Radiologist Report)"),
    ("chest", "X-Ray Chest (with Radiologist Report)"),
    ("electrolyte", "Serum Electrolytes"),
    ("uric", "Uric Acid"),
    ("calcium", "Serum Calcium"),
    ("psa", "PSA"),
    ("ca125", "CA-125"),
    ("ca-125", "CA-125"),
    ("fitness", "Fitness Certificate by Consultant"),
]

ALLOWED_MEDICAL_EXTS = {"pdf", "jpg", "jpeg", "png"}


def auto_map_filename(filename):
    """Return the requirement name a filename maps to, or None."""
    lower = (filename or "").lower()
    for keyword, requirement in MEDICAL_FILENAME_KEYWORDS:
        if keyword in lower:
            return requirement
    return None


def allowed_medical_file(filename):
    return "." in (filename or "") and \
        filename.rsplit(".", 1)[1].lower() in ALLOWED_MEDICAL_EXTS


# ── Age / gender applicability ───────────────────────────────────────────────
def employee_age(employee):
    """Age in years from date_of_birth, or None if unknown."""
    from datetime import date
    dob = getattr(employee, "date_of_birth", None)
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def medical_applicability(employee, meta):
    """Decide whether a catalog test applies to an employee.

    Returns (applies: bool, required: bool, note: str).

    Rules (per spec):
      * Tests with no rule apply to everyone and are required.
      * Age < min_age (when age known)      -> not applicable (e.g. PSA/CA-125 under 40).
      * Gender clearly mismatched           -> not applicable.
      * If age and/or gender are UNKNOWN but could match -> applies, but OPTIONAL,
        with a note saying when it's actually required.
    """
    meta = meta or {}
    gender_req = (meta.get("gender") or "").strip().lower() or None
    min_age = meta.get("min_age")

    if not gender_req and min_age is None:
        return True, True, ""  # universal test

    age = employee_age(employee)
    gender = (getattr(employee, "gender", "") or "").strip().lower() or None
    age_known = age is not None
    gender_known = gender in ("male", "female")

    # Definite exclusions
    if min_age is not None and age_known and age < min_age:
        return False, False, ""
    if gender_req and gender_known and gender != gender_req:
        return False, False, ""

    # Applies. Required only when every condition is definitely satisfied.
    uncertain = []
    if min_age is not None and not age_known:
        uncertain.append(f"you are {min_age} or above")
    if gender_req and not gender_known:
        uncertain.append(f"you are {gender_req}")

    if not uncertain:
        return True, True, ""
    return True, False, "Optional — required only if " + " and ".join(uncertain) + "."
