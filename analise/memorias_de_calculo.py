# MEMÓRIAS DE CÁLCULO · Projeto Vértice
# Recalcula, a partir dos CSVs, cada linha da demonstração do resultado (como está e pro forma),
# o business case do slide 10, os custos da solução, o payback e o resultado do 1º ano,
# e confere cada total com o Livro de Números. Se algum total divergir, o script para com erro.
#
# Uso: python memorias_de_calculo.py [pasta_dos_csvs] [livro_de_numeros.csv]
#      padrão: ../4_Dados_e_Enunciado/dados e ../2_Livro_de_Numeros_e_Calculos/livro_de_numeros.csv
# Grava memorias_de_calculo.json na pasta em que for executado e imprime as memórias.
import os, sys, json
import pandas as pd, numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
D = sys.argv[1] if len(sys.argv) > 1 else os.path.join(AQUI, '..', '4_Dados_e_Enunciado', 'dados')
LV = sys.argv[2] if len(sys.argv) > 2 else os.path.join(AQUI, '..', '2_Livro_de_Numeros_e_Calculos', 'livro_de_numeros.csv')

# ---------------------------------------------------------------- dados (mesmas regras do Livro)
v = pd.read_csv(os.path.join(D, 'Vendas.csv'), encoding='utf-8-sig').dropna(subset=['receita_bruta']).copy()
a = pd.read_csv(os.path.join(D, 'Atendimento.csv'), encoding='utf-8-sig').dropna(subset=['order_id'])
v['dt'] = pd.to_datetime(v.data_pedido); v['st'] = v.status_pagamento; v['dev'] = v.devolvido.astype(bool)
at = a.merge(v[['order_id', 'dt', 'st']], on='order_id')
at = at[pd.to_datetime(at.data_abertura) >= at.dt]                      # só tickets abertos depois do pedido
v = v.merge(at.groupby('order_id').custo_operacional_ticket.sum().rename('tk'), on='order_id', how='left').fillna({'tk': 0})

y = v[v.dt < '2024-01-01']                    # pedidos de 2023, todos os status
A = y[y.st == 'Aprovado']                     # aprovados
R = A[A.dev]                                  # aprovados e devolvidos
K = A[~A.dev]                                 # aprovados e mantidos
C = y[y.st == 'Cancelado']; P = y[y.st == 'Aguardando']
lv = pd.read_csv(LV, sep=';', encoding='utf-8-sig').set_index('id')
def L(i): return float(lv.loc[i, 'valor_bruto'])

M = {}                                        # tudo o que vai para o JSON
def grupo(df):
    return dict(pedidos=int(len(df)), bruta=float(df.receita_bruta.sum()), desconto=float(df.desconto_reais.sum()),
                liquida=float(df.receita_liquida.sum()), custo=float(df.custo_produto.sum()),
                frete=float(df.custo_frete.sum()), margem=float(df.margem_contribuicao.sum()), tickets=float(df.tk.sum()))
M['grupos'] = {'mantidos': grupo(K), 'devolvidos': grupo(R), 'cancelados': grupo(C), 'aguardando': grupo(P), 'todos': grupo(y)}
g = M['grupos']

# ---------------------------------------------------------------- demonstração: como está
RB = g['todos']['bruta']
CP = g['cancelados']['bruta'] + g['aguardando']['bruta']
DESC = g['mantidos']['desconto'] + g['devolvidos']['desconto']
DEV = g['devolvidos']['liquida']
RLR = RB - CP - DESC - DEV
CMV = g['mantidos']['custo']
FR = g['mantidos']['frete'] + g['devolvidos']['frete']
tkA = at[at.order_id.isin(A.order_id)]
tk_canal = tkA.groupby('canal_entrada').agg(tickets=('custo_operacional_ticket', 'size'),
                                            custo_unit=('custo_operacional_ticket', 'first'),
                                            total=('custo_operacional_ticket', 'sum'))
TK = float(tk_canal.total.sum())
MR = RLR - CMV - FR - TK
RL_REG = g['todos']['liquida']

# ---------------------------------------------------------------- demonstração: pro forma
fora_nov = lambda df: df[df.dt.dt.month != 11]
exc = lambda df: (df.desconto_reais - 0.20 * df.receita_bruta).clip(lower=0)
XA_K = float(exc(fora_nov(K)).sum()); XA_R = float(exc(fora_nov(R)).sum()); XA = XA_K + XA_R
n_aff_K = int((exc(fora_nov(K)) > 0).sum()); n_aff_R = int((exc(fora_nov(R)) > 0).sum())
MPk = K[(K.canal == 'Marketplace') & (K.receita_liquida >= 250)]
FR_MP = float(MPk.custo_frete.sum())
MPr = R[(R.canal == 'Marketplace') & (R.receita_liquida >= 250)]
DIA = 6000 * 1.8 / 21
api = 104 * (18000 * 2.0 + 2400 * 10.0) / 1e6 * 5.13
hosp = 24.0 * 5.13
manut = 2 * DIA
REC_MES = api * 5 + hosp + manut
SOL = REC_MES * 12
DESC_p = DESC - XA; DEV_p = DEV + XA_R; FR_p = FR - FR_MP
RLR_p = RB - CP - DESC_p - DEV_p
MR_p = RLR_p - CMV - FR_p - TK
RES_p = MR_p - SOL

M['dre'] = dict(RB=RB, CP=CP, CP_canc=g['cancelados']['bruta'], CP_pend=g['aguardando']['bruta'], DESC=DESC, DEV=DEV, RLR=RLR,
                CMV=CMV, CMV_dev=g['devolvidos']['custo'], FR=FR, TK=TK, MR=MR, PCT=MR / RLR * 100, RL_REG=RL_REG,
                PCTREG=MR / RL_REG * 100, RES=MR,
                XA=XA, XA_K=XA_K, XA_R=XA_R, n_aff_K=n_aff_K, n_aff_R=n_aff_R, n_foranov_K=int(len(fora_nov(K))),
                n_foranov_R=int(len(fora_nov(R))), FR_MP=FR_MP, n_MP=int(len(MPk)), n_MP_K=int((K.canal == 'Marketplace').sum()),
                FR_MP_dev=float(MPr.custo_frete.sum()),
                DESC_p=DESC_p, DEV_p=DEV_p, RLR_p=RLR_p, FR_p=FR_p, MR_p=MR_p, PCT_p=MR_p / RLR_p * 100,
                RL_REG_p=RL_REG + XA, PCTREG_p=MR_p / (RL_REG + XA) * 100, SOL=SOL, RES_p=RES_p)
M['atendimento'] = [dict(canal=c, tickets=int(r.tickets), custo_unit=float(r.custo_unit), total=float(r.total))
                    for c, r in tk_canal.sort_values('total', ascending=False).iterrows()]

# ---------------------------------------------------------------- ponte da margem calculada (slide 2)
N18 = g['todos']['margem']; N19 = g['cancelados']['margem']; N20 = g['aguardando']['margem']
N21 = g['devolvidos']['margem'] + g['devolvidos']['frete']; N24 = TK
M['ponte'] = dict(N18=N18, N19=N19, N20=N20, N21=N21, N21_rl=DEV, N21_custo=g['devolvidos']['custo'], N24=N24,
                  N25=N19 + N20 + N21 + N24, N27=N18 - (N19 + N20 + N21 + N24), M02=N18 / RL_REG * 100)

# ---------------------------------------------------------------- business case e custos
esforco = [('Desconto: regra de teto no checkout', 5, 10), ('Desconto: grupo de controle e leitura do teste', 5, 8),
           ('Desconto: alçadas e comunicação comercial', 2, 3), ('Frete Marketplace: leitura de contrato e proposta', 3, 5),
           ('Frete Marketplace: negociação', 3, 5), ('Pós-pedido: 3 campos obrigatórios no fluxo de devolução', 10, 15),
           ('Pós-pedido: saneamento de pendências', 3, 5), ('MarginGuard: extração semanal automatizada', 5, 10),
           ('MarginGuard: motor e testes contra o Livro', 5, 8), ('MarginGuard: camada de IA, guardrail e revisão LGPD', 5, 8),
           ('MarginGuard: memo agendado e treinamento', 3, 5)]
lo = sum(e[1] for e in esforco); hi = sum(e[2] for e in esforco); mid = (lo + hi) / 2
INV = mid * DIA
ben = XA_K / 12
def payback(inv, rec, ben, meses=8):
    acc, linhas, pb = 0.0, [], None
    for m in range(1, meses + 1):
        ganho = ben * 0.5 if m == 1 else ben
        acc += ganho - rec
        linhas.append(dict(mes=m, ganho=ganho, custo=rec, acumulado=acc, cobre=acc >= inv))
        if pb is None and acc >= inv: pb = m
    return pb, linhas
pb, tab = payback(INV, REC_MES, ben)
pb_pior, tab_pior = payback(hi * DIA * 2, api * 5 + hosp + manut * 2, ben)
Y1_desc = XA / 12 * 11.5; Y1_dev = XA_R / 12 * 11.5
M['bc'] = dict(N38=XA_K, N46=FR_MP, N48=XA_K + FR_MP, N49=XA_K / (XA_K + FR_MP) * 100, DIA=DIA, api=api, api5=api * 5, hosp=hosp,
               manut=manut, REC_MES=REC_MES, SOL=SOL, esforco=esforco, lo=lo, hi=hi, mid=mid, INV=INV, INV_pior=hi * DIA * 2,
               REC_pior=api * 5 + hosp + manut * 2, ben=ben, payback=pb, tab=tab, payback_pior=pb_pior, tab_pior=tab_pior,
               Y1_desc=Y1_desc, Y1_dev=Y1_dev, Y1_res=Y1_desc - Y1_dev - SOL - INV, N73=ben * 11.5 - SOL - INV,
               caixa_ano=(api * 5 + hosp) * 12)

# ---------------------------------------------------------------- conferência com o Livro
conf = [('DF_RB_antes', RB), ('DF_CP_antes', CP), ('DF_DESC_antes', DESC), ('DF_DEV_antes', DEV), ('DF_RLR_antes', RLR),
        ('DF_CMV_antes', CMV), ('DF_FR_antes', FR), ('DF_TK_antes', TK), ('DF_MR_antes', MR), ('DF_PCT_antes', MR / RLR * 100),
        ('DF_PCTREG_antes', MR / RL_REG * 100), ('DF_DESC_pro', DESC_p), ('DF_DEV_pro', DEV_p), ('DF_RLR_pro', RLR_p),
        ('DF_FR_pro', FR_p), ('DF_MR_pro', MR_p), ('DF_PCT_pro', MR_p / RLR_p * 100), ('DF_PCTREG_pro', MR_p / (RL_REG + XA) * 100),
        ('DF_SOL_pro', SOL), ('DF_RES_pro', RES_p), ('DF_X_A', XA), ('DF_X_R', XA_R), ('N38', XA_K), ('N46', FR_MP),
        ('DF_MP_R', float(MPr.custo_frete.sum())), ('DF_CMV_dev', g['devolvidos']['custo']), ('DF_FR_K', g['mantidos']['frete']),
        ('DF_FR_R', g['devolvidos']['frete']), ('N18', N18), ('N19', N19), ('N20', N20), ('N21', N21), ('N24', N24),
        ('N25', N19 + N20 + N21 + N24), ('N27', N18 - (N19 + N20 + N21 + N24)), ('M01', RL_REG), ('M02', N18 / RL_REG * 100),
        ('N62', DIA), ('N63', lo), ('N64', hi), ('N65', INV), ('N67', api), ('N68', hosp), ('N69', manut), ('N70', REC_MES),
        ('N71', pb), ('N72', pb_pior), ('N73', ben * 11.5 - SOL - INV), ('DF_Y1_desc', Y1_desc), ('DF_Y1_dev', Y1_dev),
        ('DF_Y1_res', Y1_desc - Y1_dev - SOL - INV), ('N74', (api * 5 + hosp) * 12), ('DF_n_all', len(y)), ('N02', len(A)),
        ('N19b', len(C)), ('N20b', len(P)), ('N21b', len(R))]
falhas = [(i, x, L(i)) for i, x in conf if abs(x - L(i)) > 1e-6 * max(1, abs(L(i)))]
M['conferencia'] = dict(itens=len(conf), falhas=len(falhas))
if falhas:
    for f in falhas: print('DIVERGE', f)
    sys.exit(1)

# identidades usadas nas memórias
assert abs(RLR - g['mantidos']['liquida']) < 1e-4, 'receita líquida realizada = receita líquida dos pedidos mantidos'
assert abs(N21 - (DEV - g['devolvidos']['custo'])) < 1e-4, 'perda da devolução = reembolso − custo que volta ao estoque'
assert abs(MR - M['ponte']['N27']) < 1e-4, 'margem realizada pela demonstração = margem calculada − perda depois do pedido'
assert abs((MR_p - MR) - (XA_K + FR_MP)) < 1e-4, 'variação da margem = teto (mantidos) + frete Marketplace'

# ---------------------------------------------------------------- dados complementares dos artefatos 2 e 3 (fatos da base)
vm = v.copy(); vm['mes'] = vm.dt.dt.to_period('M').astype(str)
mes = []
for m_, d_ in vm.groupby('mes'):
    a_ = d_[d_.st == 'Aprovado']
    mes.append(dict(mes=m_, pedidos_todos=int(len(d_)), aprovados=int(len(a_)), rl_aprov=float(a_.receita_liquida.sum()),
                    devol_pct=float(a_.dev.mean() * 100), canc_pct=float((d_.st == 'Cancelado').mean() * 100)))
M['mensal'] = mes
mot = R.groupby('motivo_devolucao').agg(pedidos=('order_id', 'size'), rl=('receita_liquida', 'sum'),
                                          perda=('margem_contribuicao', 'sum'), frete=('custo_frete', 'sum'))
mot['perda'] = mot.perda + mot.frete
M['motivos'] = [dict(motivo=k, pedidos=int(r_.pedidos), rl=float(r_.rl), perda=float(r_.perda))
                for k, r_ in mot.sort_values('pedidos', ascending=False).iterrows()]
tam = A.groupby('categoria').apply(lambda d_: (d_.motivo_devolucao == 'Tamanho errado').mean() * 100)
M['tamanho_por_categoria'] = {k: float(x) for k, x in tam.items()}
MP = A[A.canal == 'Marketplace']; DM = A[A.canal != 'Marketplace']
def perfil(d_, todos):
    return dict(pedidos=int(len(d_)), frete_rl=float(d_.custo_frete.sum() / d_.receita_liquida.sum() * 100),
                prazo=float(d_.tempo_entrega_real.mean()), margem=float(d_.margem_contribuicao.sum() / d_.receita_liquida.sum() * 100),
                rl_pedido=float(d_.receita_liquida.mean()), desc=float(d_.desconto_reais.sum() / d_.receita_bruta.sum() * 100),
                devol=float(d_.dev.mean() * 100), canc=float((todos.st == 'Cancelado').mean() * 100),
                frete_medio=float(d_.loc[d_.custo_frete > 0, 'custo_frete'].mean()))
M['marketplace'] = dict(mp=perfil(MP, y[y.canal == 'Marketplace']), demais=perfil(DM, y[y.canal != 'Marketplace']))

json.dump(M, open('memorias_de_calculo.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=float)
r = lambda z: f"{z:,.0f}".replace(',', '.')
print(f"Conferência com o Livro: {len(conf)} valores, {len(falhas)} divergências. Identidades: 4 de 4.")
print(f"Receita líquida realizada {r(RLR)} = {r(RB)} − {r(CP)} − {r(DESC)} − {r(DEV)}")
print(f"Margem realizada {r(MR)} = {r(RLR)} − {r(CMV)} − {r(FR)} − {r(TK)}")
print(f"Pro forma: margem {r(MR_p)}; resultado {r(RES_p)} (+{r(RES_p - MR)}); 1º ano, caso interno: {r(Y1_desc - Y1_dev - SOL - INV)}")
