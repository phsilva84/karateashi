import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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
    'A1': {
        'descricao': 'Base incorreta',
        'inverso': 'Bases corretas',
        'elogio': 'Alunos com bom trabalho de bases e posicionamento de pés'
    },
    'A2': {
        'descricao': 'Execução técnica incorreta',
        'inverso': 'Execução técnica correta',
        'elogio': 'Alunos com boa execução técnica e forma correta'
    },
    'A3': {
        'descricao': 'Movimento sem carga/peso',
        'inverso': 'Movimento com carga/peso',
        'elogio': 'Alunos com boa transferência de peso e potência'
    },
    'A4': {
        'descricao': 'Ausência de kiai',
        'inverso': 'Kiai presente',
        'elogio': 'Alunos com boa respiração sincronizada e vocalização'
    },
    'A5': {
        'descricao': 'Embusen incorreto',
        'inverso': 'Embusen correto',
        'elogio': 'Alunos com excelente memorização e execução de kata'
    },
    'A6': {
        'descricao': 'Falta de foco / olhar incorreto',
        'inverso': 'Foco e olhar correto',
        'elogio': 'Alunos com excelente concentração e foco visual'
    },
    'A7': {
        'descricao': 'Perda de equilíbrio',
        'inverso': 'Equilíbrio mantido',
        'elogio': 'Alunos com excelente estabilidade e equilíbrio'
    },
    'A8': {
        'descricao': 'Falta de ritmo',
        'inverso': 'Ritmo correto',
        'elogio': 'Alunos com excelente sincronização e ritmo'
    },
    'A9': {
        'descricao': 'Defesa incompleta',
        'inverso': 'Defesa completa',
        'elogio': 'Alunos com excelente defesa e contra-ataques'
    },
    'A10': {
        'descricao': 'Falta de controle no ataque',
        'inverso': 'Controle no ataque',
        'elogio': 'Alunos com excelente controle e segurança no kumite'
    },
    'A11': {
        'descricao': 'Distância inadequada',
        'inverso': 'Distância adequada',
        'elogio': 'Alunos com excelente ma-ai (distância correta)'
    },
    'A12': {
        'descricao': 'Tensão / respiração inadequada',
        'inverso': 'Tensão / respiração adequada',
        'elogio': 'Alunos com excelente relaxamento e respiração'
    }
}

# ============================================================================
# PARSING FUNCTIONS
# ============================================================================
def _parse_evaluator(line: str) -> Optional[str]:
    """Extrai nome do avaliador com tolerância a variações."""
    patterns = [
        r'Avaliador\s+\d+\s+Sensei\s+\[(.+?)\]',
        r'Avaliador\s+\d+\s+Sensei\s+(.+?):\s*$',
        r'Avaliador\s+\d+\s+Sensei\s+(.+?)$',
    ]
    for pattern in patterns:
        m = re.search(pattern, line.strip())
        if m:
            return m.group(1).strip()
    return None

def _parse_student(line: str) -> Optional[str]:
    """Extrai nome do aluno com tolerância a variações."""
    patterns = [
        r'Nome do aluno:\s*\[(.+?)\]',
        r'Nome do aluno:\s*(.+?)$',
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
    """Parse robusto que suporta múltiplos avaliadores (1-3)."""
    students: Dict[str, List[Dict[str, Any]]] = {}
    current_evaluator, current_student, current_eval = None, None, None

    logger.info(f"Iniciando parse de {filepath.name}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            if not stripped: 
                continue
            
            ev = _parse_evaluator(stripped)
            if ev:
                current_evaluator = ev
                current_student = None
                current_eval = None
                logger.info(f"Avaliador detectado: {ev}")
                continue

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

            cat = _parse_category_code(stripped)
            if cat and current_eval:
                codes = _parse_codes(stripped)
                if codes:
                    current_eval['categories'][cat].extend(codes)

    logger.info(f"Parse concluído: {len(students)} alunos encontrados")
    return students

# ============================================================================
# CÁLCULO DE RESULTADO
# ============================================================================
def compute_category_score(codes: List[int]) -> float:
    """Calcula nota de uma categoria."""
    cat_score = 25.0
    for code in codes:
        code_key = f'A{code}'
        weight = WEIGHT_TABLE_V1_1.get(code_key, 0.0)
        cat_score -= weight
    
    if 10 in codes:
        cat_score = min(cat_score, 10.0)
    
    return max(0.0, cat_score)

def compute_student_result(student: str, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Consolida resultado com múltiplos avaliadores (Método CONSENSO)."""
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
                weight = WEIGHT_TABLE_V1_1.get(code_key, 0.0)
                all_descontos.append({
                    'codigo': code_key,
                    'categoria': cat,
                    'valor': weight,
                    'avaliador': ev['evaluator']
                })
        
        notas_por_avaliador.append(total)
    
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

# ============================================================================
# GERAÇÃO DE RECOMENDAÇÕES (OPÇÃO C: CONSENSO + DIVERGÊNCIA + CALIBRAÇÃO)
# ============================================================================
def gerar_recomendacoes_opcao_c(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Opção C: CONSENSO + DIVERGÊNCIA + CALIBRAÇÃO
    
    Retorna recomendações estruturadas com:
    - Frequência total agregada
    - Frequência por avaliador
    - Consenso (alunos apontados por TODOS)
    - Divergência (alunos apontados por ALGUNS)
    - Vieses (avaliador mais/menos rigoroso)
    - Ação Sensei (foco em melhoria)
    - Ação Calibração (foco em alinhamento)
    """
    
    total_alunos = len(results)
    
    # Agregar por código + avaliador
    codigo_avaliador_stats = {}
    for result in results:
        for desconto in result['descontos_detalhados']:
            codigo = desconto['codigo']
            avaliador = desconto['avaliador']
            aluno = result['nome']
            
            if codigo not in codigo_avaliador_stats:
                codigo_avaliador_stats[codigo] = {}
            
            if avaliador not in codigo_avaliador_stats[codigo]:
                codigo_avaliador_stats[codigo][avaliador] = set()
            
            codigo_avaliador_stats[codigo][avaliador].add(aluno)
    
    # Gerar recomendações ordenadas por frequência total
    recomendacoes = {}
    
    for codigo in sorted(codigo_avaliador_stats.keys(), 
                        key=lambda x: sum(len(alunos) for alunos in codigo_avaliador_stats[x].values()),
                        reverse=True):
        
        avaliadores_dict = codigo_avaliador_stats[codigo]
        
        # Frequência por avaliador
        por_avaliador = {}
        for avaliador, alunos_set in avaliadores_dict.items():
            por_avaliador[avaliador] = {
                'frequencia': len(alunos_set),
                'percentual': round((len(alunos_set) / total_alunos) * 100, 1),
                'alunos': sorted(list(alunos_set))
            }
        
        # Consenso: alunos apontados por TODOS os avaliadores
        alunos_consenso = set.intersection(*[set(alunos) for alunos in avaliadores_dict.values()])
        
        # Divergência: alunos apontados por ALGUNS (não todos)
        alunos_divergentes = set()
        for alunos_set in avaliadores_dict.values():
            alunos_divergentes.update(alunos_set)
        alunos_divergentes -= alunos_consenso
        
        # Vieses: avaliador mais/menos rigoroso
        avaliador_mais_rigoroso = max(avaliadores_dict.items(), key=lambda x: len(x[1]))
        avaliador_menos_rigoroso = min(avaliadores_dict.items(), key=lambda x: len(x[1]))
        pct_mais = (len(avaliador_mais_rigoroso[1]) / total_alunos) * 100
        pct_menos = (len(avaliador_menos_rigoroso[1]) / total_alunos) * 100
        diferenca_pct = pct_mais - pct_menos
        
        # Ação Sensei (baseada em consenso)
        percentual_consenso = (len(alunos_consenso) / total_alunos) * 100
        if percentual_consenso >= 70:
            intensidade = "🔴 CRÍTICO"
        elif percentual_consenso >= 50:
            intensidade = "🟠 IMPORTANTE"
        else:
            intensidade = "🟡 ATENÇÃO"
        
        significado = CODE_MEANINGS_V1_1.get(codigo, {})
        acao_sensei = (
            f"{intensidade} ({percentual_consenso:.0f}% consenso): {significado.get('descricao', 'erro')} — "
            f"{significado.get('recomendacao_tecnica', 'Revisar técnica')}."
        )
        
        # Ação Calibração (baseada em vieses > 20%)
        acao_calibracao = None
        if diferenca_pct >= 20:
            acao_calibracao = (
                f"⚠️ CALIBRAÇÃO: {avaliador_mais_rigoroso[0]} é {diferenca_pct:.0f}% mais rigoroso que "
                f"{avaliador_menos_rigoroso[0]} em '{significado.get('descricao', 'erro')}'. "
                f"Considerar alinhamento de critérios entre avaliadores."
            )
        
        recomendacoes[codigo] = {
            'descricao': significado.get('descricao', 'Código desconhecido'),
            'frequencia_total': sum(len(alunos) for alunos in avaliadores_dict.values()),
            'por_avaliador': por_avaliador,
            'consenso': {
                'alunos': sorted(list(alunos_consenso)),
                'frequencia': len(alunos_consenso),
                'percentual': round((len(alunos_consenso) / total_alunos) * 100, 1)
            },
            'divergencia': {
                'alunos': sorted(list(alunos_divergentes)),
                'frequencia': len(alunos_divergentes)
            },
            'vieses': {
                'avaliador_mais_rigoroso': f"{avaliador_mais_rigoroso[0]} ({len(avaliador_mais_rigoroso[1])}/{total_alunos})",
                'avaliador_menos_rigoroso': f"{avaliador_menos_rigoroso[0]} ({len(avaliador_menos_rigoroso[1])}/{total_alunos})",
                'diferenca_percentual': round(diferenca_pct, 1)
            },
            'acao_sensei': acao_sensei,
            'acao_calibracao': acao_calibracao
        }
    
    return recomendacoes

# ============================================================================
# GERAÇÃO DE PONTOS POSITIVOS
# ============================================================================
def gerar_pontos_positivos(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Identifica forças do Dojo baseado em BAIXA incidência de erros."""
    
    total_alunos = len(results)
    
    # Contar frequência de cada código
    codigo_frequencia = {}
    for result in results:
        for desconto in result['descontos_detalhados']:
            codigo = desconto['codigo']
            if codigo not in codigo_frequencia:
                codigo_frequencia[codigo] = 0
            codigo_frequencia[codigo] += 1
    
    # Códigos NÃO apontados (excelência total)
    todos_codigos = set(PONTOS_POSITIVOS_V1_1.keys())
    codigos_nao_apontados = todos_codigos - set(codigo_frequencia.keys())
    
    # Códigos com < 30% incidência (força relativa)
    codigos_forca_relativa = {}
    for codigo, frequencia in codigo_frequencia.items():
        percentual = (frequencia / total_alunos) * 100
        if percentual < 30:
            codigos_forca_relativa[codigo] = {
                'frequencia': frequencia,
                'percentual': round(percentual, 1),
                'alunos_sem_erro': total_alunos - frequencia
            }
    
    # Desempenho por categoria
    categoria_erros = {'Kihon': 0, 'Kata': 0, 'Bunkai': 0, 'Kumite': 0}
    for result in results:
        for desconto in result['descontos_detalhados']:
            categoria = desconto['categoria']
            categoria_erros[categoria] += 1
    
    categoria_desempenho = {}
    for categoria, erros in categoria_erros.items():
        total_possivel = total_alunos * 1  # Cada aluno pode ter múltiplos erros por categoria
        percentual_erro = (erros / (total_alunos * 4)) * 100 if total_alunos > 0 else 0
        categoria_desempenho[categoria] = {
            'erros': erros,
            'percentual_erro': round(percentual_erro, 1),
            'desempenho': round(100 - percentual_erro, 1)
        }
    
    # Desempenho por aluno
    aluno_desempenho = {}
    for result in results:
        aluno_desempenho[result['nome']] = {
            'nota_final': result['nota_final'],
            'status': result['status'],
            'erros': len(result['descontos_detalhados'])
        }
    
    # Alunos destaque (aprovados com melhor nota)
    alunos_aprovados = [r for r in results if r['status'] == 'Aprovado']
    alunos_destaque = sorted(alunos_aprovados, key=lambda x: x['nota_final'], reverse=True)[:3]
    
    return {
        'excelencia_total': {
            'codigos': sorted(list(codigos_nao_apontados)),
            'descricao': 'Dimensões onde o Dojo não teve nenhuma falha apontada',
            'elogios': [PONTOS_POSITIVOS_V1_1[cod]['elogio'] for cod in sorted(codigos_nao_apontados)]
        },
        'forca_relativa': {
            'codigos': sorted(codigos_forca_relativa.keys(), 
                            key=lambda x: codigos_forca_relativa[x]['percentual']),
            'detalhes': codigos_forca_relativa
        },
        'categoria_desempenho': categoria_desempenho,
        'aluno_desempenho': aluno_desempenho,
        'alunos_destaque': [
            {'nome': r['nome'], 'nota_final': r['nota_final']} 
            for r in alunos_destaque
        ]
    }

# ============================================================================
# GERAÇÃO DE RELATÓRIO MASTER (COM RECOMENDAÇÕES + PONTOS POSITIVOS)
# ============================================================================
def gerar_relatorio_master(
    results: List[Dict[str, Any]], 
    suffix: str,
    recomendacoes: Dict[str, Any],
    pontos_positivos: Dict[str, Any]
):
    """Gera relatório master com recomendações + pontos positivos."""
    
    output_file = OUTPUT_DIR / f"relatorio_master_dojo_{suffix}.txt"
    
    media_dojo = sum(r['nota_final'] for r in results) / len(results) if results else 0.0
    
    with open(output_file, 'w', encoding='utf-8') as f:
        # Cabeçalho
        f.write(f"=== RELATÓRIO MASTER DO DOJO - {suffix.upper()} ===\n")
        f.write(f"Média Geral do Dojo: {media_dojo:.2f}\n")
        f.write(f"Quorum Predominante: {results[0]['quorum'] if results else 1} avaliador(es)\n\n")
        
        # Desempenho por Aluno
        f.write("--- Desempenho por Aluno ---\n")
        for r in sorted(results, key=lambda x: x['nome']):
            f.write(f"{r['nome']}: {r['nota_final']} (Quorum: {r['quorum']}) - {r['status']}\n")
        
        # RECOMENDAÇÕES PEDAGÓGICAS (OPÇÃO C)
        f.write("\n--- RECOMENDAÇÕES PEDAGÓGICAS (OPÇÃO C: CONSENSO + DIVERGÊNCIA + CALIBRAÇÃO) ---\n\n")
        
        for codigo, rec in recomendacoes.items():
            f.write(f"{rec['acao_sensei']}\n")
            f.write(f"  Por Avaliador:\n")
            for avaliador, stats in rec['por_avaliador'].items():
                f.write(f"    • {avaliador}: {stats['frequencia']}/{len(results)} alunos ({stats['percentual']:.1f}%)\n")
            
            f.write(f"  Consenso (Todos os avaliadores): {rec['consenso']['frequencia']}/{len(results)} alunos ({rec['consenso']['percentual']:.1f}%)\n")
            
            if rec['divergencia']['alunos']:
                f.write(f"  Divergência (Alguns avaliadores): {', '.join(rec['divergencia']['alunos'])}\n")
            
            if rec['vieses']['diferenca_percentual'] > 0:
                f.write(f"  Viés: {rec['vieses']['avaliador_mais_rigoroso']} vs {rec['vieses']['avaliador_menos_rigoroso']} (Δ {rec['vieses']['diferenca_percentual']:.1f}%)\n")
            
            if rec['acao_calibracao']:
                f.write(f"  {rec['acao_calibracao']}\n")
            
            f.write("\n")
        
        # PONTOS POSITIVOS
        f.write("--- PONTOS POSITIVOS DO DOJO ---\n\n")
        
        if pontos_positivos['excelencia_total']['codigos']:
            f.write("✅ EXCELÊNCIA TOTAL (Nenhuma falha apontada):\n")
            for elogio in pontos_positivos['excelencia_total']['elogios']:
                f.write(f"  • {elogio}\n")
            f.write("\n")
        
        if pontos_positivos['forca_relativa']['codigos']:
            f.write("✅ FORÇA RELATIVA (< 30% incidência):\n")
            for codigo in pontos_positivos['forca_relativa']['codigos']:
                stats = pontos_positivos['forca_relativa']['detalhes'][codigo]
                significado = CODE_MEANINGS_V1_1.get(codigo, {})
                f.write(f"  • {codigo} ({significado.get('descricao', 'erro')}): {stats['percentual']:.1f}% — {PONTOS_POSITIVOS_V1_1[codigo]['elogio']}\n")
            f.write("\n")
        
        # Desempenho por Categoria
        f.write("📊 DESEMPENHO POR CATEGORIA:\n")
        for categoria, stats in pontos_positivos['categoria_desempenho'].items():
            f.write(f"  • {categoria}: {stats['desempenho']:.1f}% de desempenho ({stats['erros']} erros)\n")
        f.write("\n")
        
        # Alunos Destaque
        if pontos_positivos['alunos_destaque']:
            f.write("🏆 ALUNOS DESTAQUE:\n")
            for aluno in pontos_positivos['alunos_destaque']:
                f.write(f"  • {aluno['nome']}: {aluno['nota_final']} (Aprovado)\n")
            f.write("\n")
        
        # Recomendação Estratégica
        f.write("💡 RECOMENDAÇÃO ESTRATÉGICA:\n")
        categoria_melhor = max(pontos_positivos['categoria_desempenho'].items(), 
                              key=lambda x: x[1]['desempenho'])
        categoria_pior = min(pontos_positivos['categoria_desempenho'].items(), 
                            key=lambda x: x[1]['desempenho'])
        f.write(f"  O Dojo tem excelente desempenho em {categoria_melhor[0]} ({categoria_melhor[1]['desempenho']:.1f}%).\n")
        f.write(f"  Foco deve ser em {categoria_pior[0]} ({categoria_pior[1]['desempenho']:.1f}%).\n")
        f.write(f"  Manter força em {categoria_melhor[0]}, melhorar {categoria_pior[0]}.\n")
    
    logger.info(f"Relatório Master salvo em {output_file}")

# ============================================================================
# PIPELINE PRINCIPAL
# ============================================================================
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
                
                # Gera recomendações (Opção C)
                recomendacoes = gerar_recomendacoes_opcao_c(results)
                
                # Gera pontos positivos
                pontos_positivos = gerar_pontos_positivos(results)
                
                # Salva TXT dinâmico com recomendações + pontos positivos
                gerar_relatorio_master(results, suffix, recomendacoes, pontos_positivos)
            
            # Move para processados
            dest = PROCESSED_DIR / filepath.name
            filepath.rename(dest)
            logger.info(f"Arquivo movido para {dest}")
            
        except Exception as e:
            logger.error(f"Erro ao processar {filepath.name}: {e}", exc_info=True)

if __name__ == '__main__':
    run()