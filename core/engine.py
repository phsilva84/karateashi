import re
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configure logging (SRE style)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# PESOS OFICIAIS – Tabela v1.1 (valores exemplificativos)
# Cada categoria (Kihon, Kata, Bunkai, Kumite) possui um dicionário
# mapeando o código de erro (string) para o peso (float) a subtrair.
# ----------------------------------------------------------------------
WEIGHTS = {
    'Kihon': {
        '1': 1.0, '2': 1.5, '3': 2.0, '4': 0.5, '5': 3.0,
        '6': 2.5, '7': 1.0, '8': 4.0, '9': 0.5, '10': 0.0,  # código 10 não subtrai mas aplica teto
    },
    'Kata': {
        '1': 1.0, '2': 2.0, '3': 1.5, '4': 3.0, '5': 0.5,
        '6': 2.5, '7': 4.0, '8': 0.5, '9': 1.0, '10': 0.0,
    },
    'Bunkai': {
        '1': 0.5, '2': 1.0, '3': 2.0, '4': 2.5, '5': 3.0,
        '6': 1.5, '7': 4.0, '8': 0.5, '9': 1.0, '10': 0.0,
    },
    'Kumite': {
        '1': 1.0, '2': 1.5, '3': 2.0, '4': 0.5, '5': 3.0,
        '6': 2.5, '7': 4.0, '8': 0.5, '9': 1.0, '10': 0.0,
    },
}

CATEGORIES = list(WEIGHTS.keys())  # ['Kihon', 'Kata', 'Bunkai', 'Kumite']
INITIAL_SCORE = 25.0  # nota inicial por categoria
TETO_CODE = '10'
TETO_VALUE = 10.0
APPROVAL_THRESHOLD = 70.0  # nota final mínima para aprovação

# ----------------------------------------------------------------------
# Parsing – Máquina de Estados para arquivos exame-*.txt
# ----------------------------------------------------------------------
class State:
    WAITING_EVALUATOR = 0
    INSIDE_EVALUATOR = 1
    INSIDE_STUDENT = 2

def parse_exam_file(filepath: str) -> List[dict]:
    """
    Lê um arquivo de exame e retorna uma lista de dicionários no formato:
    {
        'avaliador': str,
        'aluno': str,
        'categorias': {
            'Kihon': [códigos...],
            'Kata': [códigos...],
            'Bunkai': [códigos...],
            'Kumite': [códigos...]
        }
    }
    """
    logger.info(f"Parsing file: {filepath}")
    records = []
    state = State.WAITING_EVALUATOR
    current_evaluator = None
    current_student = None
    current_categories: Dict[str, List[str]] = {cat: [] for cat in CATEGORIES}

    # Padrões regex
    evaluator_pattern = re.compile(r'^Avaliador\s+\d+\s+Sensei\s+(.+?):\s*$', re.IGNORECASE)
    student_pattern = re.compile(r'^Nome\s+do\s+aluno:\s+(.+?)\s*$', re.IGNORECASE)
    category_pattern = re.compile(r'^(Kihon|Kata|Bunkai|Kumite):\s+(.+?)\s*$', re.IGNORECASE)

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Tentar detectar avaliador
            m_eval = evaluator_pattern.match(line)
            if m_eval:
                # Se havia um aluno em andamento, finaliza o registro anterior
                if current_student and current_evaluator:
                    records.append({
                        'avaliador': current_evaluator,
                        'aluno': current_student,
                        'categorias': {k: list(v) for k, v in current_categories.items()}
                    })
                current_evaluator = m_eval.group(1).strip()
                current_student = None
                current_categories = {cat: [] for cat in CATEGORIES}
                state = State.INSIDE_EVALUATOR
                logger.debug(f"Found evaluator: {current_evaluator}")
                continue

            # Tentar detectar aluno (pode ocorrer dentro de avaliador)
            m_stu = student_pattern.match(line)
            if m_stu:
                if current_student and current_evaluator:
                    # Fecha registro do aluno anterior (mesmo avaliador)
                    records.append({
                        'avaliador': current_evaluator,
                        'aluno': current_student,
                        'categorias': {k: list(v) for k, v in current_categories.items()}
                    })
                current_student = m_stu.group(1).strip()
                current_categories = {cat: [] for cat in CATEGORIES}
                state = State.INSIDE_STUDENT
                logger.debug(f"Found student: {current_student}")
                continue

            # Tentar detectar linha de categoria (apenas dentro de student)
            if state == State.INSIDE_STUDENT:
                m_cat = category_pattern.match(line)
                if m_cat:
                    cat_name = m_cat.group(1)
                    codes_str = m_cat.group(2)
                    # Extrair códigos (números separados por vírgula, espaço, etc.)
                    codes = re.findall(r'\d+', codes_str)
                    if codes:
                        current_categories[cat_name].extend(codes)
                        logger.debug(f"Category {cat_name} codes: {codes}")
                    continue
                else:
                    # Linha não reconhecida dentro do aluno: ignorar (pode ser comentário)
                    logger.debug(f"Ignored line inside student: {line}")
            else:
                logger.debug(f"Ignored line (state={state}): {line}")

    # Finaliza último registro se existir
    if current_evaluator and current_student:
        records.append({
            'avaliador': current_evaluator,
            'aluno': current_student,
            'categorias': {k: list(v) for k, v in current_categories.items()}
        })

    logger.info(f"Parsed {len(records)} records from {filepath}")
    return records

# ----------------------------------------------------------------------
# Cálculo de nota por avaliador para um aluno
# ----------------------------------------------------------------------
def calculate_evaluator_score(categorias: Dict[str, List[str]]) -> Tuple[float, Dict[str, List[dict]]]:
    """
    Recebe categorias de um avaliador para um aluno.
    Retorna (total_score, descontos_detalhados_avaliador).
    descontos_detalhados: lista de dicionários com 'codigo', 'categoria', 'peso' e 'subtraido'.
    """
    total = 0.0
    detalhes = []
    for cat_name in CATEGORIES:
        codes = categorias.get(cat_name, [])
        score = INITIAL_SCORE
        for code in codes:
            peso = WEIGHTS[cat_name].get(code, 0.0)
            if peso > 0:
                subtracao = peso
                score -= subtracao
                detalhes.append({
                    'codigo': code,
                    'categoria': cat_name,
                    'peso': peso,
                    'subtraido': subtracao
                })
                logger.debug(f"Subtracted {subtracao} for code {code} in {cat_name}")
            else:
                # código zero ou não encontrado – só registra se for código 10 (teto)
                if code == TETO_CODE:
                    # Nota não subtraída, mas teto será aplicado depois
                    detalhes.append({
                        'codigo': code,
                        'categoria': cat_name,
                        'peso': 0.0,
                        'subtraido': 0.0,
                        'efeito': 'teto_10'
                    })
        # Aplica teto se código 10 presente
        if TETO_CODE in codes:
            score = min(score, TETO_VALUE)
            logger.debug(f"Teto 10 aplicado em {cat_name}: score capped to {score}")
        total += score
    return total, detalhes

# ----------------------------------------------------------------------
# Consolidação de alunos entre avaliadores
# ----------------------------------------------------------------------
def consolidate_students(all_records: List[dict]) -> List[dict]:
    """
    Agrupa registros por aluno, calcula nota final e aplica lógica de quorum.
    Retorna lista de resultados (um dict por aluno).
    """
    # Agrupar por aluno
    students: Dict[str, List[dict]] = {}
    for rec in all_records:
        name = rec['aluno']
        students.setdefault(name, []).append(rec)

    results = []
    for aluno_name, records_aluno in students.items():
        # Número de avaliadores únicos
        avaliadores = set(r['avaliador'] for r in records_aluno)
        qtd_avaliadores = len(avaliadores)

        # Determinar método
        if qtd_avaliadores == 1:
            metodo = 'UNICO'
        else:
            metodo = 'CONSENSO'

        # Calcular nota de cada avaliador e somar
        total_avaliadores = 0.0
        all_descontos = []
        for rec in records_aluno:
            score_avaliador, descontos_avaliador = calculate_evaluator_score(rec['categorias'])
            total_avaliadores += score_avaliador
            all_descontos.extend(descontos_avaliador)

        # Nota final = média dos totais de cada avaliador
        nota_final = total_avaliadores / qtd_avaliadores if qtd_avaliadores > 0 else 0.0

        # Status
        status = 'Aprovado' if nota_final >= APPROVAL_THRESHOLD else 'Reprovado'

        # Quorum string
        quorum = f"{qtd_avaliadores}/3"

        # Descontos detalhados (agregados)
        # Remover duplicatas? Pode manter todos por avaliador conforme requisito.
        # Vamos agrupar por codigo e categoria? O requisito diz "quais códigos e quanto foi subtraído"
        # Vamos manter a lista completa (sem agregar) para transparência.
        # Opcional: agregar somas para facilitar leitura. Vamos agregar por (codigo, categoria).
        aggregated_descontos = {}
        for d in all_descontos:
            key = (d['codigo'], d['categoria'])
            if key not in aggregated_descontos:
                aggregated_descontos[key] = {
                    'codigo': d['codigo'],
                    'categoria': d['categoria'],
                    'total_subtraido': 0.0
                }
            aggregated_descontos[key]['total_subtraido'] += d['subtraido']

        descontos_detalhados = list(aggregated_descontos.values())

        results.append({
            'nome': aluno_name,
            'nota_final': round(nota_final, 2),
            'status': status,
            'quorum': quorum,
            'metodo': metodo,
            'descontos_detalhados': descontos_detalhados
        })
        logger.info(f"Aluno: {aluno_name}, nota_final={nota_final:.2f}, status={status}, quorum={quorum}, metodo={metodo}")

    return results

# ----------------------------------------------------------------------
# Gestão de arquivos (padrão SRE: ler, mover, evitar reprocessamento)
# ----------------------------------------------------------------------
def process_files(data_dir: str = 'data', processed_dir: str = 'data/processed', output_dir: str = 'output'):
    """
    Lê todos os arquivos 'data/exame-*.txt', processa, move para processed/ e gera relatório consolidado.
    """
    # Garantir diretórios
    Path(processed_dir).mkdir(parents=True, exist_ok=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Encontrar arquivos a processar
    pattern = os.path.join(data_dir, 'exame-*.txt')
    files = sorted(Path(data_dir).glob('exame-*.txt'))
    if not files:
        logger.warning(f"Nenhum arquivo encontrado com padrão {pattern}")
        return

    all_records = []
    for filepath in files:
        try:
            records = parse_exam_file(str(filepath))
            all_records.extend(records)
            # Mover para processed
            dest = Path(processed_dir) / filepath.name
            shutil.move(str(filepath), str(dest))
            logger.info(f"Arquivo movido para {dest}")
        except Exception as e:
            logger.error(f"Erro ao processar {filepath}: {e}")

    if not all_records:
        logger.warning("Nenhum registro extraído dos arquivos.")
        return

    # Consolidar
    alunos = consolidate_students(all_records)

    # Gerar relatório
    relatorio = {'alunos': alunos}
    output_path = os.path.join(output_dir, 'relatorio_consolidado.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(relatorio, f, indent=2, ensure_ascii=False)
    logger.info(f"Relatório consolidado gerado em {output_path}")

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
if __name__ == '__main__':
    process_files()