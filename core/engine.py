import json
import os
import sys
import re

def parse_txt(filepath):
    students = []
    current = None
    pattern_nome = re.compile(r'^Nome do aluno:\s*(.+)', re.IGNORECASE)
    pattern_nota = re.compile(r'^(Kihon|Kata|Bunkai|Kumite):\s*(\d+(?:\.\d+)?)', re.IGNORECASE)

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            m_nome = pattern_nome.match(line)
            if m_nome:
                if current is not None:
                    students.append(current)
                current = {'aluno': m_nome.group(1).strip(),
                           'Kihon': None, 'Kata': None,
                           'Bunkai': None, 'Kumite': None}
                continue

            if current is not None:
                m_nota = pattern_nota.match(line)
                if m_nota:
                    key = m_nota.group(1).capitalize()  # ensure correct case
                    current[key] = float(m_nota.group(2))

    if current is not None:
        students.append(current)

    return students

def calcular_nota_final(aluno):
    # Pesos oficiais (exemplo: iguais)
    pesos = {'Kihon': 0.25, 'Kata': 0.25, 'Bunkai': 0.25, 'Kumite': 0.25}
    total = 0.0
    erros = []

    for componente, peso in pesos.items():
        valor = aluno.get(componente)
        if valor is None:
            erros.append(f'{componente} não encontrado')
        else:
            total += valor * peso

    if erros:
        # Se faltar algum componente, nota fica 0 ou parcial?
        # Vamos atribuir 0 para componentes faltantes (já tratado)
        pass

    nota_base100 = total  # soma ponderada, base 100
    nota_final = nota_base100 / 10.0  # converter para base 10
    nota_final = min(nota_final, 10.0)  # teto de 10.0

    # Tendência simplificada
    if nota_final >= 8.0:
        tendencia = 'positiva'
    elif nota_final >= 5.0:
        tendencia = 'neutra'
    else:
        tendencia = 'negativa'

    return {
        'aluno': aluno['aluno'],
        'nota_final': round(nota_final, 2),
        'detalhes_erros': erros,
        'tendencia': tendencia
    }

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'input.txt'
    output_dir = 'output'
    output_file = os.path.join(output_dir, 'diagnostico.json')

    alunos = parse_txt(input_file)
    resultados = [calcular_nota_final(a) for a in alunos]

    os.makedirs(output_dir, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    print(f'LOG: Processados {len(alunos)} alunos.')

if __name__ == '__main__':
    main()