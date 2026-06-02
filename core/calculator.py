from typing import List, Dict, Any, Tuple
from collections import Counter
from core.config import WEIGHT_TABLE, CATEGORIES, RECOMENDACOES, PONTOS_POSITIVOS

def compute_category_score(codes: List[int]) -> float:
    score = 25.0
    for code in codes:
        score -= WEIGHT_TABLE.get(f'A{code}', 0.0)
    if 10 in codes:
        score = min(score, 10.0)
    return max(0.0, score)

def compute_student_result(student: str, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
    notas_avaliadores = []
    all_descontos = []
    for ev in evaluations:
        soma_aluno = 0.0
        for cat in CATEGORIES:
            codes = ev['categories'][cat]
            cat_score = compute_category_score(codes)
            soma_aluno += cat_score
            for c in codes:
                all_descontos.append({
                    'codigo': f'A{c}', 'categoria': cat, 
                    'valor': WEIGHT_TABLE.get(f'A{c}', 0.0), 'avaliador': ev['evaluator']
                })
        notas_avaliadores.append(soma_aluno)
    media = sum(notas_avaliadores) / len(notas_avaliadores) if notas_avaliadores else 0.0
    return {
        'nome': student, 'nota_final': round(media, 2),
        'status': 'Aprovado' if media >= 70 else 'Reprovado',
        'quorum': len(evaluations), 'descontos_detalhados': all_descontos
    }

def analisar_dojo(results: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    total_alunos = len(results)
    stats = {}
    for res in results:
        for desc in res['descontos_detalhados']:
            cod, av, aluno = desc['codigo'], desc['avaliador'], res['nome']
            stats.setdefault(cod, {}).setdefault(av, set()).add(aluno)
    
    recomendações = []
    codigos_com_erro = set()
    
    for cod in sorted(stats.keys(), key=lambda x: sum(len(s) for s in stats[x].values()), reverse=True):
        av_dict = stats[cod]
        consenso = set.intersection(*[set(s) for s in av_dict.values()])
        pct = (len(consenso) / total_alunos) * 100
        
        config = RECOMENDACOES.get(cod, {})
        threshold = config.get('threshold', 0.30) * 100
        
        if pct >= threshold:
            prefix = config.get('severidade', '🟡 ATENÇÃO')
            recomendações.append(f"{prefix} ({pct:.0f}% consenso): {config.get('descricao')} — {config.get('recomendacao')}")
        
        codigos_com_erro.add(cod)

    elogios = []
    for cod, texto in PONTOS_POSITIVOS.items():
        if cod not in codigos_com_erro:
            elogios.append(f"EXCELÊNCIA: {texto}")
        else:
            alunos_com_erro = set().union(*stats[cod].values())
            incidencia = (len(alunos_com_erro) / total_alunos) * 100
            if incidencia < 15:
                elogios.append(f"FORÇA: {texto} ({100-incidencia:.0f}% de acerto)")
    
    return recomendações, elogios