import os
import glob
import json
import logging
import re
from typing import Dict, List, Tuple, Optional

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Pesos v1.1
PESOS = {
    'A1': 1.0, 'A2': 2.0, 'A3': 1.5, 'A4': 2.5, 'A5': 3.0,
    'A6': 1.0, 'A7': 4.0, 'A8': 2.0, 'A9': 3.5, 'A10': 12.0,
    'A11': 1.0, 'A12': 5.0
}

CATEGORIAS = ['Kihon', 'Kata', 'Bunkai', 'Kumite']

def parse_file(filepath: str) -> List[dict]:
    """Analisa um arquivo de avaliação e retorna uma lista de avaliações.
    Cada avaliação é um dicionário com:
        - avaliador: str
        - aluno: str
        - categorias: dict (ex: {'Kihon': [1, 3, 7], 'Kata': [10], ...})
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        linhas = f.readlines()
    
    avaliacoes = []
    estado = 'INICIO'  # INICIO, AVALIADOR, ALUNO, CATEGORIA
    avaliador_atual = None
    aluno_atual = None
    categorias_atual = {cat: [] for cat in CATEGORIAS}
    categoria_atual = None

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue

        # Verifica linha "Avaliador X Sensei [Nome]:"
        match_av = re.match(r'^Avaliador\s+\d+\s+Sensei\s+(.+?):\s*$', linha)
        if match_av:
            # Finaliza avaliação anterior, se existir
            if aluno_atual is not None:
                avaliacoes.append({
                    'avaliador': avaliador_atual,
                    'aluno': aluno_atual,
                    'categorias': dict(categorias_atual)
                })
                logging.info(f"Avaliador {avaliador_atual} finalizou avaliação do aluno {aluno_atual}")
            # Inicia novo contexto de avaliador
            avaliador_atual = match_av.group(1).strip()
            aluno_atual = None
            categorias_atual = {cat: [] for cat in CATEGORIAS}
            categoria_atual = None
            estado = 'AVALIADOR'
            continue

        # Verifica linha "Nome do aluno: [Nome]"
        match_aluno = re.match(r'^Nome do aluno:\s+(.+?)\s*$', linha)
        if match_aluno:
            # Finaliza avaliação anterior se houver aluno ativo
            if aluno_atual is not None:
                avaliacoes.append({
                    'avaliador': avaliador_atual,
                    'aluno': aluno_atual,
                    'categorias': dict(categorias_atual)
                })
                logging.info(f"Avaliador {avaliador_atual} finalizou avaliação do aluno {aluno_atual}")
            aluno_atual = match_aluno.group(1).strip()
            categorias_atual = {cat: [] for cat in CATEGORIAS}
            categoria_atual = None
            estado = 'ALUNO'
            continue

        # Verifica linhas de categoria: "Kihon:", "Kata:", etc.
        for cat in CATEGORIAS:
            if linha.startswith(cat + ':'):
                categoria_atual = cat
                # Extrai códigos após o ':'
                resto = linha[len(cat)+1:].strip()
                codigos = re.findall(r'\d+', resto)
                for cod in codigos:
                    categorias_atual[cat].append(int(cod))
                estado = 'CATEGORIA'
                break
        else:
            # Linha dentro de uma categoria (sem o cabeçalho): pode conter códigos
            if estado == 'CATEGORIA' and categoria_atual:
                codigos = re.findall(r'\d+', linha)
                for cod in codigos:
                    categorias_atual[categoria_atual].append(int(cod))

    # Finaliza última avaliação do arquivo
    if aluno_atual is not None:
        avaliacoes.append({
            'avaliador': avaliador_atual,
            'aluno': aluno_atual,
            'categorias': dict(categorias_atual)
        })
        logging.info(f"Avaliador {avaliador_atual} finalizou avaliação do aluno {aluno_atual}")

    return avaliacoes

def calcular_nota_categoria(codigos: List[int]) -> float:
    """Calcula a nota de uma categoria a partir dos códigos de erro.
    Regra: inicia com 25.0, subtrai pesos; se código 10 presente, teto 10.0.
    """
    nota = 25.0
    for cod in codigos:
        chave = f'A{cod}'
        if chave in PESOS:
            nota -= PESOS[chave]
    if 10 in codigos:
        nota = min(nota, 10.0)
    return max(nota, 0.0)  # não negativa

def calcular_nota_total(categorias: Dict[str, List[int]]) -> float:
    """Calcula a nota total do aluno para um avaliador.
    Soma das notas das 4 categorias.
    """
    total = 0.0
    for cat in CATEGORIAS:
        total += calcular_nota_categoria(categorias.get(cat, []))
    return round(total, 2)

def consolidar_alunos(avaliacoes: List[dict]) -> Dict[str, dict]:
    """Agrupa avaliações por aluno e calcula nota final, método e quorum.
    """
    alunos = {}
    for av in avaliacoes:
        nome = av['aluno']
        if nome not in alunos:
            alunos[nome] = {'notas': [], 'avaliadores': set()}
        nota = calcular_nota_total(av['categorias'])
        alunos[nome]['notas'].append(nota)
        alunos[nome]['avaliadores'].add(av['avaliador'])
        logging.info(f"Aluno {nome}: avaliação do avaliador {av['avaliador']} -> nota {nota}")

    resultado = {}
    for nome, dados in alunos.items():
        notas = dados['notas']
        num_avaliadores = len(dados['avaliadores'])
        media = round(sum(notas) / len(notas), 2)
        if num_avaliadores == 1:
            metodo = 'UNICO'
        else:
            metodo = 'CONSENSO'
        quorum = f"{num_avaliadores}/3"  # exemplo: 1/3, 2/3, 3/3
        resultado[nome] = {
            'aluno': nome,
            'nota_final': media,
            'metodo': metodo,
            'quorum': quorum
        }
    return resultado

def gerar_arquivos_saida(resultado: Dict[str, dict], diretorio_saida: str = 'output'):
    """Gera um arquivo JSON por aluno no diretório de saída.
    """
    os.makedirs(diretorio_saida, exist_ok=True)
    for nome, dados in resultado.items():
        nome_arquivo = f"diagnostico_{nome.replace(' ', '_')}.json"
        caminho = os.path.join(diretorio_saida, nome_arquivo)
        with open(caminho, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        logging.info(f"Arquivo gerado: {caminho}")

def main():
    """Ponto de entrada: varre data/*.txt, processa e gera saída.
    """
    arquivos = glob.glob(os.path.join('data', '*.txt'))
    if not arquivos:
        logging.warning("Nenhum arquivo .txt encontrado em data/")
        return

    todas_avaliacoes = []
    for arquivo in arquivos:
        logging.info(f"Processando arquivo: {arquivo}")
        avaliacoes = parse_file(arquivo)
        todas_avaliacoes.extend(avaliacoes)

    if not todas_avaliacoes:
        logging.warning("Nenhuma avaliação encontrada nos arquivos.")
        return

    resultado = consolidar_alunos(todas_avaliacoes)
    gerar_arquivos_saida(resultado)

if __name__ == '__main__':
    main()