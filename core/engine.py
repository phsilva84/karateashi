import json
import logging
import shutil
from core.config import DATA_DIR, PROCESSED_DIR, OUTPUT_DIR
from core.parser import parse_file
from core.calculator import compute_student_result, analisar_dojo

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def gerar_relatorio_master(results, suffix, recomendações, elogios):
    master_file = OUTPUT_DIR / f"relatorio_master_dojo_{suffix}.txt"
    media_geral = sum(r['nota_final'] for r in results) / len(results) if results else 0.0
    with open(master_file, 'w', encoding='utf-8-sig') as f:
        f.write(f"=== RELATÓRIO MASTER DO DOJO - {suffix.upper()} ===\n")
        f.write(f"Média Geral do Dojo: {media_geral:.2f}\n\n")
        f.write("--- Desempenho por Aluno ---\n")
        for r in sorted(results, key=lambda x: x['nome']):
            f.write(f"{r['nome']}: {r['nota_final']} (Quorum: {r['quorum']}) - {r['status']}\n")
            if r['observacoes']: f.write(f"  • Observações: {r['observacoes']}\n")
        f.write("\n--- RECOMENDAÇÕES PEDAGÓGICAS (CONSENSO) ---\n")
        if recomendações:
            for rec in recomendações: f.write(f"• {rec}\n")
        else: f.write("Nenhuma falha sistêmica detectada acima do threshold.\n")
        f.write("\n--- PONTOS POSITIVOS DO DOJO ---\n")
        if elogios:
            for elo in sorted(elogios): f.write(f"✅ {elo}\n")
        else: f.write("Continue trabalhando os fundamentos básicos.\n")

def run():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filepath in sorted(DATA_DIR.glob('exame-*.txt')):
        suffix = filepath.stem.replace('exame-', '')
        
        logger.info(f"PROCESSANDO: {filepath.name}")
        data = parse_file(filepath)
        if not data: continue
        
        results = [compute_student_result(n, evs) for n, evs in data.items()]
        recs, elos = analisar_dojo(results)
        
        with open(OUTPUT_DIR / f"relatorio_consolidado_{suffix}.json", 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        gerar_relatorio_master(results, suffix, recs, elos)
        # Move para processados apenas após gerar tudo com sucesso
        shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))

if __name__ == '__main__':
    run()