import json
import logging
import shutil
from pathlib import Path
from core.config import DATA_DIR, PROCESSED_DIR, OUTPUT_DIR
from core.parser import parse_file
from core.calculator import compute_student_result

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def run():
    # Garantir diretórios
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Processar arquivos de exame
    for filepath in sorted(DATA_DIR.glob('exame-*.txt')):
        suffix = filepath.stem.replace('exame-', '')
        master_file = OUTPUT_DIR / f"relatorio_master_dojo_{suffix}.txt"
        
        # IDEMPOTÊNCIA SRE: Skip se o relatório já existe
        if master_file.exists():
            logger.info(f"SKIP: Relatório {suffix} já existe. Movendo arquivo original.")
            shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
            continue
            
        logger.info(f"PROCESSANDO: {filepath.name}")
        students_data = parse_file(filepath)
        if not students_data:
            logger.warning(f"Aviso: Nenhum dado extraído de {filepath.name}")
            continue
        
        results = [compute_student_result(name, evs) for name, evs in students_data.items()]
        
        # Salva o JSON Consolidado
        json_out = OUTPUT_DIR / f"relatorio_consolidado_{suffix}.json"
        with open(json_out, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        # Gera o Relatório Master TXT (UTF-8 com BOM para o Telegram)
        with open(master_file, 'w', encoding='utf-8-sig') as f:
            f.write(f"=== RELATÓRIO MASTER DO DOJO - {suffix.upper()} ===\n\n")
            for r in results:
                f.write(f"{r['nome']}: {r['nota_final']} - {r['status']}\n")
        
        # Move para processados de forma atômica
        shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
        logger.info(f"SUCESSO: {filepath.name} processado.")

if __name__ == '__main__':
    run()