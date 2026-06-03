from typing import List, Dict, Any, Tuple
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
    obs_dict = {}
    contagem_codigos = {} # Novo: { 'A1': 5, 'A10': 2 }
    
    for ev in evaluations:
        soma_aluno = 0.0
        for cat in CATEGORIES:
            codes = ev['categories'][cat]
            for c in codes:
                cod_str = f'A{c}'
                contagem_codigos[cod_str] = contagem_codigos.get(cod_str, 0) + 1
                all_descontos.append({
                    'codigo': cod_str, 'categoria': cat, 'avaliador': ev['evaluator']
                })
            soma_aluno += compute_category_score(codes)
        notas_avaliadores.append(soma_aluno)
        if ev.get('observation'):
            obs_dict[ev['evaluator']] = ev['observation']
    
    media = sum(notas_avaliadores) / len(notas_avaliadores) if notas_avaliadores else 0.0
    return {
        'nome': student,
        'nota_final': round(media, 2),
        'status': 'Aprovado' if media >= 70 else 'Reprovado',
        'quorum': len(evaluations),
        'detalhe_codigos': contagem_codigos,
        'total_marcacoes': len(all_descontos),
        'descontos_detalhados': all_descontos,
        'observacoes_por_sensei': obs_dict
    }

def analisar_dojo(results: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    total_alunos = len(results)
    avaliadores_unicos = set(d['avaliador'] for r in results for d in r['descontos_detalhados'])
    num_avaliadores = len(avaliadores_unicos)
    
    stats = {}
    for res in results:
        for desc in res['descontos_detalhados']:
            cod, av, aluno = desc['codigo'], desc['avaliador'], res['nome']
            stats.setdefault(cod, {}).setdefault(av, set()).add(aluno)
    
    recomendações = []
    codigos_com_erro = set()
    
    for cod in sorted(RECOMENDACOES.keys()):
        av_dict = stats.get(cod, {})
        if len(av_dict) == num_avaliadores:
            consenso = set.intersection(*[set(s) for s in av_dict.values()])
            qtd = len(consenso)
            pct = (qtd / total_alunos) * 100
            config = RECOMENDACOES[cod]
            if pct >= (config.get('threshold', 0.30) * 100):
                recomendações.append(f"{config['severidade']} ({pct:.0f}% - {qtd}/{total_alunos} alunos): {config['descricao']} — {config['recomendacao']}")
                codigos_com_erro.add(cod)

    elogios = []
    for cod, texto in PONTOS_POSITIVOS.items():
        alunos_com_erro = set().union(*stats.get(cod, {}).values()) if cod in stats else set()
        qtd_acerto = total_alunos - len(alunos_com_erro)
        pct_acerto = (qtd_acerto / total_alunos) * 100
        
        if pct_acerto == 100:
            elogios.append(f"⭐ EXCELÊNCIA (100% - {qtd_acerto}/{total_alunos} alunos): {texto}")
        elif pct_acerto >= 85:
            elogios.append(f"✅ DESTAQUE ({pct_acerto:.0f}% - {qtd_acerto}/{total_alunos} alunos): {texto}")
        elif pct_acerto >= 75:
            elogios.append(f"🔹 FORÇA ({pct_acerto:.0f}% - {qtd_acerto}/{total_alunos} alunos): {texto}")
            
    return recomendações, elogios