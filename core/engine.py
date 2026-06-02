import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    """Extrai nome do avaliador com tolerância a variações."""
    patterns = [
        r'Avaliador\s+\d+\s+Sensei\s+\[(.+?)\]',  # Com colchetes
        r'Avaliador\s+\d+\s+Sensei\s+(.+?):\s*$',  # Sem colchetes, com dois-pontos
        r'Avaliador\s+\d+\s+Sensei\s+(.+?)$',      # Sem colchetes
    ]
    for pattern in patterns:
        m = re.search(pattern, line.strip())
        if m:
            return m.group(1).strip()
    return None

def _parse_student(line: str) -> Optional[str]:
    """Extrai nome do aluno com tolerância a variações."""
    patterns = [
        r'Nome do aluno:\s*\[(.+?)\]',  # Com colchetes
        r'Nome do aluno:\s*(.+?)$',     # Sem colchetes
    ]
    for pattern in patterns:
        m = re.search(pattern, line.strip())
        if m:
            return m.group(1).strip()
    return None

def _parse_codes(line: str) -> Optional[List[int]]:
    """Extrai códigos de erro."""
    m = re.search(r'cod:\s*([\d,\s]+)', line)
    if m:
        codes_str = m.group(1)
        codes = [int(x.strip()) for x in codes_str.split(',') if x.strip().isdigit()]
        return codes if codes else None
    return None

def _parse_category_code(line: str) -> Optional[str]:
    """Identifica categoria."""
    for cat in CATEGORIES:
        if re.search(rf'\b{cat}\b\s*:', line, re.IGNORECASE):
            return cat
    return None

def parse_file(filepath: Path) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parse robusto que suporta múltiplos avaliadores (1-3).
    
    Retorna:
    {
        'nome_aluno': [
            {'evaluator': 'Paulo', 'categories': {'Kihon': [1,7], ...}},
            {'evaluator': 'Maria', 'categories': {'Kihon': [2,3], ...}},
            ...
        ]
    }
    """
    students: Dict[str, List[Dict[str, Any]]] = {}
    current_evaluator, current_student, current_eval = None, None, None

    logger.info(f"Iniciando parse de {filepath.name}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            stripped = line.strip()
            if not stripped: 
                continue
            
            # Tenta extrair avaliador
            ev = _parse_evaluator(stripped)
            if ev:
                current_evaluator = ev
                current_student = None
                current_eval = None
                logger.info(f"Avaliador detectado: {ev}")
                continue

            # Tenta extrair aluno
            st = _parse_student(stripped)
            if st and current_evaluator:
                current_student = st
                current_eval = {
                    'evaluator': current_evaluator,
                    'categories': {cat: [] for cat in CATEGORIES}
                }
                students.setdefault(current_student, []).append(current_eval)
                logger.info(f"Aluno detectado: {st} (Avaliador: {current_evaluator})")
                continue

            # Tenta extrair categoria e códigos
            cat = _parse_category_code(stripped)
            if cat and current_eval:
                codes = _parse_codes(stripped)
                if codes:
                    current_eval['categories'][cat].extend(codes)
                    logger.debug(f"Códigos em {cat}: {codes}")

    logger.info(f"Parse concluído: {len(students)} alunos encontrados")
    return students

def compute_category_score(codes: List[int]) -> float:
    """
    Calcula a nota de uma categoria.
    
    Lógica:
    - Começa em 25.0
    - Subtrai peso de cada código (A1-A12)
    - Se código 10 presente, teto automático de 10.0
    - Garante mínimo de 0.0
    """
    cat_score = 25.0
    
    for code in codes:
        code_key = f'A{code}'
        weight = WEIGHT_TABLE.get(code_key, 0.0)
        cat_score -= weight
    
    # Regra A10: teto automático
    if 10 in codes:
        cat_score = min(cat_score, 10.0)
    
    return max(0.0, cat_score)

def compute_student_result(student: str, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Consolida resultado de um aluno com múltiplos avaliadores.
    
    Método CONSENSO: média aritmética das notas finais de cada avaliador.
    """
    quorum = len(evaluations)
    logger.info(f"Consolidando {student} com {quorum} avaliador(es)")
    
    # Calcula nota final para cada avaliador
    notas_por_avaliador = []
    all_descontos = []
    
    for ev in evaluations:
        total = 0.0
        for cat in CATEGORIES:
            codes = ev['categories'][cat]
            cat_score = compute_category_score(codes)
            total += cat_score
            
            # Registra descontos para análise
            for code in codes:
                code_key = f'A{code}'
                weight = WEIGHT_TABLE.get(code_key, 0.0)
                all_descontos.append({
                    'codigo': code_key,
                    'categoria': cat,
                    'valor': weight,
                    'avaliador': ev['evaluator']
                })
        
        notas_por_avaliador.append(total)
    
    # Método CONSENSO: média aritmética
    nota_final = sum(notas_por_avaliador) / quorum if quorum > 0 else 0.0
    
    return {
        'nome': student,
        'nota_final': round(nota_final, 2),
        'status': 'Aprovado' if nota_final >= 70 else 'Reprovado',
        'quorum': quorum,
        'metodo': 'consenso_media',
        'notas_por_avaliador': notas_por_avaliador,
        'descontos_detalhados': all_descontos
    }

def gerar_relatorio_master(results: List[Dict[str, Any]], suffix: str):
    """Gera relatório master dinâmico com análise de múltiplos avaliadores."""
    output_file = OUTPUT_DIR / f"relatorio_master_dojo_{suffix}.txt"
    
    if not results:
        logger.warning(f"Sem resultados para gerar relatório master de {suffix}")
        return
    
    media_dojo = sum(r['nota_final'] for r in results) / len(results)
    contador_erros = Counter([d['codigo'] for r in results for d in r['descontos_detalhados']])
    
    # Estatísticas de quorum
    quorums = [r['quorum'] for r in results]
    quorum_mode = max(set(quorums), key=quorums.count) if quorums else 1
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"=== RELATÓRIO MASTER DO DOJO - {suffix.upper()} ===\n")
        f.write(f"Média Geral do Dojo: {media_dojo:.2f}\n")
        f.write(f"Quorum Predominante: {quorum_mode} avaliador(es)\n\n")
        
        f.write("--- Desempenho por Aluno ---\n")
        for r in sorted(results, key=lambda x: x['nome']):
            f.write(f"{r['nome']}: {r['nota_final']} (Quorum: {r['quorum']}) - {r['status']}\n")
        
        f.write("\n--- Destaques Técnicos (Erros Frequentes) ---\n")
        if contador_erros:
            for cod, qtd in contador_erros.most_common(5):
                f.write(f"{cod}: {qtd} ocorrências\n")
        else:
            f.write("Nenhum erro registrado.\n")
    
    logger.info(f"Relatório Master salvo em {output_file}")

def run():
    """Pipeline principal."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    exame_files = sorted(DATA_DIR.glob('exame-*.txt'))
    if not exame_files:
        logger.warning("Nenhum arquivo de exame encontrado em data/")
        return

    for filepath in exame_files:
        suffix = filepath.stem.replace('exame-', '')
        logger.info(f"=== Processando {filepath.name} ===")
        
        try:
            students = parse_file(filepath)
            
            if not students:
                logger.warning(f"Nenhum aluno extraído de {filepath.name}")
                continue
            
            results = [compute_student_result(st, ev) for st, ev in students.items()]

            if results:
                # Salva JSON dinâmico
                json_file = OUTPUT_DIR / f"relatorio_consolidado_{suffix}.json"
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                logger.info(f"JSON salvo: {json_file}")
                
                # Salva TXT dinâmico
                gerar_relatorio_master(results, suffix)
            
            # Move para processados
            dest = PROCESSED_DIR / filepath.name
            filepath.rename(dest)
            logger.info(f"Arquivo movido para {dest}")
            
        except Exception as e:
            logger.error(f"Erro ao processar {filepath.name}: {e}", exc_info=True)

if __name__ == '__main__':
    run()