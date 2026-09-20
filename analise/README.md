# Análise do case — scripts do squad

Os quatro scripts desta pasta são o trabalho de análise que **antecede** o
protótipo. Eles não fazem parte do MarginGuard: o motor em `vertice/` não
importa nada daqui, e a suíte de testes não depende deles.

Estão no repositório por um motivo específico — **procedência**. É
`livro_de_numeros.py` que produz os IDs (`N02`, `N03`, `N18`…) contra os quais
os 35 testes de aceite em `tests/test_aceite_livro_de_numeros.py` conferem o
motor. Sem esta pasta, esses IDs seriam números sem origem declarada.

## Os quatro scripts

| Script | O que faz |
|---|---|
| `auditoria_dos_dados.py` | Dicionário, identidades contábeis e qualidade das cinco bases. Grava `auditoria_dos_dados.json`. |
| `livro_de_numeros.py` | **Todo número do deck sai daqui.** Gera `livro_de_numeros.csv` e `.md` com 358 entradas identificadas. |
| `memorias_de_calculo.py` | Recalcula a demonstração de resultado (como está e pro forma), o business case, o payback — e confere cada total contra o Livro. Para com erro se divergir. |
| `checar_numeros.py` | Confere o deck (`.pptx`) contra o Livro: todo número do slide precisa ter lastro num ID ou estar declarado como derivado. |

## Como rodar

Os scripts recebem a pasta dos CSVs como primeiro argumento. A partir da raiz
do repositório:

```bash
python analise/auditoria_dos_dados.py data/
```

```bash
python analise/livro_de_numeros.py data/
```

`memorias_de_calculo.py` recebe também o CSV gerado pelo anterior:

```bash
python analise/memorias_de_calculo.py data/ livro_de_numeros.csv
```

Os arquivos de saída são gravados na pasta de onde você rodar o comando.

## O que foi verificado

Rodados contra o `data/` deste repositório:

- `livro_de_numeros.py` produz **358 números** e devolve `N02 = 23.388` e
  `N03 = R$ 15.966.340,87` — exatamente o que
  `tests/test_aceite_livro_de_numeros.py` exige do motor. Os dois lados batem
  à casa do centavo.
- `memorias_de_calculo.py` fecha com **57 valores conferidos, 0 divergências**
  e **4 de 4 identidades**. A margem realizada de R$ 7.204.820 é a mesma que a
  ferramenta `perda_pos_pedido` do motor devolve.
- `auditoria_dos_dados.py` lê as cinco bases (Vendas 27.759 linhas,
  Atendimento 35.841, Estoque 5.000, Marketing 3.500, Clientes 15.000).

## Duas ressalvas

**`checar_numeros.py` não roda a partir deste repositório.** Ele precisa de
`python-pptx`, que não está em `requirements.txt`, e do arquivo `.pptx` do
deck, que não está versionado aqui. Fica como registro do método de conferência
que foi usado, não como passo reproduzível.

**Os scripts leem `Vendas.csv` com inicial maiúscula**, e os arquivos em
`data/` são minúsculos. Funciona no Windows e no WSL sobre `/mnt/c`, porque
esses sistemas de arquivos não distinguem maiúsculas — mas falharia num Linux
nativo. Os scripts estão aqui **como foram escritos e usados pelo squad**, sem
adaptação: mexer neles descaracterizaria o artefato que gerou os números
publicados.
