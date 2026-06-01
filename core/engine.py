import json
import re
import os

# Pesos oficiais
PESOS = {
    "A1": 1.0, "A2": 2.0, "A3": 1.5, "A4": 2.5,
    "A5": 3.0, "A6": 1.0, "A7": 4.0, "A8": 2.0,
    "A9": 3.5, "A10": 12.0, "A11": 1.0, "A12": 5.0
}

# Categorias e seus códigos
CATEGORIAS = {
    "Kihon": "Kihon",
    "Kata": "Kata",
    "Bunkai": "Bunkai",
    "Kumite": "Kumite"
}

def extrair_codigos(texto):
    """Extrai códigos no formato 'cod:1,7' do texto."""
    padrao = r'cod:([\d,]+)'
    match = re.search(padrao, texto)
    if match:
        return [int(x.strip()) for x in match.group(1).split(',')]
    return []

def calcular_nota(codigos):
    """Calcula a nota para uma categoria baseada nos códigos de erro."""
    nota = 25.0
    for cod in codigos:
        chave = f"A{cod}"
        if chave in PESOS:
            nota -= PESOS[chave]
    return max(0.0, nota)

def processar_aluno(bloco_texto):
    """Processa um bloco de texto de um aluno e retorna o dicionário do aluno."""
    nome_match = re.search(r'Nome do aluno:\s*(.+)', bloco_texto)
    if not nome_match:
        return None
    
    nome = nome_match.group(1).strip()
    print(f"LOG: Processando aluno {nome}")
    
    aluno = {
        "nome": nome,
        "notas": {},
        "total": 0.0
    }
    
    for categoria in CATEGORIAS.values():
        # Encontrar o bloco da categoria
        padrao_categoria = rf'{categoria}\s*(.*?)(?=Kihon|Kata|Bunkai|Kumite|$)'
        match = re.search(padrao_categoria, bloco_texto, re.DOTALL)
        
        if match:
            texto_categoria = match.group(1)
            codigos = extrair_codigos(texto_categoria)
            nota = calcular_nota(codigos)
            
            # Aplicar teto de 10.0 no A10
            if 10 in codigos:
                nota = min(nota, 10.0)
            
            aluno["notas"][categoria] = {
                "codigos": codigos,
                "nota": round(nota, 2)
            }
            aluno["total"] += nota
        else:
            aluno["notas"][categoria] = {
                "codigos": [],
                "nota": 25.0
            }
            aluno["total"] += 25.0
    
    aluno["total"] = round(aluno["total"], 2)
    return aluno

def processar_texto(texto):
    """Processa o texto completo e retorna a lista de alunos."""
    # Divide o texto em blocos de alunos
    blocos = re.split(r'(?=Nome do aluno:)', texto)
    alunos = []
    
    for bloco in blocos:
        bloco = bloco.strip()
        if bloco:
            aluno = processar_aluno(bloco)
            if aluno:
                alunos.append(aluno)
    
    return alunos

def salvar_diagnostico(alunos, caminho="output/diagnostico.json"):
    """Salva a lista de alunos em um arquivo JSON."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(alunos, f, ensure_ascii=False, indent=2)
    print(f"Diagnóstico salvo em {caminho}")

def main():
    # Exemplo de texto para teste
    texto_exemplo = """
Nome do aluno: João Silva
Kihon cod:1,7
Kata cod:3,5
Bunkai cod:2,4
Kumite cod:6,8

Nome do aluno: Maria Santos
Kihon cod:10,1
Kata cod:2,3
Bunkai cod:4,5
Kumite cod:7,8
"""
    
    alunos = processar_texto(texto_exemplo)
    salvar_diagnostico(alunos)
    
    print("\nAlunos processados:")
    for aluno in alunos:
        print(f"\n{aluno['nome']}:")
        for categoria, dados in aluno['notas'].items():
            print(f"  {categoria}: {dados['nota']} (códigos: {dados['codigos']})")
        print(f"  Total: {aluno['total']}")

if __name__ == "__main__":
    main()