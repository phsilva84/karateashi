
Fase 08 — Pipeline v2.0: OMR + Engine + DistribuiçãoProjeto: Karate-Ashi
Responsável: Paulo Silva
Período: 14/09/2026
Status: Concluída — run validado1. ObjetivoSubstituir o pipeline v1.1 (mail.yml) por um orquestrador único (.github/workflows/pipeline.yml) responsável por sincronizar a entrada do Drive, processar os exames (OMR + engine) e distribuir os relatórios — com idempotência por estado e acesso restrito à pasta do projeto.2. Entregas2.1 Workflow — .github/workflows/pipeline.ymlTrês jobs sequenciais:
sincronizar-entrada — baixa cadastro e gabaritos do Drive para data/
processar-exame — executa OMR + engine e gera os relatórios em 3 camadas
distribuir — envia por Telegram e grava o estado
2.2 Código
core/pipeline.py — orquestrador (varredura, agrupamento, cálculo, relatórios)
core/notifications.py — distribuição e idempotência
core/omr_reader.py — leitura das folhas de exame
core/engine.py / core/parser.py — motor de cálculo e parser TXT
config/canais.json — mapeamento dojo → canal de Telegram
2.3 Correções aplicadas na revisão da fase
A faixa deixou de ser hardcoded: agora vem do QR (dados["aluno"]["faixa_atual"]), com FAIXA_FALLBACK = "branca" apenas como contingência
Relatórios gerados por Dojo — evita vazamento de dados entre unidades
data/cadastro/ fornece o mapeamento aluno_id → dojo_id para o roteamento
Agrupamento das avaliações por aluno.id
3. Autenticação e acesso ao Drive3.1 Runbook executado
Criar projeto e client OAuth no Google Cloud — tipo Externo (conta Gmail não aceita "Interno", que exige Google Workspace)
Hospedar a política de privacidade em GitHub Pages
Preencher a aba Branding (nome do app, e-mail de suporte, URL da política)
Verificar o domínio no Search Console (Prefixo de URL + arquivo HTML ou meta tag)
Publicar o app → sai de Testing para In production; o refresh_token deixa de expirar em 7 dias
Rodar rclone config com client_id e client_secret próprios
Definir o root_folder_id da pasta do projeto
3.2 Artefatos gerados

ItemValorRepositório da políticagithub.com/phsilva84/karate-ashi-docsURL públicahttps://phsilva84.github.io/karate-ashi-docs/Remote rclonegdrive: (type drive, client próprio)Secret no GitHubRCLONE_CONF (base64 do rclone.conf)Pasta raiz do remote1aFwAcB7bC7sy2VZs27cpAllE7-ZvcS23 (KarateAshi_Exames)3.3 Armadilhas encontradas (registro para reuso)
O botão Publicar app só libera após concluir a aba Branding
Domínios usados no Branding precisam estar verificados no Search Console
github.com não pode ser verificado pelo usuário → deve ser removido do Branding
O rclone config interativo não preserva root_folder_id (Enter no prompt) → precisa ser definido explicitamente
O client compartilhado do rclone será aposentado em 2026 — daí a necessidade do client próprio
4. Segurança — menor privilégio
root_folder_id aponta para documentos/KarateAshi_Exames, não para a raiz do Drive pessoal
Confirmado por rclone lsd gdrive:, que passou a listar apenas o conteúdo do projeto
O token do CI não enxerga documentos pessoais (fiscais, extratos, etc.)
5. Estrutura no DriveCódigogdrive:  (= KarateAshi_Exames)
├── pre_exame/        (existente)
├── gabaritos/        (entrada OMR — imagens das folhas)
├── cadastro/         (alunos.json — aluno_id → dojo_id)
└── estado/           (.ka-notify-state.json — idempotência)As pastas de destino (Dojo01/, Mestres/) são criadas automaticamente pelo rclone copy.6. Validação
Run de 14/09/2026: os 3 jobs concluídos sem erro
RCLONE_CONF decodificado corretamente dentro do runner
Acesso ao Drive escopado e funcional
7. Pendências
 config/canais.json — preencher os telegram_chat_id reais (hoje placeholder) via @userinfobot
 Teste com dado real: subir folha em gdrive:gabaritos/ + alunos.json em gdrive:cadastro/ e disparar workflow_dispatch
 Idempotência em produção: persistir .ka-notify-state.json em gdrive:estado/ (hoje o runner é efêmero e o estado não sobrevive entre execuções)
 GDRIVE_TOKEN do mail.yml — atualizar com o token novo antes da aposentadoria do client compartilhado
 Limpeza pós-teste: remover dados fictícios de gabaritos/, cadastro/ e estado/
 Paridade v1.1 ↔ v2.0 antes do corte definitivo
8. Descomissionamento do v1.1 (mail.yml)
Situação: redundante — o v2.0 cobre sincronização, processamento e distribuição
Preservar do legado: regras A1–A12, formato dos relatórios, canais.json e o histórico no Drive
Estratégia: rodar em paralelo → validar paridade de resultados → cortar → remover o secret GDRIVE_TOKEN
9. Contratos de entrada (referência)

FaseFormato de entradaPonto de validação04 (v1.1)TXT legado (Avaliador / Faixa / Nome / cod:)core/parser.py + core/engine.py08 (v2.0)Imagens OMR (QR) + cadastro.jsoncore/pipeline.py + core/omr_reader.pyPonte entre as fases: o v2.0 mantém fallback TXT, mas lê exclusivamente data/input.txt.
