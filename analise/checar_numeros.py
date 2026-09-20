"""Confere o deck contra o Livro de Números.

Extrai todo número dos slides (e das notas) do PPTX e verifica se ele existe no Livro
(valor formatado ou valor bruto arredondado). O que não tem lastro direto precisa estar
na lista DERIVADOS abaixo, com a conta que o produz. Também procura frases proibidas:
números de versões anteriores que não valem mais.

Uso:
    python checar_numeros.py Vertice_Deck_FINAL.pptx livro_de_numeros.csv
"""
import csv
import re
import sys
from pptx import Presentation

# Números que não são ID do Livro, mas saem de conta simples sobre IDs do Livro.
DERIVADOS = {
    '0,9': 'N13 − N12 (8,44% − 7,53%)', '0,46': 'N06 − N07 (margem dos aprovados, S1 → S2)',
    '0,47': 'M10_S1 − M10_S2', '0,09': 'M10_S1 − M10_S2sn', '2,73': 'N28 + N21 (1,39 + 1,34)',
    '2,49': 'N19 + N20 + N21', '2,62': 'soma das parcelas arredondadas do slide 2',
    '13,9': 'mínimo de SC_* − SR_*', '15,8': 'máximo de SC_* − SR_*', '14,5': 'M04',
    '38,6': 'mínimo de SR_*', '40,8': 'máximo de SR_*', '39,8': 'M03 arredondado',
    '7,55': 'DF_MR_pro em R$ mi', '54,4': 'N18 ÷ receita registrada (M02) arredondado',
    '53,1': 'DF_PCT_antes arredondado', '0,05': 'MX_s2_Marketplace − MX_s1_Marketplace',
    '0,68': 'MX_s2_TikTok − MX_s1_TikTok', '0,02': 'N31 − N32', '1,8': 'fator de encargos adotado (E08 = 1,81)',
    '287,1': 'DF_X_A em R$ mil', '45,7': 'DF_X_R em R$ mil', '15,7': 'DF_SOL_pro em R$ mil',
    '275,1': 'DF_Y1_desc em R$ mil', '43,8': 'DF_Y1_dev em R$ mil', '333,7': 'DF_RES_var em R$ mil',
    '225,7': 'DF_X_A − DF_X_R − DF_SOL_pro, em R$ mil', '39,50': 'escala do eixo (A7)', '40,00': 'escala do eixo (A7)',
    '41,00': 'escala do eixo (A7)', '40,80': 'N31 + CP_need', '65,5': 'média de N63 e N64', '100,00': 'salário-base = 100% (A6)',
    '0,00': 'vale-transporte = 0% (A6)', '27,8': 'INSS 20% + RAT 2% + terceiros 5,8% (A6)', '5,8': 'terceiros FPAS 515 (A6)',
    '4,8': 'teto do Simples, X04', '6.000': 'salário de referência (A6)',
}
# Referências legais do apêndice A6 (números de lei, não valores).
LEIS = {'4.090', '7.418', '8.036', '8.212'}
PROIBIDOS = ['1,18 mi', '2,48 mi', '25,2%', '7,36 mi', '1.184', '2.476', '7.356', 'troca', 'R$ 230,0 mil']

def pool_do_livro(caminho):
    pool = set()
    with open(caminho, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f, delimiter=';'):
            for n in re.findall(r'\d[\d\.]*,\d+|\d[\d\.]*', r['valor']):
                pool.add(n)
            try:
                v = abs(float(r['valor_bruto']))
            except ValueError:
                continue
            for d in (0, 1, 2):
                s = f"{v:,.{d}f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                pool.add(s)
                for esc in (1e3, 1e6):
                    pool.add(f"{v / esc:,.{d}f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
    return pool

def main(pptx, livro):
    pool = pool_do_livro(livro)
    prs = Presentation(pptx)
    total = sem_lastro = 0
    achados, proibidos = [], []
    for i, s in enumerate(prs.slides, 1):
        textos = [sh.text_frame.text for sh in s.shapes if sh.has_text_frame]
        if s.has_notes_slide and s.notes_slide.notes_text_frame is not None:
            textos.append(s.notes_slide.notes_text_frame.text)
        t = '\n'.join(textos)
        for p in PROIBIDOS:
            if p.lower() in t.lower() and not (p == 'troca' and 'Vale-Troca' in t and t.lower().count('troca') == t.count('Vale-Troca')):
                proibidos.append((i, p))
        for n in re.findall(r'\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+', t):
            total += 1
            if n in pool or n in LEIS:
                continue
            if n in DERIVADOS:
                achados.append((i, n, 'derivado: ' + DERIVADOS[n]))
                continue
            sem_lastro += 1
            achados.append((i, n, 'SEM LASTRO'))
    for i, n, m in achados:
        print(f'slide {i:>2} · {n:>12} · {m}')
    print(f'\n{total} números conferidos · {sem_lastro} sem lastro · {len(proibidos)} frases proibidas')
    for i, p in proibidos:
        print(f'  PROIBIDO no slide {i}: {p}')
    return 1 if (sem_lastro or proibidos) else 0

if __name__ == '__main__':
    a = sys.argv[1:] or ['Vertice_Deck_FINAL.pptx', 'livro_de_numeros.csv']
    sys.exit(main(*a))
