import json
import logging
import shutil
from core.config import DATA_DIR, PROCESSED_DIR, OUTPUT_DIR
from core.parser import parse_file
from core.calculator import compute_student_result
# Aqui você importaria as funções de relatório que geramos antes

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def run():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    for filepath in sorted(DATA_DIR.glob('exame-*.txt')):
        suffix = filepath.stem.replace('exame-', '')
        master_file = OUTPUT_DIR / f"relatorio_master_dojo_{suffix}.txt"
        
        # IDEMPOTÊNCIA SRE: Skip se o relatório já existe
        if master_file.exists():
            logger.info(f"SKIP: Relatório {suffix} já existe. Movendo para processados.")
            shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
            continue
            
        logger.info(f"PROCESSANDO: {filepath.name}")
        students_data = parse_file(filepath)
        if not students_data: continue
        
        results = [compute_student_result(name, evs) for name, evs in students_data.items()]
        
        # Salva o JSON Consolidado
        with open(OUTPUT_DIR / f"relatorio_consolidado_{suffix}.json", 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        # Aqui chamamos a função de gerar o TXT (com utf-8-sig)
        # gerar_relatorio_master(results, suffix, ...)
        
        shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
        logger.info(f"SUCESSO: {filepath.name} finalizado.")

if __name__ == '__main__':
    run()