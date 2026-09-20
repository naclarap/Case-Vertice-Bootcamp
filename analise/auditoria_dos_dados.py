# AUDITORIA DOS DADOS · Projeto Vértice
# Reproduz os números do Artefato 1 (dicionário, identidades e qualidade das cinco bases).
# Uso: python auditoria_dos_dados.py [pasta_dos_csvs]   (padrão: ../4_Dados_e_Enunciado/dados)
# Grava auditoria_dos_dados.json na pasta em que for executado e imprime o resumo.
import os, sys, json, hashlib
import pandas as pd, numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
D = sys.argv[1] if len(sys.argv) > 1 else os.path.join(AQUI, '..', '4_Dados_e_Enunciado', 'dados')
nomes = ['Vendas', 'Atendimento', 'Estoque', 'Marketing', 'Clientes']
B = {n: pd.read_csv(os.path.join(D, n + '.csv'), encoding='utf-8-sig') for n in nomes}
O = {}

# 1. Tamanho, nulos e impressão digital de cada base
for n, df in B.items():
    h = hashlib.sha256(open(os.path.join(D, n + '.csv'), 'rb').read()).hexdigest()
    O[n] = dict(linhas=int(len(df)), colunas=int(df.shape[1]), nulos_max=int(df.isna().sum().max()), sha256_12=h[:12])

# 2. Vendas: período, linha truncada, identidades, status
v = B['Vendas']; vv = v.dropna(subset=['receita_bruta']).copy()
vv['dt'] = pd.to_datetime(vv.data_pedido); vv['dev'] = vv.devolvido.astype(bool)
O['Vendas'].update(validos=int(len(vv)), inicio=str(vv.dt.min().date()), fim=str(vv.dt.max().date()),
                   order_id_duplicados=int(v.order_id.duplicated().sum()))
ident = {
    'receita_bruta = quantidade × preco_unitario': np.isclose(vv.receita_bruta, vv.quantidade * vv.preco_unitario, atol=0.011).mean(),
    'receita_liquida = receita_bruta − desconto_reais': np.isclose(vv.receita_liquida, vv.receita_bruta - vv.desconto_reais, atol=0.011).mean(),
    'margem_contribuicao = receita_liquida − custo_produto − custo_frete':
        np.isclose(vv.margem_contribuicao, vv.receita_liquida - vv.custo_produto - vv.custo_frete, atol=0.011).mean()}
O['identidades'] = {k: float(x * 100) for k, x in ident.items()}
O['status_13m'] = {k: int(x) for k, x in vv.status_pagamento.value_counts().items()}
O['devolvidos_13m'] = int(vv.dev.sum())
O['motivo_preenchido_devolvidos'] = float((vv.loc[vv.dev, 'motivo_devolucao'] != 'Não se aplica').mean() * 100)
tab = []
for rot, m in [('Aprovado, não devolvido', (vv.status_pagamento == 'Aprovado') & ~vv.dev),
               ('Aprovado, devolvido', (vv.status_pagamento == 'Aprovado') & vv.dev),
               ('Cancelado', vv.status_pagamento == 'Cancelado'), ('Aguardando', vv.status_pagamento == 'Aguardando')]:
    d = vv[m]; tab.append(dict(grupo=rot, pedidos=int(len(d)), rl=float(d.receita_liquida.sum()), margem=float(d.margem_contribuicao.sum())))
O['status_x_devolucao_13m'] = tab
O['cancelado_e_devolvido'] = int(((vv.status_pagamento == 'Cancelado') & vv.dev).sum())
O['margem_negativa'] = int((vv.margem_contribuicao < 0).sum())
O['desconto_zero_pct'] = float((vv.desconto_reais == 0).mean() * 100)
O['frete_zero_pct'] = float((vv.custo_frete == 0).mean() * 100)
top = vv.customer_id.value_counts()
O['clientes_em_vendas'] = int(vv.customer_id.nunique())
O['maior_cliente'] = dict(id=top.index[0], pct_pedidos=float(top.iloc[0] / len(vv) * 100),
                          pct_receita=float(vv.loc[vv.customer_id == top.index[0], 'receita_liquida'].sum() / vv.receita_liquida.sum() * 100),
                          receita=float(vv.loc[vv.customer_id == top.index[0], 'receita_liquida'].sum()))
vv['mes'] = vv.dt.dt.to_period('M').astype(str)
O['pedidos_por_mes'] = {k: int(x) for k, x in vv.groupby('mes').size().items()}
O['sku_em_estoque_pct'] = float(vv.sku_id.isin(B['Estoque'].sku_id).mean() * 100)

# 3. Atendimento
a = B['Atendimento'].dropna(subset=['order_id']).copy()
lig = a[a.order_id.isin(vv.order_id)].merge(vv[['order_id', 'dt']], on='order_id')
O['atendimento'] = dict(validos=int(len(a)), ligados=int(len(lig)), ligados_pct=float(len(lig) / len(a) * 100),
                        antes_do_pedido_pct=float((pd.to_datetime(lig.data_abertura) < lig.dt).mean() * 100),
                        custo_por_canal={k: float(x) for k, x in a.groupby('canal_entrada').custo_operacional_ticket.first().items()},
                        textos_distintos=int(a.texto_cliente.nunique()))

# 4. Marketing, Clientes e Estoque: reconciliação com Vendas
mk = B['Marketing'].copy(); mk['ini'] = pd.to_datetime(mk.data_inicio)
O['marketing'] = dict(conversoes_2023=float(mk.loc[mk.ini.dt.year == 2023, 'conversoes'].sum()),
                      modelos_atribuicao={k: int(x) for k, x in mk.atribuicao.value_counts().items()})
cl = B['Clientes']
prim = vv.groupby('customer_id').dt.min()
cad = cl.set_index('customer_id').data_cadastro.pipe(pd.to_datetime)
comum = prim.index.intersection(cad.index)
O['clientes'] = dict(cadastro=int(len(cl)), em_vendas=int(len(comum)),
                     cadastro_depois_do_1o_pedido=int((cad[comum] > prim[comum]).sum()),
                     ltv_maior_cliente=float(cl.set_index('customer_id').loc[top.index[0], 'ltv_acumulado']))
O['estoque'] = dict(status={k: int(x) for k, x in B['Estoque'].status_disponibilidade.value_counts().items()},
                    fornecedores=int(B['Estoque'].fornecedor_id.nunique()))

# 5. Dicionário automático: tipo, nulos, distintos e resumo de cada coluna das cinco bases
def resumo(s):
    s2 = s.dropna()
    if s.dtype == bool or set(map(str, s2.unique())) <= {'True', 'False'}:
        return 'booleano', '; '.join(f'{k} {v:,}'.replace(',', '.') for k, v in s2.astype(str).value_counts().items())
    if pd.api.types.is_numeric_dtype(s2):
        f = lambda x: f'{x:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.').replace(',00', '')
        return 'número', f'{f(s2.min())} a {f(s2.max())} (média {f(s2.mean())})'
    if s2.astype(str).str.match(r'\d{4}-\d{2}-\d{2}').mean() > 0.95:
        dt = pd.to_datetime(s2, errors='coerce', format='mixed')
        return 'data', f'{dt.min().date()} a {dt.max().date()}'
    if s2.nunique() <= 8:
        return 'texto', '; '.join(f'{k} {v:,}'.replace(',', '.') for k, v in s2.value_counts().items())
    return 'texto', f'{s2.nunique():,} valores distintos'.replace(',', '.')
O['dicionario'] = {n: [dict(coluna=c, tipo=resumo(df[c])[0], nulos=int(df[c].isna().sum()), distintos=int(df[c].nunique()),
                           resumo=resumo(df[c])[1]) for c in df.columns] for n, df in B.items()}

json.dump(O, open('auditoria_dos_dados.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('Auditoria gravada em auditoria_dos_dados.json:', ', '.join(f"{n} {O[n]['linhas']} linhas" for n in nomes))
