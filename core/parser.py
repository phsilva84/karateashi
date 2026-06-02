import re
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from core.config import CATEGORIES

logger = logging.getLogger(__name__)

def _parse_evaluator(line: str) -> Optional[str]:
    patterns = [r'Avaliador\s+\d+\s+Sensei\s+\[(.+?)\]', r'Avaliador\s+\d+\s+Sensei\s+(.+?):', r'Avaliador\s+\d+\s+Sensei\s+(.+?)$']
    for p in patterns:
        m = re.search(p, line.strip())
        if m: return m.group(1).strip()
    return None

def _parse_student(line: str) -> Optional[str]:
    m = re.search(r'Nome do aluno:\s*\[?(.+?)\]?$', line.strip())
    return m.group(1).strip() if m else None

def _parse_codes(line: str) -> List[int]:
    m = re.search(r'cod:\s*([\d,\s]+)', line)
    if m:
        return [int(x.strip()) for x in m.group(1).split(',') if x.strip().isdigit()]
    return []

def parse_file(filepath: Path) -> Dict[str, List[Dict[str, Any]]]:
    students = {}
    current_evaluator = None
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            ev = _parse_evaluator(line)
            if ev:
                current_evaluator = ev
                continue
            st = _parse_student(line)
            if st and current_evaluator:
                eval_obj = {'evaluator': current_evaluator, 'categories': {cat: [] for cat in CATEGORIES}}
                students.setdefault(st, []).append(eval_obj)
                continue
            for cat in CATEGORIES:
                if line.lower().startswith(cat.lower()):
                    codes = _parse_codes(line)
                    if students and codes:
                        last_st = list(students.keys())[-1]
                        students[last_st][-1]['categories'][cat].extend(codes)
    return students