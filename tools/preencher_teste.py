# salve como tools/preencher_teste.py (cria a folha preenchida)
import json, sys
from pathlib import Path
import cv2
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import omr_reader

coords = json.loads(Path("output/pre_exame/EXA-D01-2026-10_S01_folha1_coordenadas.json").read_text(encoding="utf-8"))
img = cv2.imread("output/scans/folha_s01.png")
a4 = omr_reader.normalizar_a4(img)
cinza = omr_reader._cinza(a4)
es = omr_reader.A4_W_PX / omr_reader.A4_W_MM
jan = omr_reader.JANELA_MM * es

alvos = []
for al in coords["alunos"]:
    if al["id"] != "T01":
        continue
    alvos.append(al["presenca"])                                    # presença
    alvos.append(al["frequencias"]["kihon_base_incorreta"][1])      # freq 2
    alvos.append(al["observacoes"]["obs_p1"])                       # obs p1

for b in alvos:
    anel = omr_reader._achar_anel(cinza, b["x_mm"]*es, b["y_mm"]*es, b["r_mm"]*es, jan)
    if anel:
        cx, cy, r = (int(v) for v in anel)
        cv2.circle(a4, (cx, cy), max(int(r*0.55), 3), (0, 0, 0), -1)

cv2.imwrite("output/scans/folha_s01_preenchida.png", a4)
print("pronto: output/scans/folha_s01_preenchida.png")