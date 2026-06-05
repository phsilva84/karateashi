import json
import logging
import shutil
import hashlib
from core.config import DATA_DIR, PROCESSED_DIR, OUTPUT_DIR, RECOMENDACOES
from core.parser import parse_file
from core.calculator import compute_student_result, analisar_dojo

# Configuração de Logs para Observabilidade SRE
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

CHECKSUM_FILE = OUTPUT_DIR / ".checksums.json"
MANIFEST_FILE = OUTPUT_DIR / ".files_to_send"

def get_file_hash(filepath):
    """Gera uma assinatura digital (MD5) do conteúdo do arquivo."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

def load_checksums():
    """Carrega o histórico de assinaturas do Google Drive."""
    if CHECKSUM_FILE.exists():
        try:
            with open(CHECKSUM_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao ler checksums: {e}")
    return {}

def gerar_relatorio_master(results, suffix, recomendações, elogios):
    """Gera o arquivo TXT formatado para o Sensei."""
    master_file = OUTPUT_DIR / f"relatorio_master_dojo_{suffix}.txt"
    media_geral = sum(r['nota_final'] for r in results) / len(results) if results else 0.0
    
    with open(master_file, 'w', encoding='utf-8-sig') as f:
        f.write(f"=== RELATORIO MASTER DO DOJO - {suffix.upper()} ===\n")
        f.write(f"Media Geral do Dojo: {media_geral:.2f}\n\n")
        
        f.write("--- DESEMPENHO POR ALUNO ---\n\n")
        for r in sorted(results, key=lambda x: x['nome']):
            f.write(f"ALUNO: {r['nome']} | NOTA: {r['nota_final']} [Meta: {r['meta']}]\n")
            if r['detalhe_codigos']:
                for cod, qtd in sorted(r['detalhe_codigos'].items()):
                    desc = RECOMENDACOES.get(cod, {}).get('descricao', 'Erro')
                    f.write(f"   [{cod} - {desc}] {qtd}x\n")
            f.write("\n")
            
        f.write("--- RECOMENDACOES (CONSENSO) ---\n")
        for rec in recomendações: f.write(f"* {rec}\n")
        f.write("\n--- DESTAQUES ---\n")
        for elo in elogios: f.write(f"* {elo}\n")
    
    return master_file

def run():
    """Motor principal com trava de validação."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Limpa manifesto anterior
    if MANIFEST_FILE.exists(): MANIFEST_FILE.unlink()
    
    checksums = load_checksums()
    new_files = []
    
    # Busca arquivos de exame na pasta data/
    exames = list(DATA_DIR.glob('exame-*.txt'))
    if not exames:
        logger.info("Nenhum arquivo encontrado em data/ para processar.")
        return

    for filepath in sorted(exames):
        suffix = filepath.stem.replace('exame-', '')
        current_hash = get_file_hash(filepath)
        
        # VALIDAÇÃO: Só processa se o conteúdo mudou
        if checksums.get(filepath.name) == current_hash:
            logger.info(f"SKIP: {filepath.name} ja processado e sem alteracoes.")
            shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
            continue
            
        logger.info(f"PROCESSANDO MUDANCAS EM: {filepath.name}")
        data = parse_file(filepath)
        if not data: continue
        
        results = [compute_student_result(n, evs) for n, evs in data.items()]
        recs, elos = analisar_dojo(results)
        
        # Gera artefatos
        master_path = gerar_relatorio_master(results, suffix, recs, elos)
        
        # Registra para o manifesto e atualiza hash
        new_files.append(str(master_path))
        checksums[filepath.name] = current_hash
        shutil.move(str(filepath), str(PROCESSED_DIR / filepath.name))
    
    # Persiste as mudanças se houver novos arquivos
    if new_files:
        with open(CHECKSUM_FILE, 'w') as f: json.dump(checksums, f, indent=2)
        with open(MANIFEST_FILE, 'w') as f:
            for line in new_files: f.write(f"{line}\n")
        logger.info(f"Sucesso: {len(new_files)} novos relatorios no manifesto.")
    else:
        logger.info("Fim da execuçao: nada novo para enviar.")

# CRÍTICO: Ponto de entrada que estava faltando
if __name__ == '__main__':
    run()