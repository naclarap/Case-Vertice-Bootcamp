# Scripts · Projeto Vértice

Quatro scripts em Python que geram e conferem todos os números do trabalho.
Rodam sobre as cinco bases do case, em `agente/data/`, sem internet e sem chave
de API.

Foram escritos e usados pelo squad na fase de análise, **antes** do protótipo.
Estão aqui por procedência: é `livro_de_numeros.py` que produz os IDs (`N02`,
`N03`, `N18`…) contra os quais os 35 testes de aceite do motor conferem, em
`agente/tests/test_aceite_livro_de_numeros.py`.

| Script | O que faz | Saída |
|---|---|---|
| `livro_de_numeros.py` | Calcula os 358 números do trabalho a partir das bases: margem no tempo, árvore de perdas, testes de desconto e volume, frete, business case e demonstração do resultado. Cada número sai com ID, valor, marca de confiança, base, cálculo e premissa | `livro_de_numeros.csv` e `livro_de_numeros.md` |
| `memorias_de_calculo.py` | Refaz, conta por conta, cada linha da demonstração do resultado (como está e pro forma), os custos da solução, o payback e o resultado do 1º ano. Confere 57 totais com o Livro e quatro identidades contábeis; se algo divergir, para com erro | `memorias_de_calculo.json` |
| `auditoria_dos_dados.py` | Audita as cinco bases: tamanho, nulos, período, SHA-256, identidades de valor, distribuição por status e dicionário coluna a coluna | `auditoria_dos_dados.json` |
| `checar_numeros.py` | Extrai todo número dos slides e das notas do deck e verifica se existe no Livro. Números derivados precisam estar declarados com a conta que os produz; também procura valores de premissas abandonadas | relatório no terminal |

## Como rodar

A partir da raiz do repositório, com Python 3.10 ou superior:

```bash
pip install pandas numpy scipy
```

```bash
python analise/livro_de_numeros.py agente/data/
```

```bash
python analise/memorias_de_calculo.py agente/data/ livro_de_numeros.csv
```

```bash
python analise/auditoria_dos_dados.py agente/data/
```

Os três aceitam a pasta dos CSVs como primeiro argumento, caso ela esteja em
outro lugar. Os arquivos de saída são gravados na pasta em que o script for
executado.

## Ordem e dependências

`livro_de_numeros.py` vem primeiro: `memorias_de_calculo.py` confere contra o
CSV que ele gera. `auditoria_dos_dados.py` é independente. Nenhum script altera
as bases; todos só leem.

## Resultado esperado

| Verificação | Resultado |
|---|---|
| Livro gerado de novo, comparado com o entregue | idêntico · 358 números (219 ● calculados, 139 ◐ estimados) |
| Memórias contra o Livro | 57 valores, 0 divergências · 4 de 4 identidades |
| Deck contra o Livro | 520 números, 0 sem lastro, 0 frases proibidas |
| Identidades de valor das bases | 100% das linhas |

## Premissa que atravessa os cálculos

Devolução é tratada como reembolso integral de todo pedido devolvido: o cliente
recebe o que pagou, o item volta ao estoque e o frete de ida se perde. As
demais premissas estão no Artefato 4 e na parte A do documento de regras e
memórias de cálculo — e, do lado do protótipo, em
[agente/PREMISSAS.md](../agente/PREMISSAS.md).

## Duas ressalvas neste repositório

**`checar_numeros.py` não roda a partir daqui.** Ele precisa de `python-pptx` e
do arquivo `.pptx` do deck, e nenhum dos dois está versionado neste
repositório. Fica como registro do método de conferência que foi usado, não
como passo reproduzível.

**Os scripts leem `Vendas.csv` com inicial maiúscula**, e os arquivos em
`agente/data/` são minúsculos. Funciona no Windows e no WSL sobre `/mnt/c`,
porque esses sistemas de arquivos não distinguem maiúsculas — mas falharia num
Linux nativo. Os scripts estão aqui **como foram escritos e usados pelo
squad**, sem adaptação: mexer neles descaracterizaria o artefato que gerou os
números publicados.
