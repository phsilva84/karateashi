import json
import logging
import shutil
import hashlib
from core.config import DATA_DIR, PROCESSED_DIR, OUTPUT_DIR, RECOMENDACOES
from core.parser import parse_file
from core.calculator import compute_student_result, analisar_dojo

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

CHECKSUM_FILE = OUTPUT_DIR / ".checksums.json"
MANIFEST_FILE = OUTPUT_DIR / ".files_to_send"

def get_file_hash(filepath):
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

def load_checksums():
    if CHECKSUM_FILE.exists():
        with open(CHECKSUM_FILE, 'r') as f: return json.load(f)
    return {}

def run():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Limpa o manifesto de envios anteriores
    if MANIFEST_FILE.exists(): MANIFEST_FILE.unlink()
    
    checksums = load_checksums()
    new_files = []
    
    for filepath in sorted(DATA_DIR.glob('exame-*.txt')):
        suffix = filepath.stem.replace('exame-', '')
        current_hash = get_file_hash(filepath)
        
        if checksums.get(filepath.name) == current_hash:
            logger.info(f"SKIP: {filepath.name} sem alteracoes.")
            shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
            continue
            
        logger.info(f"PROCESSANDO: {filepath.name}")
        data = parse_file(filepath)
        if not data: continue
        
        results = [compute_student_result(n, evs) for n, evs in data.items()]
        recs, elos = analisar_dojo(results)
        
        # Gera o relatório
        master_path = OUTPUT_DIR / f"relatorio_master_dojo_{suffix}.txt"
        gerar_relatorio_master(results, suffix, recs, elos)
        
        # Adiciona ao manifesto de envio
        new_files.append(str(master_path))
        checksums[filepath.name] = current_hash
        shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
    
    if new_files:
        with open(CHECKSUM_FILE, 'w') as f: json.dump(checksums, f, indent=2)
        with open(MANIFEST_FILE, 'w') as f:
            for line in new_files: f.write(f"{line}\n")
        logger.info(f"Manifesto criado com {len(new_files)} arquivos.")

# ... (gerar_relatorio_master permanece igual)