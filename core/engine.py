import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

DATA_DIR = Path('data')
PROCESSED_DIR = DATA_DIR / 'processed'
OUTPUT_DIR = Path('output')
OUTPUT_FILE = OUTPUT_DIR / 'relatorio_consolidado.json'

# Official weight table v1.1
WEIGHT_TABLE: Dict[str, float] = {
    'A1': 1.0,
    'A2': 2.0,
    'A3': 1.5,
    'A4': 2.5,
    'A5': 3.0,
    'A6': 1.0,
    'A7': 4.0,
    'A8': 2.0,
    'A9': 3.5,
    'A10': 12.0,
    'A11': 1.0,
    'A12': 5.0,
}

CATEGORIES = ['Kihon', 'Kata', 'Bunkai', 'Kumite']

# ----------------------------------------------------------------------
# Parsing helpers
# ----------------------------------------------------------------------
def _parse_evaluator(line: str) -> Optional[str]:
    """Extract evaluator name from line like 'Avaliador X Sensei [Nome]:'"""
    m = re.match(r'Avaliador\s+\d+\s+Sensei\s+\[(.+?)\]:\s*$', line.strip())
    if m:
        return m.group(1).strip()
    return None

def _parse_student(line: str) -> Optional[str]:
    """Extract student name from line like 'Nome do aluno: [Nome]'"""
    m = re.match(r'Nome do aluno:\s*\[(.+?)\]\s*$', line.strip())
    if m:
        return m.group(1).strip()
    return None

def _parse_codes(line: str) -> Optional[List[int]]:
    """Extract list of integer codes from line like 'Kihon: cod:1,7'"""
    m = re.search(r'cod:\s*([\d,\s]+)', line)
    if m:
        codes_str = m.group(1)
        codes = [int(x.strip()) for x in codes_str.split(',') if x.strip().isdigit()]
        return codes if codes else None
    return None

def _parse_category_code(line: str) -> Optional[str]:
    """Return the category name if the line contains a known category followed by ': cod:'"""
    for cat in CATEGORIES:
        if re.match(rf'{cat}\s*:', line, re.IGNORECASE):
            return cat
    return None

def parse_file(filepath: Path) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parse a single exame file and return a dict mapping student name to a list of evaluator evaluations.
    Each evaluation dict: {'evaluator': str, 'categories': {cat: [codes]}}
    """
    students: Dict[str, List[Dict[str, Any]]] = {}
    current_evaluator: Optional[str] = None
    current_student: Optional[str] = None
    current_eval: Optional[Dict[str, Any]] = None

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue

            # Detect evaluator header
            ev = _parse_evaluator(stripped)
            if ev:
                current_evaluator = ev
                current_student = None
                current_eval = None
                continue

            # Detect student name
            st = _parse_student(stripped)
            if st:
                if current_evaluator is None:
                    logger.warning("Student name without evaluator context: %s", st)
                    continue
                current_student = st
                # Initialize a new evaluation for this student and evaluator
                current_eval = {
                    'evaluator': current_evaluator,
                    'categories': {cat: [] for cat in CATEGORIES}
                }
                students.setdefault(current_student, []).append(current_eval)
                continue

            # Detect category line with codes
            cat = _parse_category_code(stripped)
            if cat and current_eval is not None:
                codes = _parse_codes(stripped)
                if codes:
                    current_eval['categories'][cat].extend(codes)
                continue

    return students

# ----------------------------------------------------------------------
# Consolidation logic
# ----------------------------------------------------------------------
def compute_student_result(student: str, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute final consolidated score for a single student.
    Returns dict with nome, nota_final, status, quorum, metodo, descontos_detalhados.
    """
    # For each evaluator, compute total score
    totals = []
    all_descontos = []

    for ev in evaluations:
        total = 0.0
        for cat in CATEGORIES:
            codes = ev['categories'][cat]
            # Start at 25.0
            cat_score = 25.0
            # Subtract weights for each code (skip if code not in weight table)
            for code in codes:
                code_key = f'A{code}'
                weight = WEIGHT_TABLE.get(code_key, 0.0)
                cat_score -= weight
                # Record deduction
                all_descontos.append({
                    'codigo': code_key,
                    'categoria': cat,
                    'valor': weight
                })
            # Apply A10 cap: if code 10 present, cap at 10.0
            if 10 in codes:
                cat_score = min(cat_score, 10.0)
            # Ensure non-negative
            cat_score = max(0.0, cat_score)
            total += cat_score
        totals.append(total)

    # Average across evaluators
    if totals:
        nota_final = sum(totals) / len(totals)
    else:
        nota_final = 0.0

    quorum = len(evaluations)
    status = 'Aprovado' if nota_final >= 70 else 'Reprovado'

    return {
        'nome': student,
        'nota_final': round(nota_final, 2),
        'status': status,
        'quorum': quorum,
        'metodo': 'consolidacao_media',
        'descontos_detalhados': all_descontos
    }

# ----------------------------------------------------------------------
# File management
# ----------------------------------------------------------------------
def ensure_dirs():
    """Create required directories if they don't exist."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def get_exame_files() -> List[Path]:
    """Return sorted list of exame files in data/ directory."""
    pattern = 'exame-*.txt'
    files = sorted(DATA_DIR.glob(pattern))
    if not files:
        logger.warning("No exame files found matching %s", pattern)
    return files

def move_to_processed(filepath: Path):
    """Move file to processed directory."""
    dest = PROCESSED_DIR / filepath.name
    # Avoid overwrite: if dest exists, add a timestamp
    if dest.exists():
        timestamp = int(filepath.stat().st_mtime)
        dest = PROCESSED_DIR / f"{filepath.stem}_{timestamp}{filepath.suffix}"
    filepath.rename(dest)
    logger.info("Moved %s to %s", filepath.name, dest.name)

# ----------------------------------------------------------------------
# Main pipeline
# ----------------------------------------------------------------------
def run():
    """Main execution pipeline."""
    ensure_dirs()
    exame_files = get_exame_files()
    if not exame_files:
        logger.info("Nothing to process.")
        return

    # Aggregate all student evaluations across files
    all_students: Dict[str, List[Dict[str, Any]]] = {}

    for filepath in exame_files:
        logger.info("Processing file: %s", filepath.name)
        try:
            students = parse_file(filepath)
            for student, evals in students.items():
                all_students.setdefault(student, []).extend(evals)
            move_to_processed(filepath)
        except Exception as e:
            logger.error("Error processing %s: %s", filepath.name, e, exc_info=True)
            # Continue to next file

    # Consolidate and produce output
    results = []
    for student, evaluations in all_students.items():
        logger.info("Consolidando %s com %d avaliadores", student, len(evaluations))
        result = compute_student_result(student, evaluations)
        results.append(result)

    # Write output JSON
    if results:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info("Relatório consolidado salvo em %s", OUTPUT_FILE)
    else:
        logger.warning("Nenhum resultado para exportar.")

if __name__ == '__main__':
    run()