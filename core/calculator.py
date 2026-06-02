from typing import List, Dict, Any
from collections import Counter
from core.config import WEIGHT_TABLE, CATEGORIES, CODE_MEANINGS, PONTOS_POSITIVOS

def compute_category_score(codes: List[int]) -> float:
    score = 25.0
    for code in codes:
        score -= WEIGHT_TABLE.get(f'A{code}', 0.0)
    if 10 in codes:
        score = min(score, 10.0)
    return max(0.0, score)

def compute_student_result(student: str, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
    notas_finais = []
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
        notas_finais.append(soma_aluno)
    media = sum(notas_finais) / len(notas_finais) if notas_finais else 0.0
    return {
        'nome': student, 'nota_final': round(media, 2),
        'status': 'Aprovado' if media >= 70 else 'Reprovado',
        'quorum': len(evaluations), 'descontos_detalhados': all_descontos
    }

def analisar_pedagogico(results: List[Dict[str, Any]]):
    total_alunos = len(results)
    stats = {}
    for res in results:
        for desc in res['descontos_detalhados']:
            cod, av, aluno = desc['codigo'], desc['avaliador'], res['nome']
            stats.setdefault(cod, {}).setdefault(av, set()).add(aluno)
    
    recomendações = []
    for cod in sorted(stats.keys(), key=lambda x: sum(len(s) for s in stats[x].values()), reverse=True):
        av_dict = stats[cod]
        consenso = set.intersection(*[set(s) for s in av_dict.values()])
        pct = (len(consenso) / total_alunos) * 100
        prefix = "🔴 CRÍTICO" if pct >= 70 else "🟠 IMPORTANTE" if pct >= 50 else "🟡 ATENÇÃO"
        m = CODE_MEANINGS.get(cod, {})
        recomendações.append(f"{prefix} ({pct:.0f}% consenso): {m.get('descricao')} — {m.get('recomendacao')}")

    cod_freq = Counter([d['codigo'] for r in results for d in r['descontos_detalhados']])
    elogios = [PONTOS_POSITIVOS[c] for c in (set(PONTOS_POSITIVOS.keys()) - set(cod_freq.keys()))]
    
    return recomendações, elogios