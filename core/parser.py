import re
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from core.config import CATEGORIES

logger = logging.getLogger(__name__)

def _parse_evaluator(line: str) -> Optional[str]:
    """Extrai o nome do Sensei/Avaliador."""
    patterns = [
        r'Avaliador\s+\d+\s+Sensei\s+\[(.+?)\]',
        r'Avaliador\s+\d+\s+Sensei\s+(.+?):',
        r'Avaliador\s+\d+\s+Sensei\s+(.+?)$'
    ]
    for p in patterns:
        m = re.search(p, line.strip())
        if m: return m.group(1).strip()
    return None

def _parse_student(line: str) -> Optional[str]:
    """Extrai o nome do aluno."""
    m = re.search(r'Nome do aluno:\s*\[?(.+?)\]?$', line.strip())
    return m.group(1).strip() if m else None

def _parse_codes(line: str) -> List[int]:
    """Extrai os códigos de erro (ex: cod:1,7,2)."""
    m = re.search(r'cod:\s*([\d,\s]+)', line)
    if m:
        return [int(x.strip()) for x in m.group(1).split(',') if x.strip().isdigit()]
    return []

def parse_file(filepath: Path) -> Dict[str, List[Dict[str, Any]]]:
    """
    Lê o arquivo de exame e retorna um dicionário estruturado.
    Agora inclui suporte ao campo 'Observação:'.
    """
    students = {}
    current_evaluator = None
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            
            # 1. Identifica o Avaliador
            ev = _parse_evaluator(line)
            if ev:
                current_evaluator = ev
                continue
                
            # 2. Identifica o Aluno
            st = _parse_student(line)
            if st and current_evaluator:
                eval_obj = {
                    'evaluator': current_evaluator, 
                    'categories': {cat: [] for cat in CATEGORIES},
                    'observation': "" # Inicializa campo de observação
                }
                students.setdefault(st, []).append(eval_obj)
                continue
            
            # 3. Captura a Observação (Nova Lógica)
            if line.lower().startswith("observação:"):
                obs_text = line.split(":", 1)[1].strip()
                if students:
                    last_st = list(students.keys())[-1]
                    # Vincula a observação à última avaliação do aluno atual
                    students[last_st][-1]['observation'] = obs_text
                continue

            # 4. Captura os Códigos por Categoria
            for cat in CATEGORIES:
                if line.lower().startswith(cat.lower()):
                    codes = _parse_codes(line)
                    if students and codes:
                        last_st = list(students.keys())[-1]
                        students[last_st][-1]['categories'][cat].extend(codes)
    return students