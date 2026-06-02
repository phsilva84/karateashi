import json
import logging
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Configuração de Logs para Observabilidade SRE
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

DATA_DIR = Path('data')
PROCESSED_DIR = DATA_DIR / 'processed'
OUTPUT_DIR = Path('output')

# ============================================================================
# TABELA v1.1 CORRIGIDA (A10 = 2.5)
# ============================================================================
WEIGHT_TABLE_V1_1 = {
    'A1': 1.0,    # Base incorreta
    'A2': 1.0,    # Execução técnica incorreta
    'A3': 1.0,    # Movimento sem carga/peso
    'A4': 0.5,    # Ausência de kiai
    'A5': 2.0,    # Embusen incorreto
    'A6': 1.0,    # Falta de foco / olhar incorreto
    'A7': 1.0,    # Perda de equilíbrio
    'A8': 0.5,    # Falta de ritmo
    'A9': 1.0,    # Defesa incompleta
    'A10': 2.5,   # Falta de controle no ataque (CORRIGIDO de 12.0)
    'A11': 1.0,   # Distância inadequada
    'A12': 0.5,   # Tensão / respiração inadequada
}

CATEGORIES = ['Kihon', 'Kata', 'Bunkai', 'Kumite']

# ============================================================================
# MAPEAMENTO SEMÂNTICO DE CÓDIGOS (Tabela v1.1)
# ============================================================================
CODE_MEANINGS_V1_1 = {
    'A1': {
        'descricao': 'Base incorreta',
        'recomendacao_tecnica': 'Trabalhar posicionamento de pés e distribuição de peso',
        'severidade': 'alta'
    },
    'A2': {
        'descricao': 'Execução técnica incorreta',
        'recomendacao_tecnica': 'Revisar forma correta com instrutor',
        'severidade': 'alta'
    },
    'A3': {
        'descricao': 'Movimento sem carga/peso',
        'recomendacao_tecnica': 'Aumentar transferência de peso',
        'severidade': 'alta'
    },
    'A4': {
        'descricao': 'Ausência de kiai',
        'recomendacao_tecnica': 'Trabalhar respiração sincronizada',
        'severidade': 'baixa'
    },
    'A5': {
        'descricao': 'Embusen incorreto',
        'recomendacao_tecnica': 'Memorizar padrão correto de deslocamento',
        'severidade': 'media'
    },
    'A6': {
        'descricao': 'Falta de foco / olhar incorreto',
        'recomendacao_tecnica': 'Treinar concentração visual',
        'severidade': 'media'
    },
    'A7': {
        'descricao': 'Perda de equilíbrio',
        'recomendacao_tecnica': 'Fortalecer estabilidade e core',
        'severidade': 'alta'
    },
    'A8': {
        'descricao': 'Falta de ritmo',
        'recomendacao_tecnica': 'Sincronizar movimentos com ritmo',
        'severidade': 'baixa'
    },
    'A9': {
        'descricao': 'Defesa incompleta',
        'recomendacao_tecnica': 'Treinar defesa ativa e contra-ataques',
        'severidade': 'alta'
    },
    'A10': {
        'descricao': 'Falta de controle no ataque / excesso de força / risco ao parceiro',
        'recomendacao_tecnica': 'Trabalhar controle e segurança no kumite',
        'severidade': 'critica'
    },
    'A11': {
        'descricao': 'Distância inadequada',
        'recomendacao_tecnica': 'Treinar distância correta (ma-ai)',
        'severidade': 'media'
    },
    'A12': {
        'descricao': 'Tensão / respiração inadequada',
        'recomendacao_tecnica': 'Trabalhar relaxamento e respiração',
        'severidade': 'baixa'
    }
}

# ============================================================================
# MAPEAMENTO DE PONTOS POSITIVOS (Inverso dos códigos)
# ============================================================================
PONTOS_POSITIVOS_V1_1 = {
    'A1': {'descricao': 'Base incorreta', 'inverso': 'Bases corretas', 'elogio': 'Alunos com bom trabalho de bases e posicionamento de pés'},
    'A2': {'descricao': 'Execução técnica incorreta', 'inverso': 'Execução técnica correta', 'elogio': 'Alunos com boa execução técnica e forma correta'},
    'A3': {'descricao': 'Movimento sem carga/peso', 'inverso': 'Movimento com carga/peso', 'elogio': 'Alunos com boa transferência de peso e potência'},
    'A4': {'descricao': 'Ausência de kiai', 'inverso': 'Kiai presente', 'elogio': 'Alunos com boa respiração sincronizada e vocalização'},
    'A5': {'descricao': 'Embusen incorreto', 'inverso': 'Embusen correto', 'elogio': 'Alunos com excelente memorização e execução de kata'},
    'A6': {'descricao': 'Falta de foco / olhar incorreto', 'inverso': 'Foco e olhar correto', 'elogio': 'Alunos com excelente concentração e foco visual'},
    'A7': {'descricao': 'Perda de equilíbrio', 'inverso': 'Equilíbrio mantido', 'elogio': 'Alunos com excelente estabilidade e equilíbrio'},
    'A8': {'descricao': 'Falta de ritmo', 'inverso': 'Ritmo correto', 'elogio': 'Alunos com excelente sincronização e ritmo'},
    'A9': {'descricao': 'Defesa incompleta', 'inverso': 'Defesa completa', 'elogio': 'Alunos com excelente defesa e contra-ataques'},
    'A10': {'descricao': 'Falta de controle no ataque', 'inverso': 'Controle no ataque', 'elogio': 'Alunos com excelente controle e segurança no kumite'},
    'A11': {'descricao': 'Distância inadequada', 'inverso': 'Distância adequada', 'elogio': 'Alunos com excelente ma-ai (distância correta)'},
    'A12': {'descricao': 'Tensão / respiração inadequada', 'inverso': 'Tensão / respiração adequada', 'elogio': 'Alunos com excelente relaxamento e respiração'}
}

# ============================================================================
# PARSING FUNCTIONS
# ============================================================================
def _parse_evaluator(line: str) -> Optional[str]:
    patterns = [r'Avaliador\s+\d+\s+Sensei\s+\[(.+?)\]', r'Avaliador\s+\d+\s+Sensei\s+(.+?):\s*$', r'Avaliador\s+\d+\s+Sensei\s+(.+?)$']
    for pattern in patterns:
        m = re.search(pattern, line.strip())
        if m: return m.group(1).strip()
    return None

def _parse_student(line: str) -> Optional[str]:
    patterns = [r'Nome do aluno:\s*\[(.+?)\]', r'Nome do aluno:\s*(.+?)$']
    for pattern in patterns:
        m = re.search(pattern, line.strip())
        if m: return m.group(1).strip()
    return None

def _parse_codes(line: str) -> Optional[List[int]]:
    m = re.search(r'cod:\s*([\d,\s]+)', line)
    if m:
        codes_str = m.group(1)
        return [int(x.strip()) for x in codes_str.split(',') if x.strip().isdigit()]
    return None

def _parse_category_code(line: str) -> Optional[str]:
    for cat in CATEGORIES:
        if re.search(rf'\b{cat}\b\s*:', line, re.IGNORECASE): return cat
    return None

def parse_file(filepath: Path) -> Dict[str, List[Dict[str, Any]]]:
    students: Dict[str, List[Dict[str, Any]]] = {}
    current_evaluator, current_student, current_eval = None, None, None
    logger.info(f"Iniciando parse de {filepath.name}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            if not stripped: continue
            
            ev = _parse_evaluator(stripped)
            if ev:
                current_evaluator = ev
                current_student = None
                current_eval = None
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

# ============================================================================
# CÁLCULO DE RESULTADO
# ============================================================================
def compute_category_score(codes: List[int]) -> float:
    """Calcula nota de uma categoria aplicando a Regra de Teto A10."""
    cat_score = 25.0
    for code in codes:
        weight = WEIGHT_TABLE_V1_1.get(f'A{code}', 0.0)
        cat_score -= weight
    
    # REGRA CRÍTICA: Se houver A10, a nota da categoria não pode exceder 10.0
    if 10 in codes:
        cat_score = min(cat_score, 10.0)
    
    return max(0.0, cat_score)

def compute_student_result(student: str, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
    quorum = len(evaluations)
    notas_por_avaliador = []
    all_descontos = []
    
    for ev in evaluations:
        total = 0.0
        for cat in CATEGORIES:
            codes = ev['categories'][cat]
            cat_score = compute_category_score(codes)
            total += cat_score
            for code in codes:
                code_key = f'A{code}'
                all_descontos.append({
                    'codigo': code_key, 'categoria': cat, 
                    'valor': WEIGHT_TABLE_V1_1.get(code_key, 0.0), 'avaliador': ev['evaluator']
                })
        notas_por_avaliador.append(total)
    
    nota_final = sum(notas_por_avaliador) / quorum if quorum > 0 else 0.0
    return {
        'nome': student, 'nota_final': round(nota_final, 2),
        'status': 'Aprovado' if nota_final >= 70 else 'Reprovado',
        'quorum': quorum, 'metodo': 'consenso_media',
        'notas_por_avaliador': notas_por_avaliador, 'descontos_detalhados': all_descontos
    }

# ============================================================================
# GERAÇÃO DE RECOMENDAÇÕES (OPÇÃO C)
# ============================================================================
def gerar_recomendacoes_opcao_c(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_alunos = len(results)
    codigo_avaliador_stats = {}
    for result in results:
        for desconto in result['descontos_detalhados']:
            codigo = desconto['codigo']
            avaliador = desconto['avaliador']
            aluno = result['nome']
            if codigo not in codigo_avaliador_stats: codigo_avaliador_stats[codigo] = {}
            if avaliador not in codigo_avaliador_stats[codigo]: codigo_avaliador_stats[codigo][avaliador] = set()
            codigo_avaliador_stats[codigo][avaliador].add(aluno)
    
    recomendacoes = {}
    for codigo in sorted(codigo_avaliador_stats.keys(), key=lambda x: sum(len(alunos) for alunos in codigo_avaliador_stats[x].values()), reverse=True):
        avaliadores_dict = codigo_avaliador_stats[codigo]
        por_avaliador = {av: {'frequencia': len(als), 'percentual': round((len(als)/total_alunos)*100, 1), 'alunos': sorted(list(als))} for av, als in avaliadores_dict.items()}
        alunos_consenso = set.intersection(*[set(alunos) for alunos in avaliadores_dict.values()])
        
        significado = CODE_MEANINGS_V1_1.get(codigo, {})
        pct_consenso = (len(alunos_consenso) / total_alunos) * 100
        intensidade = "🔴 CRÍTICO" if pct_consenso >= 70 else "🟠 IMPORTANTE" if pct_consenso >= 50 else "🟡 ATENÇÃO"
        
        recomendacoes[codigo] = {
            'descricao': significado.get('descricao', 'erro'),
            'acao_sensei': f"{intensidade} ({pct_consenso:.0f}% consenso): {significado.get('descricao')} — {significado.get('recomendacao_tecnica')}.",
            'por_avaliador': por_avaliador,
            'consenso': {'frequencia': len(alunos_consenso), 'percentual': round(pct_consenso, 1), 'alunos': sorted(list(alunos_consenso))}
        }
    return recomendacoes

# ============================================================================
# PONTOS POSITIVOS E RELATÓRIO MASTER
# ============================================================================
def gerar_pontos_positivos(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_alunos = len(results)
    codigo_freq = Counter([d['codigo'] for r in results for d in r['descontos_detalhados']])
    codigos_nao_apontados = set(PONTOS_POSITIVOS_V1_1.keys()) - set(codigo_freq.keys())
    
    categoria_erros = Counter([d['categoria'] for r in results for d in r['descontos_detalhados']])
    categoria_desempenho = {cat: {'erros': categoria_erros[cat], 'desempenho': round(100 - (categoria_erros[cat]/(total_alunos*4 if total_alunos > 0 else 1)*100), 1)} for cat in CATEGORIES}
    
    return {
        'excelencia_total': [PONTOS_POSITIVOS_V1_1[cod]['elogio'] for cod in sorted(codigos_nao_apontados)],
        'categoria_desempenho': categoria_desempenho,
        'alunos_destaque': sorted([r for r in results if r['status'] == 'Aprovado'], key=lambda x: x['nota_final'], reverse=True)[:3]
    }

def gerar_relatorio_master(results, suffix, recomendacoes, pontos_positivos):
    output_file = OUTPUT_DIR / f"relatorio_master_dojo_{suffix}.txt"
    media_dojo = sum(r['nota_final'] for r in results) / len(results) if results else 0.0
    
    # O SEGREDO: utf-8-sig resolve os caracteres quebrados no Telegram
    with open(output_file, 'w', encoding='utf-8-sig') as f:
        f.write(f"=== RELATÓRIO MASTER DO DOJO - {suffix.upper()} ===\n")
        f.write(f"Média Geral do Dojo: {media_dojo:.2f}\n\n")
        
        f.write("--- Desempenho por Aluno ---\n")
        for r in sorted(results, key=lambda x: x['nome']):
            f.write(f"{r['nome']}: {r['nota_final']} (Quorum: {r['quorum']}) - {r['status']}\n")
        
        f.write("\n--- RECOMENDAÇÕES PEDAGÓGICAS (OPÇÃO C) ---\n")
        for codigo, rec in recomendacoes.items():
            f.write(f"\n{rec['acao_sensei']}\n")
            f.write(f"  Consenso: {rec['consenso']['frequencia']}/{len(results)} alunos ({rec['consenso']['percentual']:.1f}%)\n")
            for av, stats in rec['por_avaliador'].items():
                f.write(f"    • {av}: {stats['frequencia']} alunos\n")

        f.write("\n--- PONTOS POSITIVOS DO DOJO ---\n")
        if pontos_positivos['excelencia_total']:
            f.write("\n✅ EXCELÊNCIA TOTAL:\n")
            for elogio in pontos_positivos['excelencia_total']: f.write(f"  • {elogio}\n")

        f.write("\n📊 DESEMPENHO POR CATEGORIA:\n")
        for cat, stats in pontos_positivos['categoria_desempenho'].items():
            f.write(f"  • {cat}: {stats['desempenho']:.1f}% de desempenho\n")

# ============================================================================
# PIPELINE PRINCIPAL
# ============================================================================
def run():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    exame_files = sorted(DATA_DIR.glob('exame-*.txt'))
    
    for filepath in exame_files:
        suffix = filepath.stem.replace('exame-', '')
        students = parse_file(filepath)
        if not students: continue
        
        results = [compute_student_result(st, ev) for st, ev in students.items()]
        
        with open(OUTPUT_DIR / f"relatorio_consolidado_{suffix}.json", 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        gerar_relatorio_master(results, suffix, gerar_recomendacoes_opcao_c(results), gerar_pontos_positivos(results))
        
        # SRE: shutil.move é atômico e seguro para volumes montados
        shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
        logger.info(f"Processado: {filepath.name}")

if __name__ == '__main__':
    run()