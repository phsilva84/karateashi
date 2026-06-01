import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

DATA_DIR = Path('data')
PROCESSED_DIR = DATA_DIR / 'processed'
OUTPUT_DIR = Path('output')

WEIGHT_TABLE: Dict[str, float] = {
    'A1': 1.0, 'A2': 2.0, 'A3': 1.5, 'A4': 2.5, 'A5': 3.0,
    'A6': 1.0, 'A7': 4.0, 'A8': 2.0, 'A9': 3.5, 'A10': 12.0,
    'A11': 1.0, 'A12': 5.0,
}

CATEGORIES = ['Kihon', 'Kata', 'Bunkai', 'Kumite']

def _parse_evaluator(line: str) -> Optional[str]:
    m = re.match(r'Avaliador\s+\d+\s+Sensei\s+\[(.+?)\]:\s*$', line.strip())
    return m.group(1).strip() if m else None

def _parse_student(line: str) -> Optional[str]:
    m = re.match(r'Nome do aluno:\s*\[(.+?)\]\s*$', line.strip())
    return m.group(1).strip() if m else None

def _parse_codes(line: str) -> Optional[List[int]]:
    m = re.search(r'cod:\s*([\d,\s]+)', line)
    if m:
        codes_str = m.group(1)
        return [int(x.strip()) for x in codes_str.split(',') if x.strip().isdigit()]
    return None

def _parse_category_code(line: str) -> Optional[str]:
    for cat in CATEGORIES:
        if re.match(rf'{cat}\s*:', line, re.IGNORECASE):
            return cat
    return None

def parse_file(filepath: Path) -> Dict[str, List[Dict[str, Any]]]:
    students: Dict[str, List[Dict[str, Any]]] = {}
    current_evaluator, current_student, current_eval = None, None, None

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            if not stripped: continue
            
            ev = _parse_evaluator(stripped)
            if ev:
                current_evaluator, current_student, current_eval = ev, None, None
                continue

            st = _parse_student(stripped)
            if st and current_evaluator:
                current_student = st
                current_eval = {'evaluator': current_evaluator, 'categories': {cat: [] for cat in CATEGORIES}}
                students.setdefault(current_student, []).append(current_eval)
                continue

            cat = _parse_category_code(stripped)
            if cat and current_eval:
                codes = _parse_codes(stripped)
                if codes: current_eval['categories'][cat].extend(codes)
    return students

def compute_student_result(student: str, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
    totals, all_descontos = [], []
    for ev in evaluations:
        total = 0.0
        for cat in CATEGORIES:
            codes = ev['categories'][cat]
            cat_score = 25.0
            for code in codes:
                code_key = f'A{code}'
                weight = WEIGHT_TABLE.get(code_key, 0.0)
                cat_score -= weight
                all_descontos.append({'codigo': code_key, 'categoria': cat, 'valor': weight})
            if 10 in codes: cat_score = min(cat_score, 10.0)
            total += max(0.0, cat_score)
        totals.append(total)

    nota_final = sum(totals) / len(totals) if totals else 0.0
    return {
        'nome': student,
        'nota_final': round(nota_final, 2),
        'status': 'Aprovado' if nota_final >= 70 else 'Reprovado',
        'quorum': len(evaluations),
        'descontos_detalhados': all_descontos
    }

def gerar_relatorio_master(results: List[Dict[str, Any]], suffix: str):
    """Gera o resumo executivo dinâmico em TXT."""
    output_file = OUTPUT_DIR / f"relatorio_master_dojo_{suffix}.txt"
    
    media_dojo = sum(r['nota_final'] for r in results) / len(results)
    contador_erros = Counter([d['codigo'] for r in results for d in r['descontos_detalhados']])
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"=== RELATÓRIO MASTER DO DOJO - {suffix.upper()} ===\n")
        f.write(f"Média Geral do Dojo: {media_dojo:.2f}\n\n")
        f.write("--- Desempenho por Aluno ---\n")
        for r in sorted(results, key=lambda x: x['nome']):
            f.write(f"{r['nome']}: {r['nota_final']} - {r['status']}\n")
        
        f.write("\n--- Destaques Técnicos (Erros Frequentes) ---\n")
        for cod, qtd in contador_erros.most_common(5):
            f.write(f"{cod}: {qtd} ocorrências\n")
    logger.info("Relatório Master salvo em %s", output_file)

def run():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    exame_files = sorted(DATA_DIR.glob('exame-*.txt'))
    if not exame_files:
        logger.info("Nenhum arquivo de exame para processar.")
        return

    for filepath in exame_files:
        # Extrai o sufixo (ex: matriz-30-05-26)
        suffix = filepath.stem.replace('exame-', '')
        logger.info(f"Processando exame do dojo: {suffix}")
        
        students = parse_file(filepath)
        all_students = {}
        for student, evals in students.items():
            all_students.setdefault(student, []).extend(evals)
        
        results = [compute_student_result(st, ev) for st, ev in all_students.items()]

        if results:
            # Salva JSON dinâmico
            json_file = OUTPUT_DIR / f"relatorio_consolidado_{suffix}.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            
            # Salva TXT dinâmico
            gerar_relatorio_master(results, suffix)
            
            # Move para processados
            dest = PROCESSED_DIR / filepath.name
            filepath.rename(dest)
        else:
            logger.warning(f"Nenhum resultado processado para {filepath.name}")

if __name__ == '__main__':
    run()