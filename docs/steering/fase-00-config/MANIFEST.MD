
FASE 00 — Configuração Base do Sistema0. PERSONA E ESPECIALIDADES — ASSUMIR AUTOMATICAMENTEVocê atua como uma equipe de 3 especialistas:
Modelador de Dados — JSON limpo, chaves consistentes, sem redundância.
Analista Pedagógico de Karatê — domínio de Kihon, Kata, Bunkai e Kumite; conhece a ética marcial.
Revisor Didático — explica em linguagem simples, para quem não programa.
Regras de conduta:
Use SEMPRE os valores da especificação v2.0 (abaixo). Nunca invente pesos ou critérios.
Se algo não estiver especificado, PERGUNTE antes de assumir.
Ao final, preencha o checklist de aceite.

1. ObjetivoCriar os arquivos de configuração do sistema. Todos os pesos, critérios e regras ficam aqui — nunca embutidos no código. Mudar um peso passa a ser editar um JSON, não o motor.2. Contexto mínimo do projetoO Karate-Ashi é um sistema Python que processa exames de Karatê. Há 4 quesitos (Kihon, Kata, Bunkai, Kumite), cada um valendo 25,0 pontos. Cada quesito tem critérios próprios; a avaliação registra a frequência de cada falha (0 a 7 marcações). O cálculo final usa média entre avaliadores + desconto progressivo. O resultado é enviado ao Telegram e sincronizado no Google Drive.3. Decisões aprovadas (não reabrir)
   A9 (Defesa Incompleta) e A12 (Tensão/Respiração) removidos.
   Códigos são relativos ao quesito (o código 1 muda de significado conforme o quesito).
   Falta de Controle só existe em Bunkai e Kumite (trava de segurança).
   Multiplicadores progressivos: 1,0 / 1,5 / 2,0 / 2,5.
   Piso de nota por quesito: 0,0.
   Status: Aprovado ≥ 70,0 · Recuperação 60,0–69,9 · Reprovado < 60,0.
2. Tarefas
   Criar config/criterios_por_quesito.json
   Criar config/regras_gerais.json
   Criar config/omr_thresholds.json
   Validar que os 3 arquivos são JSON válidos
3. Conteúdo dos arquivos

config/criterios_por_quesito.json

{
  "versao_schema": "2.0.0",
  "quesitos": {
    "kihon": {
      "nome": "Kihon", "pontos_base": 25.0,
      "criterios": [
        {"codigo": 1, "chave": "base_incorreta", "nome": "Base Incorreta", "peso": 1.0},
        {"codigo": 2, "chave": "execucao_tecnica_incorreta", "nome": "Execução Técnica Incorreta", "peso": 1.0},
        {"codigo": 3, "chave": "movimento_sem_carga", "nome": "Movimento sem Carga/Peso", "peso": 1.0},
        {"codigo": 4, "chave": "falta_foco", "nome": "Falta de Foco", "peso": 1.0},
        {"codigo": 5, "chave": "perda_equilibrio", "nome": "Perda de Equilíbrio", "peso": 1.0},
        {"codigo": 6, "chave": "ausencia_kiai", "nome": "Ausência de Kiai", "peso": 0.5}
      ]
    },
    "kata": {
      "nome": "Kata", "pontos_base": 25.0,
      "criterios": [
        {"codigo": 1, "chave": "embusen_incorreto", "nome": "Embusen Incorreto", "peso": 2.0},
        {"codigo": 2, "chave": "base_incorreta", "nome": "Base Incorreta", "peso": 1.0},
        {"codigo": 3, "chave": "falta_ritmo", "nome": "Falta de Ritmo", "peso": 0.5},
        {"codigo": 4, "chave": "ausencia_kiai", "nome": "Ausência de Kiai", "peso": 0.5},
        {"codigo": 5, "chave": "execucao_tecnica_incorreta", "nome": "Execução Técnica Incorreta", "peso": 1.0},
        {"codigo": 6, "chave": "movimento_sem_carga", "nome": "Movimento sem Carga/Peso", "peso": 1.0},
        {"codigo": 7, "chave": "falta_foco", "nome": "Falta de Foco", "peso": 1.0},
        {"codigo": 8, "chave": "perda_equilibrio", "nome": "Perda de Equilíbrio", "peso": 1.0}
      ]
    },
    "bunkai": {
      "nome": "Bunkai", "pontos_base": 25.0,
      "criterios": [
        {"codigo": 1, "chave": "base_incorreta", "nome": "Base Incorreta", "peso": 1.0},
        {"codigo": 2, "chave": "ausencia_kiai", "nome": "Ausência de Kiai", "peso": 0.5},
        {"codigo": 3, "chave": "execucao_tecnica_incorreta", "nome": "Execução Técnica Incorreta", "peso": 1.0},
        {"codigo": 4, "chave": "movimento_sem_carga", "nome": "Movimento sem Carga/Peso", "peso": 1.0},
        {"codigo": 5, "chave": "falta_foco", "nome": "Falta de Foco", "peso": 1.0},
        {"codigo": 6, "chave": "perda_equilibrio", "nome": "Perda de Equilíbrio", "peso": 1.0},
        {"codigo": 7, "chave": "distancia_inadequada", "nome": "Distância Inadequada", "peso": 1.0},
        {"codigo": 8, "chave": "falta_controle", "nome": "Falta de Controle / Risco", "peso": 2.5}
      ]
    },
    "kumite": {
      "nome": "Kumite", "pontos_base": 25.0,
      "criterios": [
        {"codigo": 1, "chave": "movimento_sem_carga", "nome": "Movimento sem Carga/Peso", "peso": 1.0},
        {"codigo": 2, "chave": "falta_foco", "nome": "Falta de Foco", "peso": 1.0},
        {"codigo": 3, "chave": "perda_equilibrio", "nome": "Perda de Equilíbrio", "peso": 1.0},
        {"codigo": 4, "chave": "ausencia_kiai", "nome": "Ausência de Kiai", "peso": 0.5},
        {"codigo": 5, "chave": "distancia_inadequada", "nome": "Distância Inadequada", "peso": 1.0},
        {"codigo": 6, "chave": "falta_combatividade", "nome": "Falta de Combatividade", "peso": 2.0},
        {"codigo": 7, "chave": "falta_controle", "nome": "Falta de Controle / Risco", "peso": 2.5}
      ]
    }
  }
}



config/regras_gerais.json


{
  "versao_schema": "2.0.0",
  "progressivo": [
    {"fc_min": 0.1, "fc_max": 1.0, "multiplicador": 1.0},
    {"fc_min": 1.1, "fc_max": 2.5, "multiplicador": 1.5},
    {"fc_min": 2.6, "fc_max": 4.5, "multiplicador": 2.0},
    {"fc_min": 4.6, "fc_max": 7.0, "multiplicador": 2.5}
  ],
  "piso_quesito": 0.0,
  "status": {"aprovado_min": 70.0, "recuperacao_min": 60.0},
  "trava_seguranca": {
    "quesitos": ["bunkai", "kumite"],
    "criterio": "falta_controle",
    "teto": 10.0,
    "regra": "consenso_total"
  },
  "elogios": {"destaque_geral_min": 85.0, "criterio_transversal_min_quesitos": 2},
  "recorrencia": {"dojo_atencao": 0.50, "dojo_maxima": 0.80, "master_global": 0.50}
}



config/omr_thresholds.json


{
  "versao_calibracao": "2.0.0-inicial",
  "limiar_vazio_max": 0.20,
  "limiar_suspeito_max": 0.40,
  "resolucao_minima_dpi": 300,
  "max_marcacoes_por_criterio": 7
}



6. Critérios de aceite
   Os 3 arquivos existem em config/
   Pesos conferem item a item com a especificação v2.0
   Contagem correta: Kihon 6 · Kata 8 · Bunkai 8 · Kumite 7 critérios
   falta_controle aparece apenas em Bunkai e Kumite
   Os 3 arquivos são JSON válidos (parse sem erro)
7. Status
   Pendente · [ ] Em execução · [ ] Concluída (data: ___)
   FIM DO ARQUIVO
