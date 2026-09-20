# LIVRO DE NÚMEROS · Projeto Vértice. Todo número do deck sai daqui.
# Uso: python livro_de_numeros.py [pasta_dos_csvs]   (padrão: ../4_Dados_e_Enunciado/dados)
# Grava livro_de_numeros.csv e livro_de_numeros.md na pasta em que for executado.
# Premissa de devolução: reembolso integral de todos os pedidos devolvidos; o item volta ao estoque e o frete de ida se perde.
import pandas as pd, numpy as np
from scipy import stats
import os, sys
_AQUI=os.path.dirname(os.path.abspath(__file__))
D=(sys.argv[1] if len(sys.argv)>1 else os.path.join(_AQUI,'..','4_Dados_e_Enunciado','dados'))
D=D if D.endswith(os.sep) or D.endswith('/') else D+os.sep
if not os.path.exists(D+'Vendas.csv'): D='./'
v=pd.read_csv(D+'Vendas.csv',encoding='utf-8-sig').dropna(subset=['receita_bruta']).copy()
e=pd.read_csv(D+'Estoque.csv',encoding='utf-8-sig'); a=pd.read_csv(D+'Atendimento.csv',encoding='utf-8-sig').dropna(subset=['order_id'])
v['dt']=pd.to_datetime(v.data_pedido); v['mes']=v.dt.dt.to_period('M').astype(str); v['dev']=v.devolvido.astype(bool); v['st']=v.status_pagamento
v['pct']=v.desconto_reais/v.receita_bruta; v['smt']=np.where(v.dt<'2023-07-01','S1',np.where(v.dt<'2024-01-01','S2','J24'))
v=v.merge(e[['sku_id','fornecedor_id']],on='sku_id',how='left')
at=a.merge(v[['order_id','dt']],on='order_id'); at=at[pd.to_datetime(at.data_abertura)>=at.dt]
v=v.merge(at.groupby('order_id').custo_operacional_ticket.sum().rename('tk'),on='order_id',how='left').fillna({'tk':0})
L=[]
def add(id_,desc,valor,fmt,tag,base,calc,prem='—'):
    L.append(dict(id=id_,numero=desc,valor=fmt.format(valor) if isinstance(fmt,str) else fmt(valor),valor_bruto=valor,marca=tag,base_colunas=base,calculo=calc,premissa=prem))
def val(i): return L[[x['id'] for x in L].index(i)]['valor_bruto']
br=lambda x: f"R$ {x:,.0f}".replace(',','.')
mi=lambda x: f"R$ {x/1e6:,.2f} mi".replace('.',',')
mil=lambda x: f"R$ {x/1e3:,.1f} mil".replace(',','X').replace('.',',').replace('X','.')
pc=lambda x: f"{x:.2f}%".replace('.',',')
pc1=lambda x: f"{x:.1f}%".replace('.',',')
pp=lambda x: f"{x:+.2f}".replace('.',',')+" p.p."
n0=lambda x: f"{x:,.0f}".replace(',','.')
y=v[v.dt<'2024-01-01']; A=y[y.st=='Aprovado']; R=A[A.dev]; K=A[~A.dev]
PREM_DEV='reembolso integral de todo pedido devolvido; item volta ao estoque; frete de ida não se recupera'
# --- Base e escala
add('N01','Pedidos válidos, 13 meses',len(v),n0,'F','vendas.csv (exclui 1 linha truncada)','contagem')
add('N02','Pedidos aprovados 2023',len(A),n0,'F','vendas: status_pagamento','contagem')
add('N03','Receita líquida aprovados 2023',A.receita_liquida.sum(),mi,'F','vendas: receita_liquida','soma')
# --- Margem no tempo
M=v[v.st=='Aprovado'].groupby('mes').apply(lambda d:d.margem_contribuicao.sum()/d.receita_liquida.sum()*100)
add('N04','Margem calculada mensal: mínimo (nov/23)',M.min(),pc,'F','vendas aprovados: margem_contribuicao, receita_liquida','Σmargem/Σreceita líquida por mês')
add('N05','Margem calculada mensal: máximo (jun/23)',M.max(),pc,'F','idem','idem')
S=v[v.st=='Aprovado'].groupby('smt').apply(lambda d:d.margem_contribuicao.sum()/d.receita_liquida.sum()*100)
add('N06','Margem calculada S1 2023',S['S1'],pc,'F','idem','jan–jun/23'); add('N07','Margem calculada S2 2023',S['S2'],pc,'F','idem','jul–dez/23')
s2n=v[(v.smt=='S2')&(v.mes!='2023-11')&(v.st=='Aprovado')]
add('N08','Margem calculada S2 sem novembro',s2n.margem_contribuicao.sum()/s2n.receita_liquida.sum()*100,pc,'F','idem','jul–dez/23 exceto nov')
nv=A[A.mes=='2023-11']; add('N09','Desconto / receita bruta em nov/23',nv.desconto_reais.sum()/nv.receita_bruta.sum()*100,pc,'F','vendas aprovados: desconto_reais, receita_bruta','Σdesconto/Σbruta')
x=np.arange(len(M)); add('N10','Tendência da margem calculada (13 meses)',np.polyfit(x,M.values,1)[0],lambda z:f"{z:+.3f}".replace('.',',')+" p.p./mês (r = "+f"{np.corrcoef(x,M.values)[0,1]:+.2f}".replace('.',',')+")",'F','idem','regressão linear mensal')
from itertools import combinations
mm=A.groupby('mes').agg(mc=('margem_contribuicao','sum'),liq=('receita_liquida','sum'))
obs=(mm.iloc[6:].mc.sum()/mm.iloc[6:].liq.sum()-mm.iloc[:6].mc.sum()/mm.iloc[:6].liq.sum())*100
dif=[]
for c in combinations(range(12),6):
    g1=mm.iloc[list(c)]; g2=mm.drop(mm.index[list(c)]); dif.append((g2.mc.sum()/g2.liq.sum()-g1.mc.sum()/g1.liq.sum())*100)
add('N11','Divisões de 2023 em 6+6 meses com diferença ≥ S1→S2',(np.abs(dif)>=abs(obs)-1e-9).mean()*100,pc1,'F','idem','924 combinações')
dS=A.groupby('smt').apply(lambda d:d.desconto_reais.sum()/d.receita_bruta.sum()*100)
add('N12','Taxa de desconto S1 2023',dS['S1'],pc,'F','vendas aprovados','Σdesconto/Σbruta'); add('N13','Taxa de desconto S2 2023',dS['S2'],pc,'F','idem','idem')
pico=['2023-03','2023-05','2023-11','2023-12']; q=A[~A.mes.isin(pico)]
dq=q.groupby('smt').apply(lambda d:d.desconto_reais.sum()/d.receita_bruta.sum()*100); add('N14','Alta da taxa de desconto fora dos meses de pico (S1→S2)',dq['S2']-dq['S1'],pp,'F','idem','exclui mar, mai, nov, dez')
def mc2(d):
    Ad=d[d.st=='Aprovado']; Rd=Ad[Ad.dev]; return (Ad[~Ad.dev].margem_contribuicao.sum()-Rd.custo_frete.sum()-Ad.tk.sum())/len(Ad)
c1,c2=mc2(v[v.smt=='S1']),mc2(v[v.smt=='S2'])
add('N15','Contribuição realizada por pedido aprovado S1',c1,lambda z:f"R$ {z:.2f}".replace('.',','),'E','vendas + atendimento','(margem não devolvidos − frete dos devolvidos − tickets)/pedidos aprovados',PREM_DEV+'; ticket = custo por canal')
add('N16','Contribuição realizada por pedido aprovado S2',c2,lambda z:f"R$ {z:.2f}".replace('.',','),'E','idem','idem','idem')
add('N17','Variação da contribuição realizada por pedido S1→S2',(c2/c1-1)*100,lambda z:f"{z:+.1f}%".replace('.',','),'E','idem','idem','idem')
# --- Árvore 2023
reg=y.margem_contribuicao.sum(); add('N18','Margem calculada sobre todos os pedidos de 2023',reg,mi,'F','vendas todos status','Σmargem_contribuicao')
canc=y[y.st=='Cancelado']; pend=y[y.st=='Aguardando']
add('N19','Cancelamento: margem de pedidos cancelados 2023',canc.margem_contribuicao.sum(),mi,'F','vendas status=Cancelado','Σmargem',); add('N19b','Pedidos cancelados 2023',len(canc),n0,'F','idem','contagem')
add('N20','Pendência: margem de pedidos Aguardando 2023',pend.margem_contribuicao.sum(),mi,'F','vendas status=Aguardando','Σmargem'); add('N20b','Pedidos Aguardando 2023',len(pend),n0,'F','idem','contagem')
perda=R.margem_contribuicao+R.custo_frete
dev_c=perda.sum()
add('N21','Devolução: margem perdida 2023 (reembolso integral)',dev_c,mi,'E','vendas aprovados devolvidos: margem_contribuicao, custo_frete','Σ(margem + frete de ida) dos 3.485 devolvidos',PREM_DEV)
add('N21b','Pedidos aprovados devolvidos 2023',len(R),n0,'F','vendas: devolvido','contagem')
add('N22','Devolução: piso factual 2023',R.custo_frete.sum()+R.tk.sum(),mil,'F','vendas + atendimento','frete de ida dos devolvidos + tickets vinculados')
add('N23','Devolução: sensibilidade alta 2023',perda.sum()+R.loc[R.motivo_devolucao=='Produto com defeito','custo_produto'].sum(),mi,'E','idem','N21 + custo do produto nos defeitos','item com defeito não revendável')
add('N24','Atendimento: custo de tickets ligados a aprovados 2023',A.tk.sum(),mi,'E','atendimento: custo_operacional_ticket','Σ tickets abertos após o pedido','custo fixo por canal (R$ 2/15/45)')
tot=canc.margem_contribuicao.sum()+pend.margem_contribuicao.sum()+dev_c+A.tk.sum()
add('N25','Margem perdida depois do pedido 2023',tot,mi,'E','N19+N20+N21+N24','soma','ver N21 e N24'); add('N26','Margem perdida depois do pedido / margem calculada',tot/reg*100,pc1,'E','N25/N18','divisão','idem')
for k,(lab,vv) in {'dev':('Devolução',dev_c),'can':('Cancelamento',canc.margem_contribuicao.sum()),'pen':('Pendência',pend.margem_contribuicao.sum()),'ate':('Atendimento',A.tk.sum())}.items():
    add(f'N26_{k}',f'{lab} / margem calculada 2023',vv/reg*100,pc1,'E' if k in('dev','ate') else 'F',f'N{ {"dev":21,"can":19,"pen":20,"ate":24}[k]}/N18','divisão','ver N21' if k=='dev' else '—')
add('N27','Margem que se realiza 2023',reg-tot,mi,'E','N18−N25','subtração','idem')
add('N28','Desconto concedido 2023 (aprovados)',A.desconto_reais.sum(),mi,'F','vendas: desconto_reais','soma')
add('N29','Frete pago 2023 (aprovados)',A.custo_frete.sum(),mi,'F','vendas: custo_frete','soma','custo_frete = custo arcado pela Vértice')
add('N30','Frete pago Marketplace 2023 (aprovados)',A[A.canal=='Marketplace'].custo_frete.sum(),mi,'F','idem','soma','idem')
add('N31','Custo do produto por R$ 100 de receita bruta S1',A[A.smt=='S1'].custo_produto.sum()/A[A.smt=='S1'].receita_bruta.sum()*100,lambda z:f"R$ {z:.2f}".replace('.',','),'F','vendas: custo_produto','Σcusto/Σbruta×100')
add('N32','Custo do produto por R$ 100 de receita bruta S2',A[A.smt=='S2'].custo_produto.sum()/A[A.smt=='S2'].receita_bruta.sum()*100,lambda z:f"R$ {z:.2f}".replace('.',','),'F','idem','idem')
add('N33','Marketplace: % da receita líquida (S1 e S2)',A[A.canal=='Marketplace'].receita_liquida.sum()/A.receita_liquida.sum()*100,pc1,'F','vendas: canal','Σ MP/Σ total')
# --- Desconto e volume
A2=A.copy(); A2['band']=pd.cut(A2.pct,[-0.001,0.0001,0.15,0.25,0.40001],labels=['0','0-15','15-25','25-40'])
for b,g in A2.groupby('band'): add(f'N34_{b}',f'Itens por pedido, faixa de desconto {b}%',g.quantidade.mean(),lambda z:f"{z:.2f}".replace('.',','),'F','vendas aprovados: quantidade, desconto_reais/receita_bruta','média')
add('N35','Teste de quantidade entre faixas (Kruskal-Wallis, p)',stats.kruskal(*[g.quantidade.values for _,g in A2.groupby('band')]).pvalue,lambda z:f"p = {z:.3f}".replace('.',','),'F','idem','Kruskal-Wallis')
d=y.groupby(y.dt.dt.date).agg(ped=('order_id','size'),desc=('desconto_reais','sum'),bruta=('receita_bruta','sum')); d['tx']=d.desc/d.bruta*100
d.index=pd.to_datetime(d.index); d['m']=d.index.month; d['w']=d.index.dayofweek
def reg_(df):
    X=np.column_stack([df.tx.values,pd.get_dummies(df.m).values.astype(float),pd.get_dummies(df.w,drop_first=True).values.astype(float)])
    b=np.linalg.lstsq(X,df.ped.values,rcond=None)[0]; r=df.ped.values-X@b; se=np.sqrt(r@r/(len(df)-X.shape[1])*np.linalg.pinv(X.T@X)[0,0]); return b[0],b[0]/se
b,t=reg_(d[d.m!=11]); add('N36','Pedidos/dia por +1 p.p. de desconto, fora de novembro',b,lambda z:f"{z:+.2f} (t = {t:.1f})".replace('.',','),'F','vendas 2023 diário','regressão com efeito fixo de mês e dia da semana')
b,t=reg_(d); add('N37','Pedidos/dia por +1 p.p. de desconto, ano todo',b,lambda z:f"{z:+.2f} (t = {t:.1f})".replace('.',','),'F','idem','idem')
nov=K.dt.dt.month==11
for cap,idn in [(0.20,'N38'),(0.25,'N39')]:
    exc=(K.desconto_reais-cap*K.receita_bruta).clip(lower=0); aff=K.pct>cap; m=~nov
    G=exc[m].sum(); eq=G/(K.loc[aff&m,'margem_contribuicao']+exc[aff&m]).sum()*100
    add(idn,f'Teto de {cap:.0%} fora de novembro: contribuição preservada/ano',G,mil,'E','vendas aprovados não devolvidos 2023','Σ max(0, desconto − teto×bruta), exceto nov','volume constante (testado N34–N36)')
    add(idn+'b',f'Teto de {cap:.0%} fora de novembro: pedidos afetados',(aff&m).sum()/m.sum()*100,pc1,'F','idem','% pedidos com desconto > teto')
    add(idn+'c',f'Teto de {cap:.0%} fora de novembro: ponto de equilíbrio',eq,pc1,'E','idem','ganho / margem dos afetados após teto','perda de pedidos afetados que zera o ganho')
    if cap==0.20:
        for cat,vl in exc[m].groupby(K.categoria[m]).sum().items(): add(f'N38_{cat}',f'Teto 20% fora de nov: {cat}',vl,mil,'E','idem','idem','idem')
# --- Frete e Marketplace
O=v[v.canal!='Marketplace']; add('N40','Aderência da regra "frete só se receita líquida < R$ 250" (6 canais)',((O.receita_liquida<250)==(O.custo_frete>0)).mean()*100,pc1,'F','vendas: custo_frete, receita_liquida','% pedidos em que a regra acerta')
for c,g in A.groupby('canal'): add(f'N41_{c}',f'% pedidos com frete pago: {c} (aprov. S1–S2)',(g.custo_frete>0).mean()*100,pc1,'F','vendas: custo_frete>0','%')
MP=A[A.canal=='Marketplace']; DM=A[A.canal!='Marketplace']
add('N42','Prazo médio Marketplace (dias)',MP.tempo_entrega_real.mean(),lambda z:f"{z:.1f}".replace('.',','),'F','vendas: tempo_entrega_real','média'); add('N43','Prazo médio demais canais (dias)',DM.tempo_entrega_real.mean(),lambda z:f"{z:.1f}".replace('.',','),'F','idem','média')
add('N44','Margem calculada Marketplace',MP.margem_contribuicao.sum()/MP.receita_liquida.sum()*100,pc,'F','vendas','Σmargem/Σliq','sem comissão do marketplace (não está na base)'); add('N45','Margem calculada demais canais',DM.margem_contribuicao.sum()/DM.receita_liquida.sum()*100,pc,'F','idem','idem')
MPk=K[K.canal=='Marketplace']; add('N46','Regra de frete dos demais canais no Marketplace: contribuição preservada/ano',MPk.loc[MPk.receita_liquida>=250,'custo_frete'].sum(),mil,'E','vendas MP aprovados não devolvidos 2023','Σ frete em pedidos com receita líquida ≥ R$ 250','parceiro aceita a regra')
add('N47','Caso-base interno/ano',val('N38'),mil,'E','N38','—','ver N38')
add('N48','Caso-base com Marketplace/ano',val('N38')+val('N46'),mil,'E','N38+N46','soma','ver N38 e N46')
add('N49','Parcela do caso-base sob controle interno',val('N38')/val('N48')*100,pc1,'E','N38/N48','divisão','idem')
# --- Pós-pedido: concentração e qualidade
def p_chi(tab): return stats.chi2_contingency(tab)[1]
add('N50','Taxa de devolução, aprovados 2023',A.dev.mean()*100,pc1,'F','vendas: devolvido','%')
add('N51','Devolução por canal: teste (p)',p_chi(pd.crosstab(A.canal,A.dev)),lambda z:f"p = {z:.2f}".replace('.',','),'F','idem','qui-quadrado')
f=A.groupby('fornecedor_id').agg(n=('order_id','size'),dfe=('motivo_devolucao',lambda s:(s=='Produto com defeito').sum()))
add('N52','Defeito por fornecedor: teste (p)',p_chi(np.c_[f.dfe,f.n-f.dfe]),lambda z:f"p = {z:.2f}".replace('.',','),'F','vendas+estoque: fornecedor_id','qui-quadrado 100 fornecedores')
add('N53','Devoluções por "Tamanho errado" em Beleza e Lifestyle',((R.motivo_devolucao=='Tamanho errado')&R.categoria.isin(['Beleza','Lifestyle'])).sum(),n0,'F','vendas: motivo_devolucao, categoria','contagem')
add('N54','Taxa de cancelamento 2023 (todos)',(y.st=='Cancelado').mean()*100,pc1,'F','vendas: status_pagamento','%'); add('N55','Cancelamento por canal: teste (p)',p_chi(pd.crosstab(y.canal,y.st=='Cancelado')),lambda z:f"p = {z:.2f}".replace('.',','),'F','idem','qui-quadrado')
j=v[v.mes=='2023-01']; add('N56','Pedidos de jan/23 ainda Aguardando em 26/01/2024',(j.st=='Aguardando').mean()*100,pc1,'F','vendas','%')
m=~nov
add('N57','Taxa de desconto fora de nov (pedidos mantidos 2023): atual',K[m].desconto_reais.sum()/K[m].receita_bruta.sum()*100,pc,'F','vendas aprovados não devolvidos','Σdesconto/Σbruta')
add('N58','Taxa de desconto fora de nov com teto de 20% (KPI de aceite)',np.minimum(K[m].desconto_reais,0.2*K[m].receita_bruta).sum()/K[m].receita_bruta.sum()*100,pc,'E','idem','Σmin(desconto, 20%×bruta)/Σbruta','volume e mix constantes')
eqt=val('N38b')*val('N38c')/100
add('N59','Equilíbrio do teto de 20% em % de todos os pedidos fora de nov',eqt,pc1,'E','N38b×N38c','produto','idem N38c')
add('N60','Regra de parada do teste: queda de pedidos no grupo tratado vs controle',eqt/2,pc1,'E','N59/2','metade do equilíbrio','margem de segurança de 50%')
add('N61','Contribuição preservada média por mês, teto de 20% (KPI)',val('N38')/12,mil,'E','N38/12','divisão','distribuição uniforme ao longo dos meses')
# --- Business case: custos, esforço e payback (premissas externas declaradas)
SAL=6000.0      # Glassdoor Brasil, Analista de Dados Pleno, média mensal (consulta 17/09/2026)
ENC=1.8         # fator de encargos e benefícios CLT — premissa a validar com RH
DU=21           # dias úteis/mês
DIA=SAL*ENC/DU
USD=5.13        # dólar comercial, dolarhoje.com, 17/09/2026
API_IN,API_OUT=2.0,10.0   # US$/milhão de tokens, Claude Sonnet 5, platform.claude.com/docs pricing
VM=24.0         # US$/mês, AWS Lightsail Linux 4 GB
esforco={'Desconto: regra de teto no checkout':(5,10),'Desconto: grupo de controle e leitura do teste':(5,8),'Desconto: alçadas e comunicação comercial':(2,3),
 'Frete MP: leitura de contrato e proposta':(3,5),'Frete MP: negociação':(3,5),
 'Pós-pedido: 3 campos obrigatórios no fluxo de devolução':(10,15),'Pós-pedido: saneamento de pendências':(3,5),
 'MarginGuard: extração semanal automatizada':(5,10),'MarginGuard: motor e testes contra o Livro':(5,8),'MarginGuard: camada de IA, guardrail e revisão LGPD':(5,8),'MarginGuard: memo agendado e treinamento':(3,5)}
lo=sum(a_ for a_,b_ in esforco.values()); hi=sum(b_ for a_,b_ in esforco.values()); mid=(lo+hi)/2
add('N62','Custo por pessoa-dia (premissa)',DIA,lambda z:f"R$ {z:,.0f}".replace(',','.'),'E','Glassdoor (salário) × fator 1,8 ÷ 21 dias','R$ 6.000 × 1,8 ÷ 21','fator de encargos a validar com RH')
add('N63','Esforço de implantação: mínimo (pessoa-dia)',lo,n0,'E','tabela de esforço por tarefa (Regras e Memórias de Cálculo, seção 4)','soma dos mínimos','estimativa por tarefa')
add('N64','Esforço de implantação: máximo (pessoa-dia)',hi,n0,'E','idem','soma dos máximos','idem')
add('N65','Investimento em esforço interno (ponto médio)',mid*DIA,lambda z:f"R$ {z/1e3:,.1f} mil".replace('.',','),'E','N62 × média(N63,N64)','produto','esforço interno valorado a custo de oportunidade')
add('N66','Investimento em esforço interno: faixa superior com custo/dia em dobro',hi*DIA*2,lambda z:f"R$ {z/1e3:,.1f} mil".replace('.',','),'E','N62×2 × N64','produto','sensibilidade')
q_mes=104; tin=18000; tout=2400
api=q_mes*(tin*API_IN+tout*API_OUT)/1e6*USD
add('N67','Custo mensal de API (104 consultas/mês)',api,lambda z:f"R$ {z:,.0f}".replace(',','.'),'E','preço Sonnet 5 × câmbio','104 × (18 mil tokens × US$ 2 + 2,4 mil × US$ 10)/1 mi × 5,13','4 memos + 100 perguntas/mês; 3 rodadas de ferramenta por consulta')
add('N68','Custo mensal de hospedagem',VM*USD,lambda z:f"R$ {z:,.0f}".replace(',','.'),'E','AWS Lightsail 4 GB × câmbio','US$ 24 × 5,13','servidor dedicado; R$ 0 se rodar em ambiente existente')
man=2*DIA; add('N69','Custo mensal de manutenção (2 pessoa-dia)',man,lambda z:f"R$ {z:,.0f}".replace(',','.'),'E','N62 × 2','produto','2 pessoa-dia/mês de analista')
rec=api*5+VM*USD+man
add('N70','Custo recorrente mensal total (API com margem ×5)',rec,lambda z:f"R$ {z:,.0f}".replace(',','.'),'E','N67×5 + N68 + N69','soma','margem de 5× no uso de API')
ben=val('N38')/12
inv=mid*DIA
def payback(inv,rec,ben):
    acc=0
    for mth in range(1,37):
        acc+=(ben*0.5 if mth==1 else ben)-rec   # mês 1: teste com 50% dos pedidos no grupo tratado
        if acc>=inv: return mth
    return None
add('N71','Payback do caso-base interno (meses)',payback(inv,rec,ben),lambda z:f"{z} meses",'E','N65, N70, N61','acúmulo mensal: mês 1 com 50% do benefício (grupo de controle)','benefício N61 uniforme; sem ganho do Marketplace')
add('N72','Payback no pior caso (esforço máximo e custo/dia em dobro)',payback(hi*DIA*2,api*5+VM*USD+man*2,ben),lambda z:f"{z} meses",'E','N66, N70 com manutenção em dobro, N61','idem','idem')
add('N73','Resultado líquido no 1º ano, caso-base interno',ben*11.5-rec*12-inv,lambda z:f"R$ {z/1e3:,.1f} mil".replace('.',','),'E','N61×11,5 − N70×12 − N65','soma','mês 1 com 50% do benefício')
add('N74','Custo em caixa incremental por ano (API ×5 + hospedagem)',(api*5+VM*USD)*12,lambda z:f"R$ {z/1e3:,.1f} mil".replace('.',','),'E','(N67×5 + N68)×12','produto','esforço interno não é caixa incremental')
# --- Série mensal (slide 3): margem calculada dos aprovados e taxa de desconto
AP=v[v.st=='Aprovado']
for mth,g in AP.groupby('mes'):
    add(f'S_{mth}',f'Margem calculada {mth}',g.margem_contribuicao.sum()/g.receita_liquida.sum()*100,pc,'F','vendas aprovados','Σmargem/Σliq por mês')
    add(f'SD_{mth}',f'Desconto/receita bruta {mth}',g.desconto_reais.sum()/g.receita_bruta.sum()*100,pc,'F','vendas aprovados','Σdesc/Σbruta por mês')
# --- Margem calculada × margem realizada sobre a receita registrada (slide 3, v3)
# Receita registrada = receita líquida de todos os pedidos da base (aprovados, cancelados, aguardando), como a margem do relatório.
# Margem realizada = margem calculada − cancelamento − pendência − devolução (reembolso integral) − atendimento.
def mr(g):
    Lq=g.receita_liquida.sum(); Mg=g.margem_contribuicao.sum(); Ag=g[g.st=='Aprovado']; Rg=Ag[Ag.dev]
    cn=g[g.st=='Cancelado'].margem_contribuicao.sum(); pn=g[g.st=='Aguardando'].margem_contribuicao.sum()
    dv=(Rg.margem_contribuicao+Rg.custo_frete).sum(); tk=Ag.tk.sum()
    return dict(L=Lq,calc=Mg/Lq*100,real=(Mg-cn-pn-dv-tk)/Lq*100,dev=dv/Lq*100,can=cn/Lq*100,pen=pn/Lq*100,ate=tk/Lq*100)
BASE_M='vendas + atendimento, todos os status'
r23=mr(y)
add('M01','Receita líquida registrada 2023 (todos os status)',r23['L'],mi,'F','vendas: receita_liquida, todos os status','soma')
add('M02','Margem calculada sobre a receita registrada 2023',r23['calc'],pc,'F',BASE_M,'Σmargem ÷ Σreceita líquida, todos os status')
add('M03','Margem realizada sobre a receita registrada 2023',r23['real'],pc,'E',BASE_M,'(Σmargem − cancelamento − pendência − devolução − atendimento) ÷ Σreceita líquida',PREM_DEV)
add('M04','Diferença calculada − realizada 2023',r23['calc']-r23['real'],lambda z:f"{z:.2f}".replace('.',',')+" p.p.",'E','M02−M03','subtração','idem')
for k,idn,lab,tg in [('dev','M05','Devolução','E'),('can','M06','Cancelamento','F'),('pen','M07','Pendência','F'),('ate','M08','Atendimento','E')]:
    add(idn,f'{lab}: p.p. da receita registrada 2023',r23[k],lambda z:f"{z:.2f}".replace('.',',')+" p.p.",tg,BASE_M,'perda ÷ Σreceita líquida registrada','ver N21' if k=='dev' else '—')
for sm in ['S1','S2']:
    add(f'M09_{sm}',f'Margem realizada sobre a receita registrada {sm} 2023',mr(y[y.smt==sm])['real'],pc,'E',BASE_M,'idem M03','idem')
for sm,g in [('S1',y[y.smt=='S1']),('S2',y[y.smt=='S2']),('S2sn',y[(y.smt=='S2')&(y.mes!='2023-11')])]:
    add(f'M10_{sm}',f'Margem calculada sobre a receita registrada {sm} 2023'+(' (S2 sem novembro)' if sm=='S2sn' else ''),mr(g)['calc'],pc,'F',BASE_M,'idem M02')
for mth,g in v.groupby('mes'):
    rr=mr(g)
    add(f'SC_{mth}',f'Margem calculada sobre a receita registrada {mth}',rr['calc'],pc,'F',BASE_M,'idem M02')
    add(f'SR_{mth}',f'Margem realizada sobre a receita registrada {mth}',rr['real'],pc,'E',BASE_M,'idem M03',PREM_DEV)
# --- Ponte S1->S2 (apêndice A1), método do deck
g1=A[A.smt=='S1']; g2=A[A.smt=='S2']
t=lambda g,c: g[c].sum()/g.receita_bruta.sum()
ef_d=-(t(g2,'desconto_reais')-t(g1,'desconto_reais'))*g2.receita_bruta.sum(); ef_f=-(t(g2,'custo_frete')-t(g1,'custo_frete'))*g2.receita_bruta.sum(); ef_p=-(t(g2,'custo_produto')-t(g1,'custo_produto'))*g2.receita_bruta.sum()
dmc=g2.margem_contribuicao.sum()-g1.margem_contribuicao.sum()
add('A1_mc1','Contribuição calculada S1 2023 (aprovados)',g1.margem_contribuicao.sum(),mi,'F','vendas aprovados','Σmargem'); add('A1_mc2','Contribuição calculada S2 2023 (aprovados)',g2.margem_contribuicao.sum(),mi,'F','idem','Σmargem')
add('A1_esc','Ponte: efeito escala',dmc-ef_d-ef_f-ef_p,mil,'F','idem','resíduo'); add('A1_desc','Ponte: efeito desconto',ef_d,mil,'F','idem','−Δ(desc/bruta)×bruta S2')
add('A1_fr','Ponte: efeito frete',ef_f,mil,'F','idem','−Δ(frete/bruta)×bruta S2'); add('A1_cp','Ponte: efeito custo do produto',ef_p,mil,'F','idem','−Δ(custo/bruta)×bruta S2')
# --- Custo do produto por R$ 100 de receita bruta, mês a mês (apêndice A7)
for mth,g in AP.groupby('mes'):
    add(f'CP_{mth}',f'Custo do produto por R$ 100 de receita bruta {mth}',g.custo_produto.sum()/g.receita_bruta.sum()*100,lambda z:f"R$ {z:.2f}".replace('.',','),'F','vendas aprovados: custo_produto, receita_bruta','Σcusto/Σbruta×100 por mês')
liq_bruta_s2=g2.receita_liquida.sum()/g2.receita_bruta.sum()
add('CP_need','Alta do custo por R$ 100 de bruta necessária para explicar a queda S1→S2',abs(val('N07')-val('N06'))*liq_bruta_s2,lambda z:f"R$ {z:.2f}".replace('.',','),'E','N06, N07, receita líquida/bruta S2','|Δmargem| × (Σliq/Σbruta S2)','efeito isolado do custo, demais fatores constantes')
# --- Mix de canais (apêndice A8)
sh1=g1.groupby('canal').receita_liquida.sum()/g1.receita_liquida.sum(); sh2=g2.groupby('canal').receita_liquida.sum()/g2.receita_liquida.sum()
mg1=g1.groupby('canal').apply(lambda d:d.margem_contribuicao.sum()/d.receita_liquida.sum()); mg2=g2.groupby('canal').apply(lambda d:d.margem_contribuicao.sum()/d.receita_liquida.sum())
mgA=A.groupby('canal').apply(lambda d:d.margem_contribuicao.sum()/d.receita_liquida.sum())
for c in sh1.index:
    add(f'MX_s1_{c}',f'Participação na receita líquida S1: {c}',sh1[c]*100,pc,'F','vendas aprovados: canal, receita_liquida','Σliq canal/Σliq S1')
    add(f'MX_s2_{c}',f'Participação na receita líquida S2: {c}',sh2[c]*100,pc,'F','idem','Σliq canal/Σliq S2')
    add(f'MX_mg_{c}',f'Margem calculada 2023: {c}',mgA[c]*100,pc,'F','idem','Σmargem/Σliq')
add('MX_efeito','Efeito mix na variação da margem S1→S2',((sh2-sh1)*mg1).sum()*100,lambda z:f"{z:+.3f}".replace('.',',')+" p.p.",'F','idem','Σ(wS2 − wS1) × mS1')
add('MX_interno','Efeito dentro dos canais na variação S1→S2',((mg2-mg1)*sh2).sum()*100,lambda z:f"{z:+.3f}".replace('.',',')+" p.p.",'F','idem','Σ wS2 × (mS2 − mS1)')
add('MX_contraf','Margem S2 com o mix de S1',(sh1*mg2).sum()*100,pc,'F','idem','Σ wS1 × mS2')
# --- Tetos (apêndice A2)
for cap in [0.15,0.20,0.25,0.30]:
    exc=(K.desconto_reais-cap*K.receita_bruta).clip(lower=0); aff=K.pct>cap
    for lab,m in [('ano',K.dt.dt.month>0),('foranov',~nov)]:
        G=exc[m].sum(); add(f'A2_{int(cap*100)}_{lab}_g',f'Teto {cap:.0%} {lab}: ganho',G,mil,'E','vendas aprovados não devolvidos 2023','Σmax(0,desc−teto×bruta)','volume constante')
        add(f'A2_{int(cap*100)}_{lab}_a',f'Teto {cap:.0%} {lab}: pedidos afetados',(aff&m).sum()/m.sum()*100,pc1,'F','idem','%')
        add(f'A2_{int(cap*100)}_{lab}_e',f'Teto {cap:.0%} {lab}: equilíbrio',G/(K.loc[aff&m,'margem_contribuicao']+exc[aff&m]).sum()*100,pc1,'E','idem','ganho/margem afetados após teto','idem')
# --- Testes de concentração (slide 6, apêndice A3)
A3=A.copy(); A3['forn']=A3.fornecedor_id; A3['defeito']=A3.motivo_devolucao=='Produto com defeito'
y3=y.copy(); y3['band']=pd.cut(y3.pct,[-0.001,0.0001,0.15,0.25,0.40001],labels=['0','0-15','15-25','25-40'])
def faixa_p(df,dim,flag,lab,idn,base):
    r=df.groupby(dim)[flag].mean()*100; p=stats.chi2_contingency(pd.crosstab(df[dim],df[flag]))[1]
    add(idn+'_min',f'{lab}: menor taxa por {dim}',r.min(),pc1,'F',base,'taxa por grupo'); add(idn+'_max',f'{lab}: maior taxa por {dim}',r.max(),pc1,'F',base,'taxa por grupo')
    add(idn+'_p',f'{lab} × {dim}: p-valor',p,lambda z:f"p = {z:.2f}".replace('.',','),'F',base,'qui-quadrado')
y3['canc']=y3.st=='Cancelado'; y3['pend']=y3.st=='Aguardando'
for dim,cod in [('canal','can'),('categoria','cat'),('metodo_pagamento','pag'),('quantidade','qtd')]:
    faixa_p(A3,dim,'dev','Devolução',f'T_dev_{cod}','vendas aprovados 2023')
    faixa_p(y3,dim,'canc','Cancelamento',f'T_can_{cod}','vendas 2023 todos status')
    faixa_p(y3,dim,'pend','Pendência',f'T_pen_{cod}','vendas 2023 todos status')
faixa_p(A3,'forn','defeito','Defeito',f'T_dev_for','vendas+estoque aprovados 2023')
faixa_p(y3,'band','canc','Cancelamento',f'T_can_des','vendas 2023 todos status'); faixa_p(y3,'band','pend','Pendência',f'T_pen_des','vendas 2023 todos status')
# --- Qualidade de dados (apêndice A4)
add('Q1','Participação do maior cliente (CLI-11830) nos pedidos',v.customer_id.value_counts().iloc[0]/len(v)*100,pc1,'F','vendas: customer_id','%')
add('Q2','Clientes distintos em vendas',v.customer_id.nunique(),n0,'F','vendas','contagem')
mk=pd.read_csv(D+'Marketing.csv',encoding='utf-8-sig'); add('Q3','Conversões de campanhas iniciadas em 2023',mk[pd.to_datetime(mk.data_inicio).dt.year==2023].conversoes.sum()/1e6,lambda z:f"{z:.1f} mi".replace('.',','),'F','marketing: conversoes','soma')
add('Q4','Pedidos Cancelados e Devolvidos ao mesmo tempo',((v.st=='Cancelado')&v.dev).sum(),n0,'F','vendas','contagem')
add('Q5','Tickets vinculados abertos antes do pedido',(lambda t_:(pd.to_datetime(t_.data_abertura)<t_.dt).mean()*100)(a.merge(v[['order_id','dt']],on='order_id')),pc1,'F','atendimento×vendas','%')
add('Q6','Textos distintos em atendimento.texto_cliente',a.texto_cliente.nunique(),n0,'F','atendimento','contagem')
# --- Fator de encargos e benefícios: memória de cálculo (justifica ENC = 1,8)
# Fontes: Lei 8.212/91 art. 22 I (INSS 20%) e II (RAT 1-3%); FPAS 515 comércio: salário-educação 2,5% + INCRA 0,2% + SESC 1,5% + SENAC 1,0% + SEBRAE 0,6% = 5,8%;
# Lei 8.036/90 art. 15 (FGTS 8%) e art. 18 §1º (multa 40%); Lei 4.090/62 (13º); CF art. 7º XVII (férias + 1/3); Lei 7.418/85 (VT: empregado custeia até 6% do salário);
# VR médio R$ 649/mês (Pluxee, jan/2026); plano de saúde R$ 520-610/vida/mês por porte (Axenya, com dados IESS/ANS, 2026); LC 123/06 (Simples: até R$ 4,8 mi/ano).
add('X01','Parâmetro externo: vale-refeição médio mensal (Pluxee, jan/2026)',649,lambda z:f"R$ {z:,.0f}".replace(',','.'),'E','pesquisa Pluxee 2026','—','média nacional')
add('X02','Parâmetro externo: plano de saúde por vida, PME 30–99 vidas (Axenya/IESS/ANS 2026)',560,lambda z:f"R$ {z:,.0f}".replace(',','.'),'E','Axenya 2026','—','titular')
add('X03','Parâmetro legal: teto de custeio do VT pelo empregado (6% de R$ 6.000)',0.06*SAL,lambda z:f"R$ {z:,.0f}".replace(',','.'),'E','Lei 7.418/1985','6% × salário','—')
add('X04','Parâmetro legal: limite de receita do Simples Nacional',4.8e6,mi,'E','LC 123/2006 (LC 155/2016)','—','—')
rb23=y.receita_bruta.sum()
add('E01','Receita bruta 2023 (todos os status) — acima do teto do Simples (R$ 4,8 mi) ⇒ contribuição patronal integral',rb23,mi,'F','vendas.csv','soma','LC 123/2006: limite do Simples de R$ 4,8 mi/ano')
P13=1/12; PFER=(1/12)*(4/3); BASE=1+P13+PFER
def fator(rat, multa, vr_meses, saude, vr=649.0):
    prov=P13+PFER; inss=(0.20+rat+0.058)*BASE; fgts=0.08*BASE; mult=0.40*fgts if multa else 0.0
    ben_=(vr*vr_meses/12+saude)/SAL
    return dict(prov=prov,inss=inss,fgts=fgts,multa=mult,ben=ben_,total=1+prov+inss+fgts+mult+ben_)
cen={'min':fator(0.01,False,0,0),'central':fator(0.02,False,11,560),'multa':fator(0.02,True,11,560),'max':fator(0.03,True,12,610)}
c=cen['central']
add('E02','13º salário (provisão mensal)',P13*100,pc,'E','Lei 4.090/1962','1/12','—')
add('E03','Férias + 1/3 (provisão mensal)',PFER*100,pc,'E','CF art. 7º XVII','(1/12)×(4/3)','—')
add('E04','INSS patronal 20% + RAT 2% + terceiros 5,8%, sobre salário+13º+férias',c['inss']*100,pc,'E','Lei 8.212/91 art. 22; FPAS 515','27,8% × 1,1944','RAT no ponto médio da faixa legal (1–3%)')
add('E05','FGTS 8% sobre salário+13º+férias',c['fgts']*100,pc,'E','Lei 8.036/90 art. 15','8% × 1,1944','—')
add('E06','Vale-refeição (R$ 649 × 11 meses ÷ 12) / salário',649*11/12/SAL*100,pc,'E','Pluxee, jan/2026','R$ 594,92 ÷ R$ 6.000','sem VR no mês de férias')
add('E07','Plano de saúde (R$ 560/vida/mês) / salário',560/SAL*100,pc,'E','Axenya (IESS/ANS), PME 30–99 vidas, 2026','R$ 560 ÷ R$ 6.000','titular apenas; VT com custo nulo acima de 6% do salário')
add('E08','Fator de encargos e benefícios: cenário central',c['total'],lambda z:f"{z:.2f}".replace('.',','),'E','E02–E07','1 + E02 + E03 + E04 + E05 + E06 + E07','regime normal (E01); sem multa rescisória; adotado 1,8 (arredondamento)')
add('E09','Fator: mínimo legal (RAT 1%, sem benefícios, sem multa)',cen['min']['total'],lambda z:f"{z:.2f}".replace('.',','),'E','idem','idem','piso: só encargos obrigatórios')
add('E10','Fator: central + provisão de multa FGTS 40%',cen['multa']['total'],lambda z:f"{z:.2f}".replace('.',','),'E','idem','E08 + 40% × E05','desligamento sem justa causa')
add('E11','Fator: máximo (RAT 3%, multa, VR 12 meses, saúde R$ 610)',cen['max']['total'],lambda z:f"{z:.2f}".replace('.',','),'E','idem','idem','teto do intervalo')
for idn,fk in [('E12','min'),('E13','max'),('E14','multa')]:
    fct=cen[fk]['total']; dia=SAL*fct/DU
    add(idn,f'Payback com fator {fk} ({fct:.2f})'.replace('.',','),payback(mid*dia,api*5+VM*USD+2*dia,ben),lambda z:f"{z} meses",'E','N65/N70 recalculados com o fator','acúmulo mensal, mês 1 a 50%','idem N71')
    add(idn+'b',f'Investimento (ponto médio) com fator {fk}',mid*dia,lambda z:f"R$ {z/1e3:,.1f} mil".replace('.',','),'E','N63/N64 × custo/dia','produto','idem')
# --- Fechamento: demonstração do resultado de contribuição, como está × pro forma (DF_*), em R$, base 2023
# Pro forma = ano cheio com as propostas, volume de 2023. Teto aplicado no checkout a todos os aprovados fora de novembro;
# o reembolso dos devolvidos sobe junto (quem devolve recebe de volta o que pagou). Frete MP = N46 (pedidos mantidos).
CPd=y[y.st!='Aprovado']; nov_A=A.dt.dt.month==11; nov_R=R.dt.dt.month==11
xa=((A.desconto_reais-0.2*A.receita_bruta).clip(lower=0))[~nov_A].sum()
xr=((R.desconto_reais-0.2*R.receita_bruta).clip(lower=0))[~nov_R].sum()
REC=val('N70')*12
ant=dict(RB=y.receita_bruta.sum(),CP=CPd.receita_bruta.sum(),DESC=A.desconto_reais.sum(),DEV=R.receita_liquida.sum(),
         CMV=K.custo_produto.sum(),FR=A.custo_frete.sum(),TK=A.tk.sum(),SOL=0.0)
pro=dict(ant); pro['DESC']=ant['DESC']-xa; pro['DEV']=ant['DEV']+xr; pro['FR']=ant['FR']-val('N46'); pro['SOL']=REC
def tot(d):
    d=dict(d); d['RLR']=d['RB']-d['CP']-d['DESC']-d['DEV']; d['MR']=d['RLR']-d['CMV']-d['FR']-d['TK']; d['PCT']=d['MR']/d['RLR']*100; d['RES']=d['MR']-d['SOL']; return d
ant=tot(ant); pro=tot(pro)
LAB={'RB':'Receita bruta de pedidos registrados','CP':'Cancelados e pendentes (receita bruta)','DESC':'Descontos concedidos (aprovados)','DEV':'Devoluções com reembolso integral',
     'RLR':'Receita líquida realizada','CMV':'Custo dos produtos vendidos (pedidos mantidos)','FR':'Frete pago (entregas e ida dos devolvidos)','TK':'Custo de atendimento',
     'MR':'Margem de contribuição realizada','PCT':'Margem sobre a receita líquida realizada','SOL':'Custo recorrente da solução','RES':'Resultado de contribuição'}
rs=lambda z:f"R$ {z:,.0f}".replace(',','.')
for k_ in LAB:
    fm=pc if k_=='PCT' else rs
    add(f'DF_{k_}_antes',LAB[k_]+' · como está 2023',ant[k_],fm,'F' if k_ in ('RB','CP','DESC','CMV','FR') else 'E','vendas + atendimento 2023','ver notas explicativas do fechamento',PREM_DEV)
    add(f'DF_{k_}_pro',LAB[k_]+' · pro forma, ano cheio',pro[k_],fm,'E','idem','idem','volume de 2023 (testado); teto de 20% fora de nov; regra de frete no Marketplace')
    dv=pro[k_]-ant[k_]
    add(f'DF_{k_}_var',LAB[k_]+' · variação',dv,(lambda z:f"{z:+.2f}".replace('.',',')+" p.p.") if k_=='PCT' else (lambda z:f"{z:+,.0f}".replace(',','.')),'E','pro forma − como está','subtração','idem')
add('DF_X_A','Teto 20% fora de nov: desconto evitado em todos os aprovados',xa,rs,'E','vendas aprovados 2023','Σ max(0, desconto − 20% × bruta), exceto nov','volume constante')
add('DF_X_R','Teto 20% fora de nov: reembolso adicional dos devolvidos',xr,rs,'E','vendas aprovados devolvidos 2023','idem, só devolvidos','quem devolve recebe o que pagou')
add('DF_MP_R','Frete MP ≥ R$ 250 em pedidos devolvidos (não contabilizado)',R[(R.canal=='Marketplace')&(R.receita_liquida>=250)].custo_frete.sum(),rs,'F','vendas MP devolvidos 2023','Σ custo_frete','fora do pro forma, por coerência com N46')
add('DF_CMV_dev','Custo do produto dos devolvidos, que volta ao estoque',R.custo_produto.sum(),rs,'F','vendas aprovados devolvidos','Σ custo_produto')
add('DF_Y1_desc','1º ano: desconto evitado (mês 1 a 50%)',xa/12*11.5,rs,'E','DF_X_A ÷ 12 × 11,5','produto','mês 1 com grupo de controle')
add('DF_Y1_dev','1º ano: reembolso adicional (mês 1 a 50%)',xr/12*11.5,rs,'E','DF_X_R ÷ 12 × 11,5','produto','idem')
add('DF_Y1_res','1º ano, caso interno: variação do resultado',(xa-xr)/12*11.5-REC-val('N65'),rs,'E','DF_Y1_desc − DF_Y1_dev − N70×12 − N65','soma','= N73')
add('DF_n_all','Pedidos 2023, todos os status',len(y),n0,'F','vendas','contagem')
add('DF_FR_K','Frete das entregas mantidas 2023',K.custo_frete.sum(),rs,'F','vendas aprovados não devolvidos','Σ custo_frete')
add('DF_FR_R','Frete de ida dos pedidos devolvidos 2023',R.custo_frete.sum(),rs,'F','vendas aprovados devolvidos','Σ custo_frete')
add('DF_perda_reais','Perda depois do pedido 2023, em reais (= N25)',val('N25'),rs,'E','N19+N20+N21+N24','soma',PREM_DEV)
add('DF_SOL_mes','Custo recorrente da solução por mês, sem arredondar (= N70)',val('N70'),lambda z:f"R$ {z:,.2f}".replace(',','X').replace('.',',').replace('X','.'),'E','N70','—','ver N67–N69')
add('DF_INV_reais','Implantação da solução, em reais (= N65)',val('N65'),rs,'E','N65','65,5 pessoa-dia × N62','ver N62–N64')
add('DF_DIA','Custo por pessoa-dia, sem arredondar (= N62)',val('N62'),lambda z:f"R$ {z:,.2f}".replace(',','X').replace('.',',').replace('X','.'),'E','N62','R$ 6.000 × 1,8 ÷ 21','fator de encargos 1,8')
RLreg_a=y.receita_liquida.sum(); RLreg_p=RLreg_a+xa
add('DF_PCTREG_antes','Margem realizada ÷ receita líquida registrada · como está (= M03 sobre 2023)',ant['MR']/RLreg_a*100,pc,'E','DF_MR_antes ÷ Σ receita líquida registrada','divisão',PREM_DEV)
add('DF_PCTREG_pro','Margem realizada ÷ receita líquida registrada · pro forma',pro['MR']/RLreg_p*100,pc,'E','DF_MR_pro ÷ (receita líquida registrada + DF_X_A)','divisão','idem')
add('DF_PCTREG_var','Margem realizada ÷ receita líquida registrada · variação',pro['MR']/RLreg_p*100-ant['MR']/RLreg_a*100,lambda z:f"{z:+.2f}".replace('.',',')+" p.p.",'E','subtração','—','idem')
add('DF_calc_rel','Margem calculada que o relatório mostra (todos os pedidos)',reg,rs,'F','vendas todos status','Σ margem_contribuicao','= N18')
cl=pd.read_csv(D+'Clientes.csv',encoding='utf-8-sig'); add('Q7','Clientes no cadastro (clientes.csv)',len(cl),n0,'F','clientes.csv','contagem')
out=pd.DataFrame(L); out.to_csv('livro_de_numeros.csv',index=False,sep=';',encoding='utf-8-sig')
with open('livro_de_numeros.md','w',encoding='utf-8') as fh:
    fh.write('| ID | Número | Valor | Marca | Base / colunas | Cálculo | Premissa |\n|---|---|---|---|---|---|---|\n')
    for r in L: fh.write(f"| {r['id']} | {r['numero']} | **{r['valor']}** | {r['marca']} | {r['base_colunas']} | {r['calculo']} | {r['premissa']} |\n")
print(out[['id','numero','valor','marca']].to_string())
print('\nTotal:',len(out),'· F:',(out.marca=='F').sum(),'· E:',(out.marca=='E').sum())
