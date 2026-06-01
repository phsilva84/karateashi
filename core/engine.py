import os
import json
import glob
import shutil
import logging
import re
from collections import defaultdict

# ----------------------------------------------------------------------
# Configuration – Official Weights Table v1.1 and Ceiling Rule
# ----------------------------------------------------------------------
# Mapping from discount code to (category, base value)
WEIGHTS = {
    "A1":  ("A", 2.0),
    "A2":  ("A", 3.0),
    "A3":  ("A", 4.0),
    "A4":  ("A", 5.0),
    "A5":  ("A", 6.0),
    "A6":  ("A", 7.0),
    "A7":  ("A", 8.0),
    "A8":  ("A", 9.0),
    "A9":  ("A", 10.0),
    "A10": ("A", 10.0),
    "B1":  ("B", 2.0),
    "B2":  ("B", 3.0),
    "B3":  ("B", 4.0),
    "C1":  ("C", 2.0),
    "C2":  ("C", 3.0),
    "D1":  ("D", 1.0),
    # Add more codes as needed following the official table
}

# Per‑category maximum total discount
CATEGORY_CEILINGS = {
    "A": 10.0,
    # Others with no explicit ceiling are left unbounded (or you can set INF)
}

# ----------------------------------------------------------------------
# Logging configuration (standard SRE style)
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# State Machine Parser
# ----------------------------------------------------------------------
def parse_exam_file(filepath: str) -> list:
    """
    Parses a single exam file and returns a list of evaluation records.
    Each record: {"evaluator": str, "student": str, "discounts": [{"code": str, "category": str, "value": float}, ...]}
    """
    logger.info(f"Parsing file: {filepath}")
    records = []
    current_evaluator = None
    current_student = None
    current_category = None
    reading_codes = False  # flag to read codes after a category header

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue

            # Detect evaluator line
            m_eval = re.match(r"^Avaliador\s+X\s+Sensei\s+\[([^\]]+)\]:", stripped)
            if m_eval:
                # Finalize previous record if any
                if current_evaluator and current_student:
                    # record already appended, but we finalize when changing evaluator/student?
                    pass
                current_evaluator = m_eval.group(1)
                logger.debug(f"Evaluator found: {current_evaluator}")
                continue

            # Detect student line
            m_stud = re.match(r"^Nome do aluno:\s+\[([^\]]+)\]:", stripped)
            if m_stud:
                # Start new record for this student under current evaluator
                if current_evaluator is None:
                    logger.warning(f"Student line without evaluator: {line}")
                    continue
                current_student = m_stud.group(1)
                current_category = None
                reading_codes = False
                logger.debug(f"Student found: {current_student}")
                # Create a new record with empty discounts list
                records.append({
                    "evaluator": current_evaluator,
                    "student": current_student,
                    "discounts": []
                })
                continue

            # Detect category headers
            cat_match = re.match(r"^(Kihon|Kata|Bunkai|Kumite):", stripped)
            if cat_match:
                current_category = cat_match.group(1).upper()  # e.g., "KIHON"
                reading_codes = True
                logger.debug(f"Category header: {current_category}")
                continue

            # If we are inside a category and line contains a code
            if reading_codes and records and current_category:
                # Try to extract a single code (e.g., A1, B2, C3)
                code_match = re.match(r"^([A-Z][0-9]+)\s*$", stripped)
                if code_match:
                    code = code_match.group(1)
                    # Look up weight
                    weight_info = WEIGHTS.get(code.upper())
                    if weight_info is None:
                        logger.warning(f"Unknown code '{code}' – skipping")
                        continue
                    cat, base_val = weight_info
                    # Apply category ceiling: total discount for this category cannot exceed ceiling
                    # We'll enforce the ceiling later during consolidation, but we store the base value now.
                    records[-1]["discounts"].append({
                        "code": code.upper(),
                        "category": current_category,
                        "value": base_val
                    })
                    logger.debug(f"Discount added: {code} ({current_category}) = {base_val}")
                else:
                    logger.debug(f"Line inside category not a code: {stripped}")
            else:
                logger.debug(f"Ignored line (outside category or no current record): {stripped}")

    logger.info(f"Parsed {len(records)} evaluation records from {filepath}")
    return records


# ----------------------------------------------------------------------
# Consolidation
# ----------------------------------------------------------------------
def consolidate(records: list) -> list:
    """
    Groups evaluations by student, calculates average score,
    applies category ceilings per evaluator, and returns consolidated report.
    """
    logger.info("Starting consolidation of all records")

    # Group records by student
    student_records = defaultdict(list)
    for rec in records:
        student_records[rec["student"]].append(rec)

    # Total number of distinct evaluators in the entire exam (for quorum)
    all_evaluators = {rec["evaluator"] for rec in records}
    total_evaluators = len(all_evaluators)
    logger.debug(f"Total distinct evaluators: {total_evaluators}")

    consolidated = []
    for student, evals in student_records.items():
        logger.info(f"Consolidating student: {student} ({len(evals)} evaluators)")

        scores_per_evaluator = []
        discount_details = []  # all discounts after ceiling application per evaluator
        all_disc_codes_flat = []  # for the details we output in JSON

        for rec in evals:
            # Apply category ceilings per evaluator
            cat_totals = defaultdict(float)
            capped_discounts = []
            for disc in rec["discounts"]:
                code = disc["code"]
                category_from_weight = WEIGHTS[code][0]  # e.g., "A"
                base_val = disc["value"]
                # Accumulate in category
                new_total = cat_totals[category_from_weight] + base_val
                if category_from_weight in CATEGORY_CEILINGS:
                    ceiling = CATEGORY_CEILINGS[category_from_weight]
                    if new_total > ceiling:
                        # Cap the value for this discount
                        allowed = ceiling - cat_totals[category_from_weight]
                        if allowed > 0:
                            capped_discounts.append({
                                "code": code,
                                "category": disc["category"],
                                "original_value": base_val,
                                "applied_value": allowed,
                                "capped": True
                            })
                            cat_totals[category_from_weight] = ceiling
                        else:
                            capped_discounts.append({
                                "code": code,
                                "category": disc["category"],
                                "original_value": base_val,
                                "applied_value": 0.0,
                                "capped": True
                            })
                    else:
                        cat_totals[category_from_weight] = new_total
                        capped_discounts.append({
                            "code": code,
                            "category": disc["category"],
                            "original_value": base_val,
                            "applied_value": base_val,
                            "capped": False
                        })
                else:
                    # No ceiling
                    cat_totals[category_from_weight] = new_total
                    capped_discounts.append({
                        "code": code,
                        "category": disc["category"],
                        "original_value": base_val,
                        "applied_value": base_val,
                        "capped": False
                    })

            total_discount = sum(d["applied_value"] for d in capped_discounts)
            score = 100.0 - total_discount  # assume base 100
            scores_per_evaluator.append(score)

            # Prepare discount details for output (list of discounts from this evaluator)
            for d in capped_discounts:
                discount_details.append({
                    "avaliador": rec["evaluator"],
                    "codigo": d["code"],
                    "categoria": d["category"],
                    "valor_aplicado": d["applied_value"]
                })
            all_disc_codes_flat.extend(discount_details)

        # Compute average score
        if scores_per_evaluator:
            avg_score = sum(scores_per_evaluator) / len(scores_per_evaluator)
        else:
            avg_score = 0.0

        # Approval status
        status = "Aprovado" if avg_score >= 70.0 else "Reprovado"

        # Quorum: proportion of evaluators who evaluated this student out of total
        num_evaluators_for_student = len(evals)
        if total_evaluators > 0:
            quorum = f"{num_evaluators_for_student}/{total_evaluators}"
        else:
            quorum = "N/A"

        # Method: UNICO if single evaluator, CONSENSO if multiple
        method = "UNICO" if num_evaluators_for_student == 1 else "CONSENSO"

        consolidated.append({
            "aluno": student,
            "media": round(avg_score, 2),
            "status": status,
            "quorum": quorum,
            "metodo": method,
            "avaliadores": [rec["evaluator"] for rec in evals],
            "descontos": discount_details  # detailed list for JSON output
        })

    logger.info(f"Consolidation finished. {len(consolidated)} students processed.")
    return consolidated


# ----------------------------------------------------------------------
# File Management (Idempotent)
# ----------------------------------------------------------------------
def process_exam_files(input_glob: str = "data/exame-*.txt",
                       output_dir: str = "output",
                       processed_dir: str = "data/processed") -> str:
    """
    Reads exam files matching input_glob, parses, consolidates, writes JSON,
    and moves processed files to processed_dir.
    Returns path to generated JSON report.
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)

    files = sorted(glob.glob(input_glob))
    if not files:
        logger.warning(f"No files matching {input_glob}")
        return ""

    all_records = []
    for fpath in files:
        records = parse_exam_file(fpath)
        all_records.extend(records)

    if not all_records:
        logger.warning("No records found in any file.")
        return ""

    # Consolidate
    consolidated = consolidate(all_records)

    # Write output JSON with details
    output_path = os.path.join(output_dir, "relatorio_consolidado.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(consolidated, f, ensure_ascii=False, indent=2)
    logger.info(f"Output written to {output_path}")

    # Move original files to processed/
    for fpath in files:
        dest = os.path.join(processed_dir, os.path.basename(fpath))
        shutil.move(fpath, dest)
        logger.info(f"Moved {fpath} -> {dest}")

    return output_path


# ----------------------------------------------------------------------
# Main entry point (can be run standalone)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    report_path = process_exam_files()
    if report_path:
        logger.info(f"Consolidated report generated at: {report_path}")
    else:
        logger.error("No report generated – check input files.")