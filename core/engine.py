import json
import logging
import shutil
from core.config import DATA_DIR, PROCESSED_DIR, OUTPUT_DIR, RECOMENDACOES
from core.parser import parse_file
from core.calculator import compute_student_result, analisar_dojo

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def gerar_relatorio_master(results, suffix, recomendações, elogios):
    master_file = OUTPUT_DIR / f"relatorio_master_dojo_{suffix}.txt"
    media_geral = sum(r['nota_final'] for r in results) / len(results) if results else 0.0
    
    with open(master_file, 'w', encoding='utf-8-sig') as f:
        f.write(f"=== RELATORIO MASTER DO DOJO - {suffix.upper()} ===\n")
        f.write(f"Media Geral do Dojo: {media_geral:.2f}\n\n")
        
        f.write("--- DESEMPENHO POR ALUNO ---\n\n")
        for r in sorted(results, key=lambda x: x['nome']):
            f.write(f"ALUNO: {r['nome']} | NOTA: {r['nota_final']} (Quorum: {r['quorum']}) [Meta: {r['meta']}]\n")
            f.write(f"   Status: {r['status']} | Marcacoes Totais: {r['total_marcacoes']}\n")
            
            if r['detalhe_codigos']:
                f.write("   Falhas Detectadas:\n")
                for cod, qtd in sorted(r['detalhe_codigos'].items()):
                    desc = RECOMENDACOES.get(cod, {}).get('descricao', 'Erro Desconhecido')
                    f.write(f"     [{cod} - {desc}] {qtd}x\n")
            
            if r['observacoes_por_sensei']:
                f.write("   Observacoes:\n")
                for sensei, texto in r['observacoes_por_sensei'].items():
                    f.write(f"     [Sensei {sensei}] - {texto}\n")
            f.write("\n\n")
        
        f.write("--- RECOMENDACOES PEDAGOGICAS AO SENSEI (CONSENSO) ---\n\n")
        if recomendações:
            for rec in recomendações: f.write(f"* {rec}\n")
        else:
            f.write("Nenhuma falha sistemica detectada acima do threshold.\n")
            
        f.write("\n--- DESTAQUES E PONTOS POSITIVOS DO DOJO ---\n\n")
        if elogios:
            for elo in sorted(elogios, reverse=True): f.write(f"* {elo}\n")
        else:
            f.write("Continue trabalhando os fundamentos basicos.\n")

def run():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Remove flag de processamento anterior se existir
    flag_file = OUTPUT_DIR / ".new_processed"
    if flag_file.exists(): flag_file.unlink()
    
    new_reports_count = 0
    
    for filepath in sorted(DATA_DIR.glob('exame-*.txt')):
        suffix = filepath.stem.replace('exame-', '')
        
        # Idempotência: Se o master já existe (baixado do GD), pula
        if (OUTPUT_DIR / f"relatorio_master_dojo_{suffix}.txt").exists():
            shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
            continue
            
        logger.info(f"PROCESSANDO NOVO EXAME: {filepath.name}")
        data = parse_file(filepath)
        if not data: continue
        
        results = [compute_student_result(n, evs) for n, evs in data.items()]
        recs, elos = analisar_dojo(results)
        
        with open(OUTPUT_DIR / f"relatorio_consolidado_{suffix}.json", 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        gerar_relatorio_master(results, suffix, recs, elos)
        new_reports_count += 1
        shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
    
    # Cria o flag file se houver novos processamentos
    if new_reports_count > 0:
        with open(flag_file, "w") as f:
            f.write(str(new_reports_count))
        logger.info(f"Sucesso: {new_reports_count} novos relatórios gerados.")

if __name__ == '__main__':
    run()