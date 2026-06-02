from typing import List, Dict, Any
from core.config import WEIGHT_TABLE, CATEGORIES

def compute_category_score(codes: List[int]) -> float:
    score = 25.0
    for code in codes:
        score -= WEIGHT_TABLE.get(f'A{code}', 0.0)
    
    # REGRA CRÍTICA A10: Teto de 10.0 se houver falta de controle
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
        'nome': student,
        'nota_final': round(media, 2),
        'status': 'Aprovado' if media >= 70 else 'Reprovado',
        'quorum': len(evaluations),
        'descontos_detalhados': all_descontos
    }