import os
import json
import shutil
from core.config import DATA_DIR, PROCESSED_DIR, OUTPUT_DIR
from core.parser import parse_file
from core.calculator import compute_student_result, analisar_dojo

def gerar_relatorio_master(results, suffix, recomendacoes, elogios):
    filename = os.path.join(OUTPUT_DIR, f"relatorio_master_{suffix}.txt")
    with open(filename, "w", encoding="utf-8-sig") as f:
        f.write("RELATÓRIO MASTER - KARATE-ASHI V1.1.4\n")
        f.write("="*40 + "\n\n")
        for student in results:
            f.write(f"Aluno: {student['nome']}\n")
            f.write(f"Observações: {student.get('observacoes', 'Nenhuma')}\n")
            f.write("-"*20 + "\n")
        f.write("\nRECOMENDAÇÕES DE CONSENSO:\n")
        for rec in recomendacoes:
            f.write(f"- {rec}\n")
        f.write("\nPONTOS POSITIVOS:\n")
        for elogio in elogios:
            f.write(f"- {elogio}\n")

def run():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    files = [f for f in os.listdir(DATA_DIR) if f.startswith("exame-") and f.endswith(".txt")]
    
    for filename in files:
        input_path = os.path.join(DATA_DIR, filename)
        suffix = filename.replace("exame-", "").replace(".txt", "")
        output_txt = os.path.join(OUTPUT_DIR, f"relatorio_master_{suffix}.txt")
        
        if os.path.exists(output_txt):
            print(f"Relatório {suffix} já existe. Pulando processamento.")
            shutil.move(input_path, os.path.join(PROCESSED_DIR, filename))
            continue
            
        data = parse_file(input_path)
        results = [compute_student_result(s) for s in data]
        analise = analisar_dojo(results)
        
        gerar_relatorio_master(results, suffix, analise['recomendacoes'], analise['elogios'])
        
        json_path = os.path.join(OUTPUT_DIR, f"data_{suffix}.json")
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(results, jf, indent=4, ensure_ascii=False)
            
        shutil.move(input_path, os.path.join(PROCESSED_DIR, filename))
        print(f"Processado com sucesso: {filename}")

if __name__ == "__main__":
    run()