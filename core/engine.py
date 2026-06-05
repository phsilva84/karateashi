import json
import logging
import shutil
import hashlib
from pathlib import Path
from core.config import DATA_DIR, PROCESSED_DIR, OUTPUT_DIR, RECOMENDACOES
from core.parser import parse_file
from core.calculator import compute_student_result, analisar_dojo

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

CHECKSUM_FILE = OUTPUT_DIR / ".checksums.json"

def get_file_hash(filepath):
    """Gera um hash MD5 do conteúdo do arquivo."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def load_checksums():
    if CHECKSUM_FILE.exists():
        with open(CHECKSUM_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_checksums(checksums):
    with open(CHECKSUM_FILE, 'w') as f:
        json.dump(checksums, f, indent=2)

def run():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Flag para o Telegram
    flag_file = OUTPUT_DIR / ".new_processed"
    if flag_file.exists(): flag_file.unlink()
    
    checksums = load_checksums()
    new_reports_count = 0
    
    for filepath in sorted(DATA_DIR.glob('exame-*.txt')):
        suffix = filepath.stem.replace('exame-', '')
        current_hash = get_file_hash(filepath)
        
        # VALIDAÇÃO SRE: Se o hash for igual ao anterior, ignora o processamento
        if checksums.get(filepath.name) == current_hash:
            logger.info(f"SKIP: Arquivo {filepath.name} sem modificacoes detectadas.")
            shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
            continue
            
        logger.info(f"PROCESSANDO MODIFICACOES: {filepath.name}")
        data = parse_file(filepath)
        if not data: continue
        
        results = [compute_student_result(n, evs) for n, evs in data.items()]
        recs, elos = analisar_dojo(results)
        
        # Gera os relatórios
        gerar_relatorio_master(results, suffix, recs, elos)
        
        # Atualiza a "memória" de hashes
        checksums[filepath.name] = current_hash
        new_reports_count += 1
        shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
    
    if new_reports_count > 0:
        save_checksums(checksums)
        with open(flag_file, "w") as f: f.write(str(new_reports_count))
        logger.info(f"Sucesso: {new_reports_count} novos relatorios gerados.")

# ... (função gerar_relatorio_master permanece igual à v1.1.8)