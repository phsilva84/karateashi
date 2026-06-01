import os
import json
import logging
from typing import List, Dict, Any, Tuple

# Configure logging (SRE padrão)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Tabela v1.1 de pesos para erros em cada quesito
PESOS = {
    'kihon': {'falha_tecnica': 0.5, 'desequilibrio': 0.3, 'postura': 0.2},
    'kata': {'ritmo': 0.4, 'embusen': 0.35, 'kime': 0.25},
    'bunkai': {'aplicacao': 0.5, 'sincronia': 0.3, 'realismo': 0.2},
    'kumite': {'distancia': 0.4, 'reacao': 0.35, 'finalizacao': 0.25}
}
A10_CEILING = 10.0  # Teto máximo para a nota final consolidada

class Consolidador:
    """Estratégias de consolidação de notas."""

    @staticmethod
    def consolidar(notas: List[float], metodo: str) -> float:
        """
        Consolida uma lista de notas conforme o método.
        - UNICO: retorna a única nota (base 100)
        - CONSENSO: média aritmética das notas
        """
        if metodo == 'UNICO':
            if len(notas) != 1:
                raise ValueError("Método UNICO requer exatamente 1 nota")
            return min(notas[0], 100.0)  # garante teto 100
        elif metodo == 'CONSENSO':
            if len(notas) < 2 or len(notas) > 3:
                raise ValueError("Método CONSENSO requer 2 ou 3 notas")
            media = sum(notas) / len(notas)
            return min(media, 100.0)
        else:
            raise ValueError(f"Método desconhecido: {metodo}")

def detectar_metodo(notas_por_aluno: Dict[str, List[float]]) -> str:
    """Determina o método de consolidação baseado no número de avaliadores."""
    num_notas = len(notas_por_aluno.get('avaliadores', []))
    if num_notas == 1:
        return 'UNICO'
    else:
        return 'CONSENSO'

def calcular_nota_por_quesito(erros: Dict[str, Dict[str, float]], quesito: str) -> float:
    """
    Calcula a nota de um quesito partindo de 25.0 e subtraindo erros ponderados.
    erros: dict com tipo_erro -> valor para cada quesito
    """
    try:
        peso_quesito = PESOS[quesito]
        total_deducao = 0.0
        for tipo_erro, valor in erros.get(quesito, {}).items():
            peso = peso_quesito.get(tipo_erro, 0.0)
            total_deducao += peso * valor
        return max(0.0, 25.0 - total_deducao)
    except KeyError as e:
        logger.error(f"Quesito desconhecido: {e}")
        return 0.0

def parse_exame_file(path: str) -> List[Dict[str, Any]]:
    """
    Varre a pasta 'data/' por arquivos .txt e agrupa dados por aluno e avaliador.
    Retorna lista de alunos com suas respectivas notas e metadados.
    Expectativa de formato por linha (exemplo):
        Aluno: Joao Silva | Avaliador: Maria | Kihon_falha_tecnica: 1.5 | Kihon_desequilibrio: 0.8 | Kata_ritmo: 0.3 | ...
    """
    logger.info(f"Processando arquivo: {path}")
    alunos_data = {}  # nome_aluno -> {avaliadores: [nomes], erros_por_avaliador: [{quesito->{tipo:valor}}]}

    with open(path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            # Parsing simples: assume chave: valor separado por '|'
            partes = [p.strip() for p in line.split('|') if p.strip()]
            if not partes:
                continue

            dados = {}
            for parte in partes:
                if ':' in parte:
                    chave, valor = parte.split(':', 1)
                    dados[chave.strip().lower()] = valor.strip()

            nome_aluno = dados.get('aluno')
            nome_avaliador = dados.get('avaliador')
            if not nome_aluno or not nome_avaliador:
                logger.warning(f"Linha {line_num}: ignorada sem aluno ou avaliador.")
                continue

            # Extrai erros por quesito
            erros_avaliador = {'kihon': {}, 'kata': {}, 'bunkai': {}, 'kumite': {}}
            for chave, valor_str in dados.items():
                match = re.match(r'^(kihon|kata|bunkai|kumite)_(.+)$', chave)
                if match:
                    quesito = match.group(1)
                    tipo_erro = match.group(2).lower()
                    try:
                        valor = float(valor_str)
                    except ValueError:
                        logger.error(f"Linha {line_num}: valor inválido para {chave}: {valor_str}")
                        continue
                    erros_avaliador[quesito][tipo_erro] = valor

            # Agrupa por aluno
            if nome_aluno not in alunos_data:
                alunos_data[nome_aluno] = {'avaliadores': [], 'erros_por_avaliador': []}
            alunos_data[nome_aluno]['avaliadores'].append(nome_avaliador)
            alunos_data[nome_aluno]['erros_por_avaliador'].append(erros_avaliador)

    # Converte para lista de dicionários com notas calculadas
    alunos = []
    for nome, data in alunos_data.items():
        notas_por_avaliador = []
        for erros in data['erros_por_avaliador']:
            # Calcula nota total (soma dos 4 quesitos, cada um máximo 25 -> base 100)
            nota_total = sum(calcular_nota_por_quesito(erros, q) for q in ['kihon','kata','bunkai','kumite'])
            # Aplica teto A10 se necessário (caso a nota exceda 100, cap para 100)
            nota_total = min(nota_total, 100.0)
            notas_por_avaliador.append(nota_total)

        metodo = detectar_metodo(data)
        # Nota final consolidada
        nota_final = Consolidador.consolidar(notas_por_avaliador, metodo)

        quorum = f"{len(data['avaliadores'])}/{len(data['avaliadores'])}"  # Ex: 2/2 ou 3/3; melhoraria para mostrar qtd máxima esperada?
        # Nota: quorum original pedido '2/3' indica 2 avaliadores de 3 possíveis. Mas como não sabemos o máximo, usamos presente/total.
        # Adicionamos campo 'total_avaliadores_esperado' se houver info, senão usamos len presente.
        total_esperado = len(data['avaliadores'])  # Por padrão, assume que todos os esperados estavam presentes
        quorum = f"{len(data['avaliadores'])}/{total_esperado}"

        alunos.append({
            'nome': nome,
            'notas_por_avaliador': notas_por_avaliador,
            'avaliadores': data['avaliadores'],
            'nota_final': round(nota_final, 2),
            'metodo': metodo,
            'quorum': quorum
        })
        logger.info(f"Aluno: {nome} | Notas: {notas_por_avaliador} | Método: {metodo} | Final: {nota_final:.2f}")

    return alunos

def consolidar_exame(filename: str, input_dir: str = 'data', output_dir: str = 'output'):
    """Wrapper para processar um arquivo e gerar o diagnóstico."""
    filepath = os.path.join(input_dir, filename)
    if not os.path.exists(filepath):
        logger.error(f"Arquivo não encontrado: {filepath}")
        return

    logger.info(f"Iniciando consolidação de {filename}")
    alunos = parse_exame_file(filepath)

    # Cria diretório de saída se não existir
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(filename)[0]
    output_path = os.path.join(output_dir, f'diagnostico_{base_name}.json')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(alunos, f, ensure_ascii=False, indent=2)

    logger.info(f"Diagnóstico salvo em: {output_path}")

if __name__ == '__main__':
    # Processa todos os arquivos .txt na pasta data/
    data_dir = 'data'
    if not os.path.isdir(data_dir):
        logger.error(f"Diretório 'data/' não encontrado.")
        exit(1)

    txt_files = [f for f in os.listdir(data_dir) if f.endswith('.txt')]
    if not txt_files:
        logger.warning("Nenhum arquivo .txt encontrado em data/.")
    else:
        for fname in txt_files:
            consolidar_exame(fname)