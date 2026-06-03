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
    obs_list = []
    
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
        if ev.get('observation'):
            obs_list.append(f"[{ev['evaluator']}]: {ev['observation']}")
    
    media = sum(notas_avaliadores) / len(notas_avaliadores) if notas_avaliadores else 0.0
    return {
        'nome': student, 'nota_final': round(media, 2),
        'status': 'Aprovado' if media >= 70 else 'Reprovado',
        'quorum': len(evaluations), 'descontos_detalhados': all_descontos,
        'observacoes': " ; ".join(obs_list)
    }

def analisar_dojo(results: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    total_alunos = len(results)
    # Identifica quantos avaliadores únicos existem no exame
    avaliadores_unicos = set(d['avaliador'] for r in results for d in r['descontos_detalhados'])
    num_avaliadores = len(avaliadores_unicos)
    
    stats = {}
    for res in results:
        for desc in res['descontos_detalhados']:
            cod, av, aluno = desc['codigo'], desc['avaliador'], res['nome']
            stats.setdefault(cod, {}).setdefault(av, set()).add(aluno)
    
    recomendações = []
    codigos_com_erro = set()
    for cod in sorted(stats.keys(), key=lambda x: sum(len(s) for s in stats[x].values()), reverse=True):
        av_dict = stats[cod]
        
        # Consenso SRE: Só existe se TODOS os avaliadores viram o erro
        if len(av_dict) < num_avaliadores:
            consenso = set()
        else:
            consenso = set.intersection(*[set(s) for s in av_dict.values()])
            
        pct = (len(consenso) / total_alunos) * 100
        config = RECOMENDACOES.get(cod, {})
        threshold = config.get('threshold', 0.30) * 100
        
        if pct >= threshold:
            recomendações.append(f"{config.get('severidade')} ({pct:.0f}% consenso): {config.get('descricao')} — {config.get('recomendacao')}")
        
        codigos_com_erro.add(cod)

    elogios = []
    for cod, texto in PONTOS_POSITIVOS.items():
        if cod not in codigos_com_erro:
            elogios.append(f"EXCELÊNCIA: {texto}")
        else:
            alunos_com_erro = set().union(*stats[cod].values())
            incidencia = (len(alunos_com_erro) / total_alunos) * 100
            # Se menos de 20% do dojo errou, vira um ponto de força
            if incidencia < 20:
                elogios.append(f"FORÇA: {texto} ({100-incidencia:.0f}% de acerto)")
    
    return recomendações, elogios