from core.config import WEIGHT_TABLE, CATEGORIES, RECOMENDACOES, PONTOS_POSITIVOS

def compute_category_score(codes):
    """Calcula a nota baseada nos códigos de erro."""
    score = 25.0
    for code in codes:
        score -= WEIGHT_TABLE.get(code, 0)
    
    # Aplica teto de 10.0 se o código 10 estiver presente
    if 10 in codes:
        score = min(score, 10.0)
        
    return max(0.0, score)

def compute_student_result(student, evaluations):
    """Consolida notas e observações de múltiplos avaliadores."""
    total_score = 0
    observations = []
    discounts = []
    
    for eval_data in evaluations:
        sensei = eval_data.get('sensei', 'Desconhecido')
        codes = eval_data.get('codes', [])
        text = eval_data.get('obs', '')
        
        total_score += compute_category_score(codes)
        observations.append(f"{sensei}: {text}")
        discounts.extend([WEIGHT_TABLE.get(c, 0) for c in codes])

    avg_score = total_score / len(evaluations) if evaluations else 0
    quorum = len(evaluations) >= 2
    
    return {
        "nome": student,
        "nota_final": round(avg_score, 2),
        "status": "Aprovado" if avg_score >= 7.0 else "Reprovado",
        "quorum": quorum,
        "descontos_detalhados": discounts,
        "observacoes": "; ".join(observations)
    }

def analisar_dojo(results):
    """Realiza análise de consenso e identifica pontos positivos."""
    total_students = len(results)
    if total_students == 0: return {}

    error_counts = {}
    for res in results:
        for code in res.get('descontos_detalhados', []):
            error_counts[code] = error_counts.get(code, 0) + 1

    # Identifica pontos positivos (Força Relativa < 15%)
    pontos_positivos = []
    for code, count in error_counts.items():
        if (count / total_students) < 0.15:
            pontos_positivos.append(PONTOS_POSITIVOS.get(code, "Desempenho técnico sólido"))

    return {
        "total_avaliados": total_students,
        "pontos_positivos": list(set(pontos_positivos)),
        "recomendacoes_gerais": [RECOMENDACOES.get(c) for c in error_counts if error_counts[c] / total_students > 0.5]
    }