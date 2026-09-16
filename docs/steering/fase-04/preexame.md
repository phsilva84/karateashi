
FASE 04 — Pré-exame: Geração de Folhas PDF com QR CodeVersão: v2col-4.0 (consolida v2col-2.8 → 2.9 → 3.0 → 4.0)
Data: 16/09/2026
Status: Implementada e coberta por testes; leitura de campo em validação com o novo lote de folhas0. PERSONA E ESPECIALIDADES — ASSUMIR AUTOMATICAMENTE
Dev Python Sênior — CLI, CSV, integração de bibliotecas.
Designer de Formulário A4 — layout limpo, elementos bem distribuídos, instrução no rodapé.
Analista Pedagógico de Karatê — estrutura do gabarito (4 quesitos, 7 checkboxes, observação).
Especialista em Visão Computacional (OMR) — leitura de checkboxes, QR e alinhamento por âncora. [ATUALIZADO]
Regras de conduta: use SEMPRE o padrão de payload definido abaixo; nunca invente campos; se algo não estiver especificado, PERGUNTE antes de assumir; ao final, preencha o checklist.1. ObjetivoAntes do exame, o Sensei responsável prepara a lista de alunos. O script gera as folhas prontas para imprimir. O QR elimina a leitura de nome manuscrito: o OMR (Fase 03) lê o QR para identificar aluno, avaliador, dojo, exame e faixa. O cadastro inicial fica persistido e não precisa ser refeito nas próximas avaliações.[ATUALIZADO] A Fase 04 passou a cobrir também: a observação estruturada (antes escrita livre), as contradições de observação, a robustez de leitura das folhas, a segunda camada de entrada (scanner) e o ciclo de vida do aluno (promoção de faixa).O princípio que governa a fase é o "princípio dos gêmeos": a folha (desenhada pelo tools/pre_exame.py) e o relatório (montado pelo sistema) consomem o mesmo vocabulário e a mesma geometria. Nenhuma transcrição manual entra no fluxo.2. Contexto mínimo do projeto
Entrada: CSV de alunos (id,nome,faixa_atual,faixa_pretendida,dojo_id).
Saída: PDFs de folhas (um por avaliador) + config/coordenadas/<faixa></faixa>.json com a geometria real desenhada.
Cadastro: data/cadastro/alunos.json — estado atual do aluno, com histórico de promoções embutido. [ATUALIZADO]
Leitura: core/omr_reader.py (Fase 03) lê as ROIs na mesma geometria gravada aqui.
Entrada de imagens: fotos de celular ou folhas digitalizadas (scanner). [ATUALIZADO]
3. Decisões aprovadas (não reabrir)
CSV de entrada com colunas: id,nome,faixa_atual,faixa_pretendida,dojo_id.
Exame ID único por Dojo: EXA-<DOJO_ID>-<ANO></ano>-<EDICAO></edicao> (ex: EXA-D01-2026-02).
Cadastro: merge no alunos.json, novos alunos com "novo": true; não duplicar os existentes.
Folha A4 vertical, 1 aluno por folha; QR no canto superior direito; rodapé com instrução "Como marcar".
Dependências: qrcode[pil], reportlab.
[ATUALIZADO] — decisões acrescentadas:
Layout em DUAS COLUNAS: esquerda = Kihon + Kata; direita = Bunkai + Kumite. Cada quesito com seus critérios e 7 checkboxes.
Observações estruturadas (16 opções, sem campo "Outro"): coluna "Ótimo!" (obs_p1..p8) e "A Melhorar" (obs_m1..m8), no rodapé, uniformes para todas as faixas.
Vocabulário único: vive em core/observacoes.py e é importado pelo pre_exame.py — folha e relatório nunca divergem.
Coordenadas em mm: o pre_exame.py grava config/coordenadas/<faixa></faixa>.json com a posição real de cada linha e de cada checkbox de observação. O OMR lê a mesma geometria.
Marcadores fiduciais em 3 cantos (TL, BR, BL) — o QR no canto superior direito é a 4ª referência. [CORRIGIDO] (o MD original dizia "4 cantos", mas o código sempre desenhou 3 + QR).
Faixa no QR = faixa_atual (a faixa que a folha avalia). [CORRIGIDO] — o código de referência original usava faixa_pretendida, o que divergia do cabeçalho da folha e quebrava a validação cruzada do OMR.
Elegibilidade: só gera folha para aluno ativo e com faixa_pretendida preenchida (regra em core/cadastro.py).
Contradições: par "Ótimo!"/"A melhorar" oposto do mesmo avaliador é anulado e registrado para o mestre.
Entrada dupla: fotos ou scanner, com ingestão unificada.
4. Tarefas
 Criar tools/pre_exame.py (multi-faixa, duas colunas, observações estruturadas).
 Criar data/exemplo_alunos_exame.csv com alunos de exemplo.
 Rodar o script com --dry-run e depois gerar um lote de teste.
 Verificar com um leitor de QR que o payload decodificado confere.
 Gravar config/coordenadas/<faixa></faixa>.json com a geometria real.
 Implementar observações estruturadas (v2col-2.8).
 Implementar robustez de leitura: âncora QR + fiduciais (v2col-2.9).
 Implementar contradições de observação (v2col-3.0).
 Implementar camada de scanner e ciclo de vida do aluno (v2col-4.0).
 Registrar no Status.
 Ampliar FAIXAS_SUPORTADAS para roxa/marrom/preta. [PENDENTE]
 Regerar as folhas com o vocabulário atual e validar o lote novo. [EM ANDAMENTO]
5. Código de referência[ATUALIZADO] O código de referência original (single-column, observação livre, QR com faixa_pretendida) foi substituído pelos arquivos reais do projeto. O contrato que o MD deve fixar é:Payload do QR (inalterado):KA|DOJO|EXAME|ALUNO|SENSEI|FAIXA
FAIXA = faixa_atual, sem acentos, em maiúsculas.
Constantes de geometria (fixas no código):Código12345678910111213COLUNAS = [("esquerda", 15.0, ["kihon", "kata"]),
           ("direita", 107.0, ["bunkai", "kumite"])]
CHECKBOX_X_OFFSET_MM = 46.0
CHECKBOX_PASSO_MM = 5.5
CHECKBOX_LADO_MM = 4.0
CHECKBOX_QTD = 7
OBS_COL_X_MM = [15.0, 107.0]
OBS_CHK_LADO_MM = 4.5
OBS_LINHA_MM = 6.5
QR_LADO_MM = 22.0
QR_MARGEM_MM = 10.0
LINHA_MM = 8.5
MAX_CRITERIOS_BLOCO = 8Arquivos de referência (fonte de verdade):

ArquivoPapeltools/pre_exame.pyGera folhas + grava coordenadascore/observacoes.pyVocabulário oficial (fonte única)core/contradicoes.pyRegra de contradiçãocore/cadastro.pyCiclo de vida e elegibilidadecore/omr_reader.pyLeitura OMR (foto + scanner)tools/promover_alunos.pyPromoção pós-exametools/ingest_folhas.pyIngestão unificada scanner/fotos6. Critérios de aceite
CSV de exemplo lido sem erro; cadastro atualizado sem duplicar existentes.
PDF gerado por avaliador com uma folha por aluno.
Folha A4 contém: 4 quesitos, seus critérios com 7 checkboxes, cabeçalho e rodapé com instrução.
Arquivos .png temporários do QR gerados em pasta temp e removidos ao final.
[ATUALIZADO] — critérios acrescentados:
Folha contém a seção de observações estruturadas (16 opções, duas colunas).
config/coordenadas/<faixa></faixa>.json gravado com a geometria real (mm).
QR decodifica o payload com a faixa correta (faixa_atual).
Aluno ativo: false ou sem faixa_pretendida não gera folha.
O merge do cadastro preserva ativo, ultima_promocao e historico_promocoes.
--dry-run lista o plano sem gravar cadastro nem PDFs.
7. StatusConcluída (v2col-4.0) — implementada e coberta por testes (157 verdes, 91% de cobertura). Leitura de campo em validação com o novo lote de folhas.8. Observações estruturadas (v2col-2.8)A observação nasce na folha como checkboxes, uniformes para todas as faixas. Sem limite de marcações, sem campo "Outro", ICR (manuscrito) descartado por acurácia.Coluna "Ótimo!" (obs_p1..obs_p8):

ChaveTextoobs_p1Boa execução técnicaobs_p2Ótima base / posturaobs_p3Bom controle de distância (era "Chutes firmes")obs_p4Boa concentração / focoobs_p5Ótima execução do Bunkai (era "Bom controle e defesa")obs_p6Combate técnico / ágilobs_p7Ótima Execução do Kataobs_p8Ótima execução de KihonsColuna "A Melhorar" (obs_m1..obs_m8):

ChaveTextoobs_m1Melhorar bases / posturaobs_m2Dificuldade nas Transições de Basesobs_m3Falta kiai (usar mais o kiai)obs_m4Falta foco / olhar nas técnicasobs_m5Mais carga nos golpesobs_m6Erros Técnicos Constantesobs_m7Execução Incorreta do Kataobs_m8Dificuldade na execução de KihonsLeitura pelo OMR — o JSON do aluno ganha:Código12345{
  "observacoes_marcadas": ["obs_p1", "obs_m3"],
  "observacoes_lidas_brutas": ["obs_p1", "obs_p7", "obs_m7", "obs_m3"],
  "observacao_montada": "Ótimo! Boa execução técnica. A melhorar: Falta kiai (usar mais o kiai)"
}observacoes_lidas_brutas guarda a leitura antes da anulação (rastreabilidade).9. Contradições de observação (v2col-3.0)O mesmo avaliador (uma folha) não pode marcar o par contraditório: um "Ótimo!" e o "A melhorar" oposto. Quando marca, as duas são anuladas e a contradição é registrada no relatório geral para o mestre refinar com o avaliador.Pares (data-driven — config/observacoes_contradicoes.json):

TópicoÓtimoA melhorarexecução técnicaobs_p1obs_m6bases / posturaobs_p2obs_m1foco / olharobs_p4obs_m4kataobs_p7obs_m7kihonobs_p8obs_m8A detecção roda antes do merge_no_json, para o texto montado já sair sem as anuladas. O campo contradicoes_observacoes alimenta o relatório geral.10. Robustez de leitura (v2col-2.9)
O QR é decodificado primeiro na imagem original — se o recorte de perspectiva sair errado, o QR cru ainda é lido.
Detecção da folha testa três binarizações (Otsu, Otsu invertido, Canny) e valida borda e retangularidade.
Fallback de âncora: quando o contorno falha (folha cortada, fundo claro), o QR + 3 cruzes de registro estimam a homografia e fazem o warp direto.
O template da cruz foi corrigido para polaridade correta (cruz preta em fundo branco) — antes, com polaridade invertida, o refino por fiduciais nunca atuava.
Guardas: folha cortada (área preta > 15%) recusada; coordenadas não calibradas (x=0, y=0) rejeitadas; validação cruzada de faixa (QR × layout).
11. Camada de scanner (v2col-4.0)

OrigemComportamentofotoDetecção de contorno + fallback por âncorascannerPágina já plana; usa âncora QR/fiduciais quando localizável (corrige inclinação de ADF); senão assume que a imagem É a páginaautoHeurística _parece_scanner decide (proporção A4 + borda clara)A guarda de "folha cortada" só se aplica ao caminho de foto. A --faixa é opcional: sem ela, a faixa vem do QR — o que permite lote misto.12. Ciclo de vida do aluno (v2col-4.0)Cadastro (data/cadastro/alunos.json) — estado atual + histórico:

CampoFunçãoid, nome, dojo_idIdentidadefaixa_atualFaixa hoje — define o layout da folhafaixa_pretendidaAlvo do próximo exame (vazio = não examina)novoPrimeira avaliação no sistemaativofalse = fora do dojo (não gera folha; mantém histórico)ultima_promocaoData ISO da última promoçãohistorico_promocoesLista append-onlyOrdem de faixas (config/faixas.json):{ "ordem": ["Branca", "Amarela", "Laranja", "Verde", "Azul", "Roxa", "Marrom", "Preta"] }Promoção (tools/promover_alunos.py): a faixa nova é sempre a faixa_pretendida; só promove status aprovado; valida que a pretendida é a próxima na ordem (--permitir-pulo libera); idempotente por (aluno_id, exame_id); faixa terminal registra conclusão; dry-run por padrão, grava só com --aplicar (backup .bak).13. Ingestão unificada e Google Drivetools/ingest_folhas.py roteia por pasta (scanner → scanner; foto/fotos → foto), expande PDF/TIFF multipágina (uma página = uma folha), lê a faixa do QR e move os originais para o arquivo.Arquitetura de acesso — dois Drives Compartilhados (única forma de garantir que "Colaborador" não veja os relatórios):

PastaSenseiMestreDrive A / entrada/**ColaboradorGerenteDrive B / imagens/**sem acessoGerenteDrive B / processados/**sem acessoGerenteDrive B / relatorios/**sem acessoGerenteO config/diretorios.json centraliza os caminhos.14. Ferramentas e módulos

ArtefatoPapelcore/observacoes.pyVocabulário oficial + montagem do textocore/contradicoes.pyRegra de contradição (detectar, consolidar)core/cadastro.pyCiclo de vida, elegibilidade, ordem de faixascore/omr_reader.pyLeitura OMR (foto + scanner + âncora + contradições)tools/pre_exame.pyGera folhas + grava coordenadastools/promover_alunos.pyPromoção pós-exametools/ingest_folhas.pyIngestão unificada scanner/fotostools/calibrar_observacoes.pyMede deslocamento/escala das ROIstools/comparar_json.pyCompara lotes de JSON do OMRtools/diagnostico_rois.pySobrepõe ROIs na folha alinhadaconfig/observacoes_contradicoes.jsonPares contraditóriosconfig/faixas.jsonOrdem canônica das faixasconfig/diretorios.jsonCaminhos dos Drives15. Testes e cobertura
tests/test_omr_robustez.py — variantes de QR, âncora QR/fiduciais, guardas, pipeline e caminhos de erro.
tests/test_contradicoes.py — anulação do par, preservação do solto, carregar_pares, consolidar.
CI: pytest tests/ -q --cov=core.omr_reader --cov-fail-under=80.
Estado atual: 157 testes verdes, 91% de cobertura.
16. Diagnósticos de campo
Vocabulário dessincronizado (causa raiz encontrada). As folhas impressas usavam uma geração antiga do vocabulário (obs_p3 = "Chutes firmes", obs_p5 = "Bom controle e defesa"). O código já os renomeou — divergência de interpretação (mesma caixa, texto novo).
Bloco de observações fora de escala. O calibrador mediu passo de ~5,74 mm contra 6,50 mm do config (~12% de compressão) na seção de observações, com os critérios OK — consistente com folha de outra geração, não com falha de warp.
Amplificação por anulação. Se a leitura estiver errada, a regra de contradição pode anular observação válida (ex.: A07 ficou vazia). Mitigado por observacoes_lidas_brutas.
Correção aplicada: regerar as folhas com o pre_exame atual (resolve vocabulário e calibração de uma vez).
17. Pendências e decisões abertas
Mapeamento chave → código A ausente. O OMR lê por chave (base_incorreta), o motor usa A1–A12. Falta o config/codigos_tecnicos.json ligando chave → A-código → peso → recomendação.
falta_combatividade sem A-código, e A9/A12 sem chave na folha — vocabulário folha × motor precisa reconciliar.
Conversão OMR → motor. O motor espera .txt; o OMR gera JSON. Falta o extrator output/json → relatorio_consolidado_*.json.
Tabela de pesos: config.py (v2.0, A10=2.5) × contexto v1.1 (A10=12.0) — confirmar a oficial.
FAIXAS_SUPORTADAS hoje = branca..azul; ampliar para roxa/marrom/preta.
18. ChangelogCódigov2col-2.8  observações estruturadas (16 opções, sem "Outro")
v2col-2.9  âncora QR+fiduciais; guarda de folha cortada; template da cruz
v2col-3.0  contradições (anular pares; campo contradicoes_observacoes)
v2col-4.0  camada scanner; ciclo de vida do aluno; ingestão unificada; DriveResumindo
O MD foi atualizado preservando a estrutura original (seções 0–7) e acrescentando as seções 8–18 com tudo o que construímos.
Duas correções ficaram registradas: os fiduciais são 3 cantos + QR (não 4), e o QR carrega faixa_atual (não faixa_pretendida).
As pendências críticas ficaram explícitas: mapeamento chave → A-código, falta_combatividade sem código, extrator JSON → consolidado, e a tabela de pesos a confirmar.
