/* Painéis do MarginGuard — relatório semanal, auditoria de dados e política
   de desconto, todos alimentados pela mesma API que o chat usa.

   Existe para que nada precise de terminal: o que antes era
   `python -m vertice.relatorio` ou uma chamada de ferramenta virou uma tela.
   Nenhum número é calculado aqui — tudo vem pronto de /api/*; este arquivo só
   formata (pt-BR) e desenha. */
(function(){
  "use strict";

  /* Navegação persistente: os seis destinos ficam sempre à vista na barra
     lateral, e qualquer um alcança qualquer outro em um clique.

     O MarginGuard é destino E atalho. Como destino, tem tela própria com a
     conversa inteira; como atalho, o botão flutuante abre a MESMA conversa
     por cima de qualquer outra tela. É uma conversa só: o corpo do chat é
     movido entre os dois hospedeiros (ver "Painel de chat" em script.js), em
     vez de existirem duas instâncias com históricos diferentes. */
  var VIEWS = ['visao', 'relatorio', 'auditoria', 'politica', 'monitoramento', 'marginguard'];
  // A proposta que o monitoramento está exibindo: é ela que a criação do
  // experimento referencia, e guardá-la evita reler a tela para achar o id.
  var propostaEmTeste = null;
  // Propostas paradas em Aprovação, esperando a decisão de outra pessoa.
  var filaAprovacao = [];
  var TELAS = {
    visao:         { nome: 'Visão geral',           carrega: function(){ carregarVisao(); } },
    relatorio:     { nome: 'Relatório por período', carrega: function(){ carregarRelatorio(); } },
    auditoria:     { nome: 'Auditoria de dados',    carrega: function(){ carregarAuditoria(); } },
    politica:      { nome: 'Política de desconto',  carrega: function(){ carregarPolitica(); } },
    monitoramento: { nome: 'Monitoramento',         carrega: function(){ carregarMonitoramento(); } },
    marginguard:   { nome: 'MarginGuard',           carrega: null }
  };
  var viewAtiva = null;
  var carregado = {};           // evita refetch a cada troca de aba
  var el = function(id){ return document.getElementById(id); };

  /* ------------------------------------------------ formatação (só visual) */
  function brl(v, casas){
    if(v === null || v === undefined) return '—';
    var n = Number(v);
    var s = Math.abs(n).toLocaleString('pt-BR', {
      minimumFractionDigits: casas === undefined ? 2 : casas,
      maximumFractionDigits: casas === undefined ? 2 : casas
    });
    // Sinal antes do símbolo: "R$ -5.782,86" não é como se escreve em pt-BR.
    return (n < 0 ? '−' : '') + 'R$ ' + s;
  }
  function pct(v, casas){
    if(v === null || v === undefined) return '—';
    return Number(v).toFixed(casas === undefined ? 2 : casas).replace('.', ',') + '%';
  }
  function pp(v, casas){
    if(v === null || v === undefined) return '—';
    return Number(v).toFixed(casas === undefined ? 2 : casas).replace('.', ',') + ' p.p.';
  }
  function num(v){
    if(v === null || v === undefined) return '—';
    return Number(v).toLocaleString('pt-BR');
  }
  function esc(s){
    var d = document.createElement('div');
    d.textContent = s === null || s === undefined ? '' : String(s);
    return d.innerHTML;
  }
  /* Regra de interface: toda data mostrada ao usuário sai em DD/MM/AAAA. O
     valor original do backend (AAAA-MM-DD) não é alterado em lugar nenhum —
     só a apresentação. Fatiar a string em vez de usar new Date() é de
     propósito: "2023-01-01" vira 31/12/2022 quando o navegador interpreta a
     data como UTC e converte para o fuso local. */
  function data(iso){
    if(!iso) return '—';
    var m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? m[3] + '/' + m[2] + '/' + m[1] : String(iso);
  }
  // Data com hora ("2024-01-26 10:53:49") — a hora acompanha quando existe.
  function dataHora(iso){
    if(!iso) return '—';
    var t = String(iso);
    var hora = t.match(/(\d{2}:\d{2}(?::\d{2})?)/);
    var d = data(t);
    return hora ? d + ' ' + hora[1] : d;
  }
  // AAAA-MM-DD <-> Date, sem passar por fuso horário.
  function paraISO(d){
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) +
           '-' + ('0' + d.getDate()).slice(-2);
  }
  function paraData(iso){
    var m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
  }
  function diasEntre(isoA, isoB){
    var a = paraData(isoA), b = paraData(isoB);
    if(!a || !b) return null;
    return Math.round((b - a) / 86400000) + 1;   // janela fechada nos dois lados
  }

  function kpi(rotulo, valor, contexto){
    var longo = String(valor).length > 12 ? ' longo' : '';
    // Valor sem dígito nenhum é texto, e texto pode quebrar entre palavras.
    // Número não pode: "R$ 1.450.067,34" quebrado depois do "R$" parece erro
    // de dado, e foi exatamente assim que "Aguardando aprovação" saiu cortado.
    if(!/[0-9]/.test(String(valor))) longo += ' texto';
    return '<div class="kpi"><div class="kpi-lbl">' + esc(rotulo) + '</div>' +
           '<div class="kpi-val' + longo + '">' + esc(valor) + '</div>' +
           (contexto ? '<div class="kpi-ctx">' + esc(contexto) + '</div>' : '') +
           '</div>';
  }
  // Cor nunca sozinha: todo status leva ícone e rótulo junto.
  function chip(status){
    // "Requer leitura" é o estado de quem ACHOU algo que não é erro provado
    // (outlier, incoerência de domínio). Antes isso saía como "Sem problema".
    var m = { ok:['ok','✓','Sem problema'], revisar:['rev','◆','Requer leitura'],
              atencao:['warn','▲','Atenção'], critico:['crit','✕','Crítico'] };
    var c = m[status] || m.revisar;
    return '<span class="pill ' + c[0] + '">' + c[1] + ' ' + c[2] + '</span>';
  }
  function delta(valor, sufixo, bomQuandoSobe){
    if(valor === null || valor === undefined) return '—';
    var bom = (valor >= 0) === (bomQuandoSobe !== false);
    var sinal = valor > 0 ? '+' : (valor < 0 ? '−' : '');
    return '<span class="delta ' + (bom ? 'sobe' : 'desce') + '">' + sinal +
           Math.abs(Number(valor)).toFixed(2).replace('.', ',') + ' ' + sufixo + '</span>';
  }
  /* ------------------------------------------------ gráficos (sem canvas)
     Divs com altura proporcional, no padrão de cascata e barras do design
     system da Vértice: barra é bloco com altura em %, rótulo em mono
     maiúsculo sob uma hairline, e a revelação anima só a altura/largura.
     Nenhuma biblioteca externa. */

  // Valor curto para caber sob a barra: R$ 1,2 mi / R$ 84,3 mil / R$ 512.
  function brlCurto(v){
    if(v === null || v === undefined) return '—';
    var n = Number(v), a = Math.abs(n), s = n < 0 ? '−' : '';
    if(a >= 1e6) return s + 'R$ ' + (a / 1e6).toFixed(1).replace('.', ',') + ' mi';
    if(a >= 1e3) return s + 'R$ ' + (a / 1e3).toFixed(1).replace('.', ',') + ' mil';
    return s + 'R$ ' + a.toFixed(0);
  }

  /* Cascata: cada passo é uma barra flutuante entre o acumulado anterior e o
     novo. `total` zera o acumulado — é pilar (começa no chão), não degrau. */
  function graficoCascata(passos){
    var correndo = 0;
    var pontos = passos.map(function(p){
      var ini = p.total ? 0 : correndo;
      var fim = p.total ? p.valor : correndo + p.valor;
      correndo = p.total ? p.valor : fim;
      return { rotulo: p.rotulo, valor: p.valor, total: !!p.total,
               topo: Math.max(ini, fim), base: Math.min(ini, fim) };
    });
    var maximo = Math.max.apply(null, pontos.map(function(p){ return p.topo; }).concat([1]));

    var barras = pontos.map(function(p){
      var classe = p.total ? 'total' : (p.valor < 0 ? 'baixa' : 'sobe');
      return '<div class="cascata-col">' +
        '<span class="cascata-val ' + classe + '" style="bottom:calc(' +
          (p.topo / maximo * 100).toFixed(2) + '% + 6px)">' + esc(brlCurto(p.valor)) + '</span>' +
        '<span class="cascata-barra ' + classe + '" style="bottom:' +
          (p.base / maximo * 100).toFixed(2) + '%;height:' +
          ((p.topo - p.base) / maximo * 100).toFixed(2) + '%"></span>' +
        '</div>';
    }).join('');

    var rotulos = pontos.map(function(p){
      return '<span class="cascata-lbl">' + esc(p.rotulo) + '</span>';
    }).join('');

    return '<div class="grafico"><div class="cascata">' + barras + '</div>' +
           '<div class="cascata-eixo">' + rotulos + '</div></div>';
  }

  /* Barras verticais comparáveis entre si. `destaque` marca a pior linha —
     um acento por peça, como manda a marca. */
  function graficoBarras(itens){
    var maximo = Math.max.apply(null, itens.map(function(i){
      return Math.abs(Number(i.valor) || 0); }).concat([1]));
    var colunas = itens.map(function(i){
      var alt = (Math.abs(Number(i.valor) || 0) / maximo * 100).toFixed(2);
      return '<div class="barrav-col">' +
        '<span class="barrav-val">' + esc(i.texto) + '</span>' +
        '<span class="barrav-barra' + (i.destaque ? ' destaque' : '') +
          '" style="height:' + alt + '%"></span>' +
        '</div>';
    }).join('');
    var rotulos = itens.map(function(i){
      return '<span class="barrav-lbl">' + esc(i.rotulo) + '</span>';
    }).join('');
    return '<div class="grafico"><div class="barrav">' + colunas + '</div>' +
           '<div class="barrav-eixo">' + rotulos + '</div></div>';
  }

  function aviso(html){ return '<div class="aviso">' + html + '</div>'; }
  function carregando(){ return '<div class="vazio">Carregando…</div>'; }
  function falha(e){
    return '<div class="vazio erro">Não foi possível carregar: ' +
           esc(e && e.message ? e.message : e) + '</div>';
  }

  function pegar(url, opcoes){
    return fetch(url, opcoes).then(function(r){
      if(!r.ok){
        return r.json().catch(function(){ return {}; }).then(function(b){
          throw new Error(b.detail || ('HTTP ' + r.status));
        });
      }
      return r.json();
    });
  }

  /* ------------------------------------------------------ navegação */
  function mostrar(view){
    if(VIEWS.indexOf(view) === -1) view = VIEWS[0];
    viewAtiva = view;
    VIEWS.forEach(function(v){
      var secao = el('view-' + v);
      if(secao) secao.hidden = (v !== view);
    });
    el('scrollArea').scrollTop = 0;

    var tela = TELAS[view];
    document.title = tela.nome + ' · MarginGuard';
    document.querySelectorAll('.nav-item').forEach(function(b){
      b.classList.toggle('is-active', b.getAttribute('data-view') === view);
      b.setAttribute('aria-current', b.getAttribute('data-view') === view ? 'page' : 'false');
    });

    // O agente tem tela própria: o corpo do chat muda de hospedeiro, e o
    // atalho flutuante some (estaria sobre a própria conversa).
    if(window.MarginGuardUI) window.MarginGuardUI.modoTela(view === 'marginguard');

    if(tela.carrega && !carregado[view]){
      carregado[view] = true;
      tela.carrega();
    }
  }

  /* O título de cada tela é uma FRASE sobre o que ela achou, não o rótulo do
     menu — "3 pontos encontrados, do mais grave ao mais leve" diz algo;
     "Auditoria" só repete onde a pessoa clicou. Como a frase depende do dado,
     ela é escrita quando o dado chega. */
  function definirTitulo(view, eyebrow, titulo, sub){
    var cabeca = el('head-' + view);
    if(!cabeca) return;
    var e = cabeca.querySelector('.view-eyebrow');
    var t = cabeca.querySelector('.view-title');
    var s = cabeca.querySelector('.view-sub');
    if(e) e.textContent = eyebrow;
    if(t) t.textContent = titulo;
    if(s){ s.textContent = sub || ''; s.hidden = !sub; }
  }

  function navegar(view){
    // Navegar com o painel flutuante aberto fecha o painel e fica na tela
    // NOVA — por isso `false`: não é caso de restaurar a anterior.
    if(window.MarginGuardUI) window.MarginGuardUI.fecharChat(false);
    mostrar(view);
  }

  document.querySelectorAll('.nav-item').forEach(function(b){
    b.addEventListener('click', function(){ navegar(b.getAttribute('data-view')); });
  });

  /* Navegação fica fechada no celular e é aberta pelo botão da topbar; no
     desktop ela é sempre visível (CSS), e este par de funções não atrapalha. */
  var nav = el('nav'), navBtn = el('navBtn');
  function fecharNav(){ nav.classList.remove('aberta'); navBtn.setAttribute('aria-expanded','false'); }
  navBtn.addEventListener('click', function(){
    var abre = !nav.classList.contains('aberta');
    nav.classList.toggle('aberta', abre);
    navBtn.setAttribute('aria-expanded', abre ? 'true' : 'false');
  });
  document.querySelectorAll('.nav-item').forEach(function(b){
    b.addEventListener('click', fecharNav);
  });

  // script.js precisa saber em que tela a pessoa estava para voltar a ela
  // quando o painel de chat fecha.
  window.MarginGuardPainel = {
    viewAtual: function(){ return viewAtiva; },
    mostrar: mostrar
  };

  /* =========================================================== visão geral
     Cockpit executivo: um KPI principal com variação, os drivers de perda,
     os alertas da auditoria e as ações de maior valor. Nenhum número é
     calculado aqui — tudo vem de /api/visao-geral, que compõe ferramentas do
     motor determinístico. */

  /* Atalhos de período. `dias` é o tamanho da janela; a comparação com o
     período anterior de mesmo tamanho é feita pelo motor (margem_na_janela),
     não aqui. Mês e trimestre são 30 e 90 dias corridos — a base é diária, e
     mês-calendário exigiria outra ferramenta. */
  var PERIODOS = [
    { id: '7',  dias: 7,  rotulo: '7 dias' },
    { id: '30', dias: 30, rotulo: '30 dias' },
    { id: '90', dias: 90, rotulo: 'Trimestre' }
  ];
  PERIODOS.splice(2, 0, { id: 'mes', dias: 30, rotulo: 'Mês' });
  var periodoVisao = '30';

  function barraPeriodo(alvoId, selecionado, aoEscolher){
    var alvo = el(alvoId);
    if(!alvo) return;
    alvo.innerHTML = '<span class="eyebrow periodo-lbl">Período</span>' +
      '<span class="segmentado">' + PERIODOS.map(function(p){
        return '<button type="button" class="seg' + (p.id === selecionado ? ' is-active' : '') +
               '" data-periodo="' + p.id + '">' + esc(p.rotulo) + '</button>';
      }).join('') + '</span>';
    alvo.querySelectorAll('[data-periodo]').forEach(function(b){
      b.addEventListener('click', function(){ aoEscolher(b.getAttribute('data-periodo')); });
    });
  }

  function diasDoPeriodoId(id){
    var p = PERIODOS.filter(function(x){ return x.id === id; })[0];
    return p ? p.dias : 30;
  }

  function carregarVisao(){
    barraPeriodo('visaoPeriodo', periodoVisao, function(id){
      periodoVisao = id;
      carregarVisao();
    });
    var alvo = el('visaoConteudo');
    alvo.innerHTML = carregando();
    pegar('/api/visao-geral?dias=' + encodeURIComponent(diasDoPeriodoId(periodoVisao)))
      .then(function(d){ alvo.innerHTML = htmlVisao(d); ligarVisao(); })
      .catch(function(e){ alvo.innerHTML = falha(e); });
  }

  function saudacao(){
    var h = new Date().getHours();
    return h < 12 ? 'Bom dia' : (h < 18 ? 'Boa tarde' : 'Boa noite');
  }

  function htmlVisao(d){
    // A headline diz o número, não o nome da tela. Quem abre a Visão geral já
    // sai sabendo como está a margem, sem precisar procurar.
    var m = d.margem || {}, p = d.periodo || {};
    definirTitulo('visao', 'Visão geral · ' + esc(data(p.inicio)) + ' a ' + esc(data(p.fim)),
      (m.pct === null || m.pct === undefined || p.vazio)
        ? saudacao() + '! Nenhum pedido aprovado neste período.'
        : saudacao() + '! A margem consolidada está em ' + pct(m.pct) + '.');

    return htmlKpiPrincipal(d) + htmlValorEmRisco(d.valor_em_risco) +
           htmlAlertas(d.alertas) + htmlAcoes(d.acoes) +
           '<p class="meta rodape">Gerado em ' + esc(dataHora(d.gerado_em)) +
           ' · Todo número vem de ferramenta determinística do motor: ' +
           (d.fontes || []).map(function(f){ return '<code>' + esc(f) + '</code>'; }).join(', ') +
           '.</p>';
  }

  function htmlKpiPrincipal(d){
    var m = d.margem || {}, p = d.periodo || {}, ant = d.periodo_anterior || {};
    if(p.vazio || m.pct === null || m.pct === undefined){
      return '<h2 class="sec">Margem de contribuição</h2>' +
        aviso('Nenhum pedido aprovado no período de <strong>' + esc(data(p.inicio)) +
              '</strong> a <strong>' + esc(data(p.fim)) + '</strong>.');
    }
    var v = m.variacao || {};
    var sobe = (v.margem_pp || 0) >= 0;
    var setinha = (v.margem_pp === null || v.margem_pp === undefined) ? '' :
      '<span class="kpi-variacao ' + (sobe ? 'sobe' : 'desce') + '">' +
        '<span class="ico" data-ico="' + (sobe ? 'arrow-up-right' : 'arrow-down-right') + '"></span>' +
        (sobe ? '+' : '−') + pp(Math.abs(v.margem_pp)) + '</span>';

    return '<section class="kpi-principal">' +
      '<div class="kpi-principal-corpo">' +
        '<span class="eyebrow">Margem de contribuição · ' + num(p.dias) + ' dias</span>' +
        '<div class="kpi-principal-linha">' +
          '<span class="kpi-principal-val">' + pct(m.pct) + '</span>' + setinha +
        '</div>' +
        '<p class="kpi-principal-ctx">' + brl(m.reais) + ' sobre ' + brl(m.receita_liquida) +
          ' de receita líquida · ' + num(m.pedidos) + ' pedidos</p>' +
        '<p class="kpi-principal-periodo">' + esc(data(p.inicio)) + ' a ' + esc(data(p.fim)) +
          ' · comparado com ' + esc(data(ant.inicio)) + ' a ' + esc(data(ant.fim)) +
          ' (margem de ' + pct(m.anterior_pct) + ')</p>' +
      '</div>' +
      '<div class="kpi-principal-lado">' +
        kpiMini('Taxa de desconto', pp(v.desconto_pp), 'variação no período') +
        kpiMini('Receita bruta', pct(v.receita_pct), 'variação no período') +
        kpiMini('Pedidos', pct(v.pedidos_pct), 'variação no período') +
      '</div>' +
      '</section>';
  }

  function kpiMini(rotulo, valor, ctx){
    return '<div class="kpi-mini"><span class="kpi-lbl">' + esc(rotulo) + '</span>' +
           '<span class="kpi-mini-val">' + valor + '</span>' +
           '<span class="kpi-ctx">' + esc(ctx) + '</span></div>';
  }

  /* Dois grupos, dois subtotais, nenhum total único: o motor declara que as
     duas famílias medem perdas em momentos diferentes do funil e que somá-las
     conta a mesma perda duas vezes. A tela não desfaz essa distinção. */
  function htmlValorEmRisco(r){
    if(!r) return '';
    // Barra proporcional ao maior driver do grupo: a leitura é comparativa,
    // não absoluta — quem olha quer saber qual pesa mais, e o valor exato fica
    // à direita para quem precisa dele.
    function grupo(g, titulo, legenda){
      var drivers = g.drivers || [];
      var maximo = Math.max.apply(null, drivers.map(function(dr){
        return Math.abs(Number(dr.valor_reais) || 0); }).concat([1]));
      var linhas = drivers.map(function(dr){
        var larg = (Math.abs(Number(dr.valor_reais) || 0) / maximo * 100).toFixed(1);
        return '<div class="risco-linha" title="' + esc(dr.nota) + '">' +
          '<span class="risco-nome">' + esc(dr.driver) + '</span>' +
          '<span class="risco-trilha"><span class="risco-preenche" style="width:' +
            larg + '%"></span></span>' +
          '<span class="risco-valor">' + brl(dr.valor_reais) + '</span></div>';
      }).join('');
      return '<div class="risco-grupo">' +
        '<div class="risco-cabeca"><h3 class="risco-titulo">' + esc(titulo) + '</h3>' +
        '<span class="risco-subtotal-val">' + brl(g.subtotal_reais) + '</span></div>' +
        '<p class="meta">' + esc(legenda) + '</p>' +
        '<div class="risco-barras">' + linhas + '</div></div>';
    }
    return '<h2 class="sec">Valor em risco</h2>' +
      '<p class="meta">' + esc(r.periodo) + '.</p>' +
      '<div class="cartao">' +
        '<div class="risco-grade">' +
          grupo(r.entre_receita_e_margem, 'Entre a receita e a margem',
                'O que se perde antes de a margem ser calculada.') +
          grupo(r.depois_da_margem, 'Depois da margem calculada',
                'O que se perde depois que o pedido já entrou.') +
        '</div>' +
      '</div>';
  }

  function htmlAlertas(alertas){
    if(!alertas || !alertas.length){
      return '<h2 class="sec">Alertas</h2><div class="cartao">' +
        '<div class="vazio">Nenhuma checagem com problema. Resultado limpo também é resultado.</div>' +
        '</div>';
    }
    var linhas = alertas.map(function(a){
      return '<tr><td>' + esc(a.rotulo) + '</td>' +
             '<td class="alvo">' + esc(a.alvo) + '</td>' +
             '<td class="status-celula">' + chip(a.status) + '</td></tr>';
    }).join('');
    return '<h2 class="sec">Alertas</h2>' +
      '<p class="meta">' + num(alertas.length) +
      (alertas.length === 1 ? ' checagem' : ' checagens') + ' pedindo leitura.</p>' +
      '<div class="cartao"><table class="tab">' +
      '<tr><th>Achado</th><th>Onde</th><th class="status-celula">Status</th></tr>' +
      linhas + '</table>' +
      '<div class="acao-linha"><button class="btn" type="button" data-ir="auditoria">' +
      'Ver auditoria completa</button></div></div>';
  }

  function htmlAcoes(acoes){
    if(!acoes || !acoes.length) return '';
    /* A marca de confiança é a mesma do motor: ● fato calculado, ◐ estimativa
       sob premissa. Ela fica no card porque a diferença entre os dois muda o
       que o comitê pode prometer. */
    var cards = acoes.map(function(a){
      var estimado = a.fonte === 'simular_teto_desconto' || a.fonte === 'custo_assimetria_frete';
      var marca = '<span class="acao-marca ' + (estimado ? 'estimado' : 'calculado') + '">' +
        (estimado ? '◐ estimado' : '● calculado') + '</span>';
      return '<div class="acao-card">' +
        '<div class="acao-topo"><span class="acao-nome">' + esc(a.acao) + '</span>' + marca + '</div>' +
        '<span class="acao-valor">' + brl(a.valor_reais) + '</span>' +
        '<span class="eyebrow">' + esc(a.unidade) + '</span>' +
        '<span class="acao-detalhe">' + esc(a.detalhe) + '</span>' +
        // Alavanca sem tela para configurar não ganha botão: mandar para
        // Políticas prometeria uma configuração de frete que não existe lá.
        (a.destino
          ? '<button class="btn" type="button" data-ir="' + esc(a.destino) + '">' +
              (a.destino === 'politica' ? 'Abrir políticas' : 'Abrir auditoria') + '</button>'
          : '<span class="acao-controle">' + esc(a.controle || 'Sem ação no sistema') +
            '</span>') +
        '</div>';
    }).join('');
    return '<h2 class="sec">Principais ações</h2>' +
      '<div class="acao-grade">' + cards + '</div>';
  }

  function ligarVisao(){
    document.querySelectorAll('#visaoConteudo [data-ir]').forEach(function(b){
      b.addEventListener('click', function(){ navegar(b.getAttribute('data-ir')); });
    });
  }

  /* ------------------------------------------------- relatório por período */
  /* A janela do relatório vai para a API como TAMANHO (`dias`) mais DATA DE FIM
     (`ate`), que é como `margem_na_janela` sempre soube trabalhar. O seletor
     manda as duas coisas a partir do período escolhido.

     A tela ainda sabe avisar quando o período apurado difere do pedido: isso
     agora só acontece por limite do DADO (data fora do intervalo da base), não
     mais por limite da rota. */
  var baseJanela = null;        // [inicio, fim] da base, como o backend devolve
  var periodoPedido = null;     // {inicio, fim} escolhido pelo usuário

  /* Os campos de data são texto com máscara DD/MM/AAAA, não <input type="date">.
     O seletor nativo desenha a data no formato do NAVEGADOR — num Chrome em
     inglês, 01/12/2023 aparece como 12/01/2023, e a regra desta interface é que
     data se lê em DD/MM/AAAA sempre. O calendário continua disponível pelo botão
     ao lado, que abre um input nativo escondido; o que ele devolve é convertido
     para o formato de exibição. Para o backend vai o AAAA-MM-DD de sempre. */
  function isoDoCampo(id){
    var m = String(el(id).value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if(!m) return '';
    var iso = m[3] + '-' + m[2] + '-' + m[1];
    var d = paraData(iso);
    // 31/02/2024 casa com a máscara mas não existe: a volta pelo Date denuncia.
    return (d && paraISO(d) === iso) ? iso : '';
  }
  function porCampo(id, iso){ el(id).value = iso ? data(iso) : ''; }

  function mascaraDeData(campo, aoMudar){
    campo.addEventListener('input', function(){
      var d = campo.value.replace(/\D/g, '').slice(0, 8);
      campo.value = d.length > 4 ? d.slice(0, 2) + '/' + d.slice(2, 4) + '/' + d.slice(4)
                  : d.length > 2 ? d.slice(0, 2) + '/' + d.slice(2)
                  : d;
      if(aoMudar) aoMudar();
    });
  }

  /* Markup do campo de data, para quem é desenhado por JS (a vigência da
     política). O do relatório já vem pronto no HTML com estas mesmas classes. */
  function campoDataHTML(id, rotulo, nome){
    return '<label class="campo"><span>' + esc(rotulo) + '</span>' +
      '<span class="campo-data">' +
        '<input type="text" id="' + id + '"' + (nome ? ' name="' + nome + '"' : '') +
          ' inputmode="numeric" maxlength="10" placeholder="DD/MM/AAAA" autocomplete="off">' +
        '<button type="button" class="campo-cal" data-picker="' + id + '" ' +
          'aria-label="Abrir calendário"><svg viewBox="0 0 24 24" fill="none" ' +
          'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" ' +
          'stroke-linejoin="round"><rect x="3" y="5" width="18" height="16" rx="2"/>' +
          '<path d="M8 3v4M16 3v4M3 10h18"/></svg></button>' +
        '<input type="date" class="campo-nativo" id="' + id + 'Nativo" tabindex="-1" ' +
          'aria-hidden="true">' +
      '</span></label>';
  }

  /* Liga máscara e calendário. O input nativo escondido existe só para emprestar
     o widget: o que ele devolve é convertido para DD/MM/AAAA na hora. */
  function ligarCampoData(id, aoMudar){
    var campo = el(id);
    if(!campo) return;
    mascaraDeData(campo, aoMudar);
    var nativo = el(id + 'Nativo');
    var botao = document.querySelector('.campo-cal[data-picker="' + id + '"]');
    if(!nativo || !botao) return;
    botao.addEventListener('click', function(){
      nativo.value = isoDoCampo(id) || '';
      if(typeof nativo.showPicker === 'function'){
        try { nativo.showPicker(); return; } catch(e){ /* navegador recusou */ }
      }
      campo.focus();
    });
    nativo.addEventListener('change', function(){
      if(!nativo.value) return;
      porCampo(id, nativo.value);
      if(aoMudar) aoMudar();
    });
  }

  function diasDoPeriodo(){
    var i = isoDoCampo('relInicio'), f = isoDoCampo('relFim');
    var n = (i && f) ? diasEntre(i, f) : null;
    return (n && n > 0) ? n : null;
  }

  function urlRelatorio(extra){
    return '/api/relatorio.html?com_resumo=' + (el('relResumo').checked ? 'true' : 'false') +
           qsPeriodo() + (extra || '');
  }

  /* `dias` e `ate` andam juntos: a janela é [ate-dias+1, ate]. */
  function qsPeriodo(){
    var dias = diasDoPeriodo(), fim = isoDoCampo('relFim');
    return (dias ? '&dias=' + dias : '') + (fim ? '&ate=' + fim : '');
  }
  el('relAbrir').addEventListener('click', function(){
    window.open(urlRelatorio(), '_blank');
  });
  el('relBaixar').addEventListener('click', function(){
    window.location.href = urlRelatorio('&baixar=true');
  });
  el('relResumo').addEventListener('change', function(){ carregarRelatorio(); });
  el('relGerar').addEventListener('click', function(){ carregarRelatorio(); });

  /* Os atalhos de período preenchem os MESMOS campos de data que o seletor
     manual usa — não existe um segundo caminho até a API. A janela termina no
     último dia da base, que é o que a primeira resposta informou. */
  var periodoRelatorio = '';
  function aplicarPeriodoRapido(id){
    periodoRelatorio = id;
    var dias = diasDoPeriodoId(id);
    var fim = baseJanela ? baseJanela[1] : null;
    if(!fim){ carregarRelatorio(); return; }
    var d = paraData(fim);
    d.setDate(d.getDate() - (dias - 1));
    porCampo('relInicio', paraISO(d));
    porCampo('relFim', fim);
    textoPeriodo('');
    barraPeriodo('relPeriodoRapido', periodoRelatorio, aplicarPeriodoRapido);
    carregarRelatorio();
  }
  barraPeriodo('relPeriodoRapido', periodoRelatorio, aplicarPeriodoRapido);

  function validarPeriodo(){
    var i = isoDoCampo('relInicio'), f = isoDoCampo('relFim');
    if(!el('relInicio').value || !el('relFim').value)
      return 'Informe as duas datas para gerar o relatório.';
    if(!i || !f) return 'Data inválida. Use o formato DD/MM/AAAA.';
    if(diasEntre(i, f) < 1) return 'A data de início precisa ser anterior à data de fim.';
    return '';
  }

  function textoPeriodo(erro){
    var alvo = el('relPeriodoTexto');
    if(!alvo) return;
    if(erro){
      alvo.className = 'filtros-resumo erro';
      alvo.textContent = erro;
      return;
    }
    var i = isoDoCampo('relInicio'), f = isoDoCampo('relFim');
    alvo.className = 'filtros-resumo';
    var n = (i && f) ? diasEntre(i, f) : null;
    alvo.textContent = (n && n > 0)
      ? 'Período selecionado: ' + data(i) + ' a ' + data(f) + ' · ' + num(n) + ' dias'
      : (baseJanela
          ? 'Dados disponíveis de ' + data(baseJanela[0]) + ' a ' + data(baseJanela[1]) + '.'
          : '');
  }

  ['relInicio', 'relFim'].forEach(function(id){
    ligarCampoData(id, function(){ textoPeriodo(''); });
  });

  /* Na primeira carga a base ainda é desconhecida: pede a janela padrão, e é a
     resposta que diz qual é o intervalo disponível para preencher os campos. */
  function ajustarCampos(d){
    var sem = d.semana || {};
    if(d.janela && d.janela.length === 2) baseJanela = [data0(d.janela[0]), data0(d.janela[1])];
    var min = baseJanela ? baseJanela[0] : '';
    var max = baseJanela ? baseJanela[1] : '';
    ['relInicio', 'relFim'].forEach(function(id){
      var nativo = el(id + 'Nativo');
      if(nativo && min) nativo.min = min;
      if(nativo && max) nativo.max = max;
    });
    if(!el('relInicio').value) porCampo('relInicio', data0(sem.inicio) || min);
    if(!el('relFim').value) porCampo('relFim', data0(sem.fim) || max);
    textoPeriodo('');
  }
  function data0(iso){
    var m = String(iso || '').match(/^(\d{4}-\d{2}-\d{2})/);
    return m ? m[1] : '';
  }

  function carregarRelatorio(){
    var alvo = el('relConteudo');
    var qs = '';
    if(el('relInicio').value || el('relFim').value){
      var erro = validarPeriodo();
      if(erro){ textoPeriodo(erro); return; }
      textoPeriodo('');
      qs = qsPeriodo();
      periodoPedido = { inicio: isoDoCampo('relInicio'), fim: isoDoCampo('relFim') };
    }
    alvo.innerHTML = carregando();
    pegar('/api/relatorio?com_resumo=' + (el('relResumo').checked ? 'true' : 'false') + qs)
      .then(function(d){
        ajustarCampos(d);
        alvo.innerHTML = htmlRelatorio(d);
        // Os gráficos entram depois, cada um na sua chamada: se um deles
        // falhar, o relatório de números continua na tela.
        ligarGraficos();
        carregarGraficos(d.semana);
      })
      .catch(function(e){ alvo.innerHTML = falha(e); });
  }

  /* Com `ate` chegando ao motor, o período pedido é respeitado — o aviso agora
     só aparece quando o pedido esbarra no DADO, não na rota: janela que começa
     antes do primeiro pedido da base, ou termina depois do último. */
  function avisoDePeriodo(sem){
    if(!periodoPedido || !sem || !sem.fim) return '';
    if(data0(sem.inicio) === periodoPedido.inicio && data0(sem.fim) === periodoPedido.fim) return '';
    var faixa = baseJanela
      ? ' A base cobre de ' + esc(data(baseJanela[0])) + ' a ' + esc(data(baseJanela[1])) + '.' : '';
    return aviso('Você pediu <strong>' + esc(data(periodoPedido.inicio)) + ' a ' +
                 esc(data(periodoPedido.fim)) + '</strong>; o relatório foi apurado sobre ' +
                 '<strong>' + esc(data(sem.inicio)) + ' a ' + esc(data(sem.fim)) + '</strong> (' +
                 num(sem.dias) + ' dias).' + faixa);
  }

  function htmlSemana(sem){
    if(!sem || !sem.fim) return '';
    // Período fora da base devolve a janela certa e zero pedidos. Mostrar seis
    // KPIs com travessão seria pior que dizer o que aconteceu.
    if(!sem.pedidos){
      return '<h2 class="sec">Período de ' + esc(data(sem.inicio)) + ' a ' +
        esc(data(sem.fim)) + '</h2>' +
        aviso('Nenhum pedido aprovado neste período.' + (baseJanela
          ? ' A base cobre de <strong>' + esc(data(baseJanela[0])) + '</strong> a <strong>' +
            esc(data(baseJanela[1])) + '</strong>.' : ''));
    }
    var ant = sem.anterior || {}, v = sem.variacao || {};
    var kpis =
      kpi('Margem do período', pct(sem.margem_pct),
          brl(sem.margem_reais) + ' sobre receita líquida · anterior ' +
          pct(ant.margem_pct)) +
      kpi('Taxa de desconto', pct(sem.desconto_pct), 'anterior ' + pct(ant.desconto_pct)) +
      kpi('Pedidos', num(sem.pedidos), 'anterior ' + num(ant.pedidos)) +
      kpi('Ticket médio', brl(sem.ticket_medio),
          brl(sem.receita_liquida) + ' de receita líquida');

    var linhas = v ? [
      ['Margem de contribuição', delta(v.margem_pp, 'p.p.', true)],
      ['Taxa de desconto', delta(v.desconto_pp, 'p.p.', false)],
      ['Receita bruta', delta(v.receita_pct, '%', true)],
      ['Pedidos', delta(v.pedidos_pct, '%', true)]
    ].map(function(l){
      return '<tr><td>' + l[0] + '</td><td class="num">' + l[1] + '</td></tr>';
    }).join('') : '';

    return '<h2 class="sec">Período de ' + esc(data(sem.inicio)) + ' a ' +
      esc(data(sem.fim)) + '</h2>' +
      '<p class="meta">vs ' + esc(data(ant.inicio)) + ' a ' + esc(data(ant.fim)) +
      ' · janela de ' + num(sem.dias) + ' dias</p>' +
      avisoDePeriodo(sem) +
      '<div class="kpis">' + kpis + '</div>' +
      '<div class="cartao" style="margin-top:12px">' +
      (linhas ? '<table class="tab"><tr><th>Indicador</th>' +
                '<th class="num">Variação sobre o período anterior</th></tr>' +
                linhas + '</table>' : '') +
      '</div>';
  }

  /* ---------------------------------------------- gráficos do relatório
     Os dois gráficos cobrem exatamente a MESMA janela dos KPIs acima: a
     consulta usa `dias`/`fim` que o backend devolveu como período apurado, não
     o que está digitado no campo — se o pedido esbarrou no limite da base, o
     gráfico acompanha o que foi apurado, e não o que foi pedido. */
  var dimensaoBarras = 'canal';       // seletor do gráfico de barras
  var janelaGraficos = null;          // {dias, ate} da última carga

  function qsJanela(){
    if(!janelaGraficos) return '';
    return 'dias=' + encodeURIComponent(janelaGraficos.dias) +
           '&ate=' + encodeURIComponent(janelaGraficos.ate);
  }

  function carregarGraficos(sem){
    if(!sem || !sem.fim || !sem.dias) return;
    janelaGraficos = { dias: sem.dias, ate: data0(sem.fim) };
    carregarCascata();
    carregarBarras();
  }

  function carregarCascata(){
    var alvo = el('relCascata');
    if(!alvo) return;
    alvo.innerHTML = carregando();
    pegar('/api/relatorio/cascata?' + qsJanela())
      .then(function(c){ alvo.innerHTML = htmlCascata(c); })
      .catch(function(e){ alvo.innerHTML = falha(e); });
  }

  function ramo(c, nome){
    var r = (c.ramos || []).filter(function(x){ return x.ramo === nome; })[0];
    return r ? Number(r.margem_perdida_reais) : 0;
  }

  function htmlCascata(c){
    // Ordem fixa do diagnóstico — não a ordem por tamanho que a ferramenta
    // devolve: a cascata conta uma sequência, não um ranking.
    var passos = [
      { rotulo: 'Margem calculada', valor: Number(c.margem_calculada_reais), total: true },
      { rotulo: 'Cancelamento', valor: -ramo(c, 'Cancelamento') },
      { rotulo: 'Pendência', valor: -ramo(c, 'Pendência') },
      { rotulo: 'Devolução', valor: -ramo(c, 'Devolução') },
      { rotulo: 'Atendimento', valor: -ramo(c, 'Atendimento') },
      { rotulo: 'Margem realizada', valor: Number(c.margem_que_se_realiza_reais), total: true }
    ];
    var perdeu = (c.perda_pct_da_margem_calculada === null ||
                  c.perda_pct_da_margem_calculada === undefined)
      ? '' : ' · ' + pct(c.perda_pct_da_margem_calculada) + ' da margem calculada';
    // Duas leituras diferentes, dois parágrafos: a perda total e o piso
    // factual não são a mesma frase, e emendados viravam um bloco corrido.
    return graficoCascata(passos) +
      '<p class="meta grafico-leitura">Perda pós-pedido de ' +
      brl(c.perda_pos_pedido_reais) + perdeu + '.</p>' +
      '<p class="meta grafico-leitura">Piso factual da devolução: ' +
      brl(c.piso_factual_da_devolucao_reais) + '.</p>';
  }

  function carregarBarras(){
    var alvo = el('relBarras');
    if(!alvo) return;
    alvo.innerHTML = carregando();
    pegar('/api/relatorio/margem-por?dimensao=' + encodeURIComponent(dimensaoBarras) +
          '&' + qsJanela())
      .then(function(b){ alvo.innerHTML = htmlBarras(b); })
      .catch(function(e){ alvo.innerHTML = falha(e); });
  }

  function htmlBarras(b){
    var linhas = b.linhas || [];
    if(!linhas.length) return '<div class="vazio">Nenhum pedido no período para abrir por ' +
      esc(dimensaoBarras) + '.</div>';
    // Ordena da pior para a melhor margem: a leitura do gráfico é "onde dói".
    var ord = linhas.slice().sort(function(x, y){
      return x.margem_pct_sobre_liquida - y.margem_pct_sobre_liquida;
    });
    var pior = ord[0];
    var itens = ord.map(function(l){
      return {
        rotulo: l[b.dimensao],
        valor: l.margem_pct_sobre_liquida,
        texto: pct(l.margem_pct_sobre_liquida),
        destaque: l === pior
      };
    });
    // O destaque do pior recorte vai em linha própria: emendado na legenda,
    // ele some no meio da frase justamente quando é o que importa ler.
    return graficoBarras(itens) +

      // Os números ficam num grupo só: se a linha quebrar, ela quebra ANTES
      // deles, e nenhuma linha começa com o middot separador.
      '<p class="grafico-destaque"><span class="eyebrow">Pior ' + esc(b.dimensao) +
      '</span> <strong>' + esc(pior[b.dimensao]) + '</strong> ' +
      '<span class="grafico-destaque-num">' + pct(pior.margem_pct_sobre_liquida) + ' · ' +
      brl(pior.margem_contribuicao) + ' em ' + num(pior.pedidos) + ' pedidos</span></p>';
  }

  function ligarGraficos(){
    document.querySelectorAll('[data-dim]').forEach(function(b){
      b.addEventListener('click', function(){
        dimensaoBarras = b.getAttribute('data-dim');
        document.querySelectorAll('[data-dim]').forEach(function(o){
          o.classList.toggle('is-active', o === b);
        });
        carregarBarras();
      });
    });
  }

  function htmlBlocoGraficos(){
    return '<h2 class="sec">Ponte da margem no período</h2>' +
      '<div class="cartao" id="relCascata"></div>' +
      '<div class="sec-linha">' +
        '<h2 class="sec">Margem por recorte</h2>' +
        '<div class="segmentado">' +
          '<button type="button" class="seg' + (dimensaoBarras === 'canal' ? ' is-active' : '') +
            '" data-dim="canal">Canal</button>' +
          '<button type="button" class="seg' + (dimensaoBarras === 'categoria' ? ' is-active' : '') +
            '" data-dim="categoria">Categoria</button>' +
        '</div>' +
      '</div>' +
      '<div class="cartao" id="relBarras"></div>';
  }

  function htmlRelatorio(d){
    var m = d.margem, desc = d.desconto, neg = d.margem_negativa;
    var frete = d.frete_canal_foco, dev = d.devolucoes, pior = d.pior_canal_por_margem;

    var kpis =
      kpi('Margem de contribuição', pct(m.margem_pct),
          brl(m.margem_reais) + ' sobre receita líquida') +
      kpi('Taxa de desconto', pct(desc.taxa_desconto_pct), brl(desc.desconto_reais)) +
      kpi('Pedidos com margem negativa', num(neg.pedidos),
          pct(neg.pct_dos_pedidos) + ' dos pedidos · ' + brl(neg.perda_reais)) +
      kpi('Frete evitável — ' + frete.canal, brl(frete.frete_evitavel_reais),
          '+' + pp(frete.ganho_margem_pp_consolidado, 3) + ' na margem consolidada') +
      kpi('Taxa de devolução', pct(dev.taxa_global_pct),
          brl(dev.margem_perdida_reais) + ' de margem') +
      kpi('Pior canal por margem', pior.canal, pct(pior.margem_pct));

    var resumo = '';
    if(d.resumo_executivo){
      resumo = '<h2 class="sec">Resumo executivo</h2><div class="cartao">' +
        '<p class="p">' + esc(d.resumo_executivo) + '</p></div>';
    } else if(el('relResumo').checked){
      resumo = '<h2 class="sec">Resumo executivo</h2><div class="cartao">' +
        aviso('O modelo não respondeu agora, então o relatório saiu sem o parágrafo. ' +
              'Os KPIs acima não dependem dele.') + '</div>';
    }

    var devol = '<h2 class="sec">Devoluções</h2><div class="cartao"><table class="tab">' +
      '<tr><th>Indicador</th><th class="num">Valor</th></tr>' +
      '<tr><td>Taxa global de devolução</td><td class="num">' + pct(dev.taxa_global_pct) + '</td></tr>' +
      '<tr><td>Margem carregada nos pedidos devolvidos</td><td class="num">' + brl(dev.margem_perdida_reais) + '</td></tr>' +
      '<tr><td>Impacto na margem consolidada</td><td class="num">' + pp(dev.impacto_pp_na_margem) + '</td></tr>' +
      '<tr><td>Custo de devolução deduzido da margem</td><td class="num">' + chip('atencao') + ' Não</td></tr>' +
      '</table></div>';

    var janela = (d.janela && d.janela.length === 2)
      ? data(d.janela[0]) + ' a ' + data(d.janela[1]) : '';
    var fontes = (d.fontes || []).map(function(f){ return '<code>' + esc(f) + '</code>'; }).join(', ');

    return htmlSemana(d.semana) +
      (d.semana && d.semana.pedidos ? htmlBlocoGraficos() : '') +
      '<h2 class="sec">Acumulado da base</h2>' +
      '<p class="meta">' + esc(janela) + '</p>' +
      '<div class="kpis">' + kpis + '</div>' + resumo + devol +
      '<p class="meta rodape">Gerado em ' + esc(dataHora(d.gerado_em)) + ' · Todo número vem de ' +
      'ferramenta determinística do motor: ' + fontes + '.</p>';
  }

  /* ----------------------------------------------------------- auditoria */
  el('audAbrir').addEventListener('click', function(){
    window.open('/api/auditoria.html', '_blank');
  });
  el('audBaixar').addEventListener('click', function(){
    window.location.href = '/api/auditoria.html?baixar=true';
  });

  function carregarAuditoria(){
    var alvo = el('audConteudo');
    alvo.innerHTML = carregando();
    pegar('/api/auditoria')
      .then(function(d){ alvo.innerHTML = htmlAuditoria(d); })
      .catch(function(e){ alvo.innerHTML = falha(e); });
  }

  function detalhe(nome, r){
    if(nome === 'integridade_referencial')
      return num(r.registros_orfaos) + ' órfãos em ' + num(r.linhas_verificadas) + ' linhas';
    if(nome === 'duplicatas_chave')
      return num(r.linhas_duplicadas) + ' duplicadas em ' + num(r.linhas_verificadas) + ' linhas';
    if(nome === 'completude'){
      if(r.linhas_quebradas){
        var ex = (r.exemplos_linhas_quebradas || [{}])[0];
        var ident = Object.keys(ex).filter(function(k){
          return k !== 'linha' && k !== 'campos_vazios'; }).map(function(k){ return ex[k]; })[0];
        return num(r.linhas_quebradas) + ' linha(s) com ' + ex.campos_vazios +
               ' campos vazios (ex: ' + esc(ident) + ')';
      }
      if(r.linhas_incompletas)
        return num(r.linhas_incompletas) + ' linha(s) com algum nulo em ' +
               (r.colunas_com_nulo || []).length + ' coluna(s)';
      return 'nenhum nulo';
    }
    if(nome === 'outliers_iqr')
      return num(r.outliers) + ' outliers (' + pct(r.pct_outliers) + ') em ' +
             esc(r.coluna || '') + ' — máx observado ' + num(r.maximo_observado);
    if(nome === 'faixa_implausivel')
      return num(r.fora_da_faixa) + ' fora da faixa esperada em ' + esc(r.coluna || '');
    return '—';
  }

  /* Checagens cujos registros o motor sabe listar por inteiro. Fora desta
     lista, a linha não ganha botão — melhor não oferecer o que não existe. */
  var EXPORTAVEIS = ['integridade_referencial', 'duplicatas_chave', 'completude',
                     'outliers_iqr', 'faixa_implausivel'];

  /* O botão baixa a lista COMPLETA do que falhou, para correção humana no
     sistema de origem. Não existe caminho de volta: o motor é só-leitura e
     nada aqui escreve em data/*.csv. */
  function botaoExportar(c){
    var st = (c.resultado || {}).status;
    if(('erro' in c) || (st !== 'atencao' && st !== 'revisar')) return '';
    if(EXPORTAVEIS.indexOf(c.checagem) === -1) return '';
    var qs = ['checagem=' + encodeURIComponent(c.checagem)];
    Object.keys(c.parametros || {}).forEach(function(k){
      var v = c.parametros[k];
      if(v === null || v === undefined) return;
      qs.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
    });
    return '<a class="btn-soft" download href="/api/auditoria/exportar?' +
           qs.join('&') + '">Exportar lista para correção</a>';
  }

  /* Rótulo de negócio para cada checagem. O backend continua com os nomes
     reais das funções — isto é tradução de exibição, e o nome técnico fica a
     um clique de distância, em "Ver detalhes". */
  var ROTULO_CHECAGEM = {
    integridade_referencial: 'Pedidos com referência quebrada',
    duplicatas_chave: 'Registros duplicados',
    completude: 'Campos obrigatórios faltando',
    outliers_iqr: 'Valores fora do padrão',
    faixa_implausivel: 'Valores fora da faixa esperada',
    consistencia_categorica: 'Categorias inconsistentes',
    devolucao_fora_prazo: 'Devoluções fora do prazo',
    coerencia_motivo_entrega: 'Motivo de devolução inconsistente'
  };
  // O motor também nomeia as funções com o prefixo `checar_`/`verificar_`.
  var PREFIXOS = ['checar_', 'verificar_'];

  function rotuloDaChecagem(nome){
    var n = String(nome || '');
    PREFIXOS.forEach(function(p){ if(n.indexOf(p) === 0) n = n.slice(p.length); });
    return ROTULO_CHECAGEM[n] || ROTULO_CHECAGEM[nome] || nome;
  }

  // Exceção primeiro: o que pede ação abre a tabela, o que veio limpo fecha.
  var ORDEM_STATUS = { critico: 0, revisar: 1, atencao: 2, ok: 3 };
  function pesoDoStatus(c){
    if('erro' in c) return ORDEM_STATUS.critico;
    var s = (c.resultado || {}).status;
    return s in ORDEM_STATUS ? ORDEM_STATUS[s] : ORDEM_STATUS.revisar;
  }

  /* Os identificadores de registro que a checagem trouxe — ficam no "Ver
     detalhes" junto do nome técnico, porque é informação de quem vai corrigir,
     não de quem está lendo o painel. */
  function idsDeExemplo(r){
    var ids = [];
    (r.exemplos_orfaos || []).slice(0, 12).forEach(function(v){ ids.push(String(v)); });
    (r.exemplos || []).slice(0, 12).forEach(function(e){
      ids.push(typeof e === 'object' ? (e.valor != null ? String(e.valor) : JSON.stringify(e)) : String(e));
    });
    (r.exemplos_linhas_quebradas || []).slice(0, 12).forEach(function(e){
      var chave = Object.keys(e).filter(function(k){
        return k !== 'linha' && k !== 'campos_vazios'; })[0];
      ids.push(chave ? String(e[chave]) : ('linha ' + e.linha));
    });
    return ids;
  }

  /* Cada achado é um card, e o que veio limpo encolhe para uma linha. Numa
     tabela de nove linhas, as sete que dizem "sem problema" enterram as duas
     que pedem ação — que é exatamente o contrário de orientar por exceção. */
  function htmlAuditoria(d){
    var checagens = (d.checagens || []).slice().sort(function(a, b){
      return pesoDoStatus(a) - pesoDoStatus(b);
    });
    var comProblema = checagens.filter(function(c){ return pesoDoStatus(c) < 3; });
    var limpas = checagens.filter(function(c){ return pesoDoStatus(c) === 3; });

    var cards = comProblema.map(function(c){
      var r = c.resultado || {};
      var status = ('erro' in c) ? 'critico' : (r.status || 'revisar');
      var txt = ('erro' in c) ? esc(c.erro) : detalhe(c.checagem, r);
      var alvo = Object.keys(c.parametros || {}).map(function(k){
        return k + '=' + c.parametros[k];
      }).join(' · ');
      var ids = idsDeExemplo(r);
      return '<div class="achado ' + esc(status) + '">' +
        '<div class="achado-corpo">' +
          '<div class="achado-titulo"><span class="achado-ponto"></span>' +
            esc(rotuloDaChecagem(c.checagem)) + '</div>' +
          '<div class="achado-desc">' + txt + '</div>' +
          '<details class="checagem-detalhe"><summary>Ver detalhes técnicos</summary>' +
            '<dl class="checagem-tecnica">' +
              '<dt>Função do motor</dt><dd><code>' + esc(c.checagem) + '</code></dd>' +
              '<dt>Parâmetros</dt><dd><code>' + esc(alvo || '—') + '</code></dd>' +
              (ids.length ? '<dt>Registros</dt><dd><code>' + esc(ids.join(', ')) +
                            (ids.length >= 12 ? ', …' : '') + '</code></dd>' : '') +
            '</dl></details>' +
        '</div>' +
        '<div class="achado-acao">' + botaoExportar(c) + '</div>' +
        '</div>';
    }).join('');

    var linhasLimpas = limpas.map(function(c){
      var r = c.resultado || {};
      return '<div class="achado-limpo"><span class="achado-ponto"></span>' +
             esc(rotuloDaChecagem(c.checagem)) + ' — ' + detalhe(c.checagem, r) + '</div>';
    }).join('');

    var tabela = (cards || '<div class="achado-limpo"><span class="achado-ponto"></span>' +
                  'Nenhuma checagem com problema.</div>') +

      (linhasLimpas ? '<h2 class="sec">Verificado e sem problema</h2>' +
                      linhasLimpas : '');

    var dest = d.destaque_incoerencia, bloco = '';
    if(dest && dest.celulas && dest.celulas.length){
      var topo = dest.celulas.slice(0, 6);
      var maximo = Math.max.apply(null, topo.map(function(c){ return c.registros; })) || 1;
      var barras = topo.map(function(c){
        return '<div class="barra"><span class="barra-lbl">' + esc(c[dest.coluna_a]) + '</span>' +
          '<span class="barra-trilha"><span class="barra-preenche" style="width:' +
          (c.registros / maximo * 100).toFixed(1) + '%"></span></span>' +
          '<span class="barra-val">' + num(c.registros) + '</span></div>';
      }).join('');
      bloco = '<h2 class="sec">Incoerência de domínio encontrada</h2><div class="cartao">' +
        '<p class="p">Motivo de devolução <strong>"' + esc(dest.valor_b) + '"</strong> por ' +
        'categoria de produto.</p><div class="barras">' + barras + '</div>' +
        aviso('<strong>' + num(dest.fora) + ' registros</strong> fora da categoria ' +
              'esperada.') + '</div>';
    }

    // A seção "Lacunas de dado" saiu da tela a pedido do usuário. O backend
    // continua devolvendo `lacunas_de_dado` e `prazo_devolucao` normalmente —
    // a auditoria segue completa no relatório baixável e no trace; o que mudou
    // é só o que esta aba desenha.
    // O título da tela é o que a auditoria ACHOU, não o nome da ferramenta.
    var n = comProblema.length;
    var titulo = n === 0
      ? 'Nenhum ponto de atenção na base'
      : (n === 1 ? '1 ponto encontrado' : n + ' pontos encontrados, do mais grave ao mais leve');
    definirTitulo('auditoria', 'Auditoria de dados', titulo,
      num(d.total_checagens) + ' checagens determinísticas sobre a base bruta.');

    return tabela + bloco;
  }
  /* ============================================================== política
     Fluxo com estado real, não uma tela com botão "Aplicar".

     O stepper reflete o `estado` que a API devolve — ele nunca é decorativo:
     se a proposta está em Simulação, o passo aceso é Simulação, e as únicas
     ações oferecidas são as que aquele estado permite. Aprovar é uma decisão
     registrada (quem e quando), e só depois dela a política passa a valer.

     Vocabulário: em toda a tela é "margem potencialmente preservada", nunca
     "recuperada". A diferença não é estilística — a política ainda não rodou,
     e o valor vem de simulação sob premissa de volume constante. */
  var recorte = { canal: '', categoria: '' };   // de qual recorte é a vigente exibida
  var listas = { canais: [], categorias: [] };
  var propostaAberta = null;                    // proposta em foco no fluxo
  // Preenchido pela API: até onde o fluxo vai hoje. Vazio até a primeira
  // carga, e aí o stepper mostra tudo como disponível — o backend recusa de
  // qualquer forma, então a tela nunca promete sozinha.
  var etapasHabilitadas = null;

  var PASSOS = [
    { id: 'rascunho',      rotulo: 'Rascunho' },
    { id: 'simulacao',     rotulo: 'Simulação' },
    { id: 'aprovacao',     rotulo: 'Aprovação' },
    { id: 'ativa',         rotulo: 'Ativa' },
    { id: 'monitoramento', rotulo: 'Monitoramento' }
  ];

  function carregarPolitica(){
    var alvo = el('polConteudo');
    alvo.innerHTML = carregando();
    Promise.all([
      pegar('/api/politica' + qsRecorte()),
      pegar('/api/politica/propostas'),
      pegar('/api/politica/cenarios' + qsRecorte())
    ]).then(function(res){
      var d = res[0], props = res[1].propostas || [], cen = res[2];
      filaAprovacao = res[1].aguardando_aprovacao || [];
      etapasHabilitadas = res[1].etapas_habilitadas || null;
      listas = { canais: d.canais || [], categorias: d.categorias || [] };
      // Mantém em foco a proposta que já estava aberta, se ela ainda existe.
      var foco = propostaAberta &&
        props.filter(function(p){ return p.id === propostaAberta.id; })[0];
      propostaAberta = foco || props[0] || null;
      alvo.innerHTML = htmlPolitica(d, props, cen);
      ligarPolitica();
    }).catch(function(e){ alvo.innerHTML = falha(e); });
  }

  function qsRecorte(){
    return '?canal=' + encodeURIComponent(recorte.canal) +
           '&categoria=' + encodeURIComponent(recorte.categoria);
  }

  function opcoes(lista, rotuloTodos, selecionado){
    return '<option value="">' + rotuloTodos + '</option>' +
      lista.map(function(v){
        return '<option value="' + esc(v) + '"' + (v === selecionado ? ' selected' : '') +
               '>' + esc(v) + '</option>';
      }).join('');
  }

  /* ---------------------------------------------------------- stepper */
  function htmlStepper(estado){
    var indice = PASSOS.map(function(p){ return p.id; }).indexOf(estado);
    var passos = PASSOS.map(function(p, i){
      var classe = i < indice ? 'feito' : (i === indice ? 'atual' : 'futuro');
      // Etapa desligada continua visível — some daria a impressão de que o
      // fluxo tem três passos, quando ele tem cinco e dois não foram feitos.
      if(!etapaHabilitada(p.id)) classe += ' bloqueado';
      return '<li class="passo ' + classe + '">' +
        '<span class="passo-num">' + String(i + 1).padStart(2, '0') + '</span>' +
        '<span class="passo-rotulo">' + esc(p.rotulo) + '</span></li>';
    }).join('');
    var proxima = PASSOS[indice + 1];
    var nota = (proxima && !etapaHabilitada(proxima.id))
      ? '<p class="meta stepper-nota">Aguardando ' + esc(proxima.rotulo.toLowerCase()) +
        ' — implementação futura.</p>'
      : (PASSOS.some(function(p){ return !etapaHabilitada(p.id); })
         ? '<p class="meta stepper-nota">Aprovação em diante: implementação futura.</p>'
         : '');
    return '<ol class="stepper" aria-label="Estado da proposta">' + passos + '</ol>' + nota;
  }

  /* As ações vêm do ESTADO, não de um botão fixo: "Aplicar política" só
     existe depois da aprovação, que é o ponto do fluxo. */
  function etapaHabilitada(id){
    return !etapasHabilitadas || etapasHabilitadas.indexOf(id) !== -1;
  }

  function acoesDoEstado(estado){
    // Ação que leva a uma etapa desligada não é oferecida: o botão existiria
    // só para receber uma recusa do backend.
    return acoesBrutas(estado).filter(function(a){ return etapaHabilitada(a.destino); });
  }

  function acoesBrutas(estado){
    return ({
      rascunho:  [{ rota: 'simular', destino: 'simulacao',
                    rotulo: 'Simular cenário', primaria: true }],
      simulacao: [{ rota: 'enviar-aprovacao', destino: 'aprovacao',
                    rotulo: 'Enviar para aprovação', primaria: true }],
      aprovacao: [{ rota: 'aprovar', destino: 'ativa',
                    rotulo: 'Aprovar e aplicar política', primaria: true }],
      ativa:     [{ rota: 'monitorar', destino: 'monitoramento',
                    rotulo: 'Iniciar monitoramento', primaria: false }],
      monitoramento: []
    })[estado] || [];
  }

  /* Quando a próxima etapa está desligada, a proposta não está "em
     Simulação": ela está parada esperando uma etapa que ainda não existe. O
     rótulo diz isso, e sai da própria lista de passos — trocar a trava muda o
     texto junto. */
  function estadoExibido(p){
    var ids = PASSOS.map(function(x){ return x.id; });
    var i = ids.indexOf(p.estado);
    var prox = PASSOS[i + 1];
    if(prox && !etapaHabilitada(prox.id)){
      return 'Aguardando ' + prox.rotulo.toLowerCase();
    }
    return (PASSOS[i] || {}).rotulo || p.estado;
  }

  function congelada(p){
    var ids = PASSOS.map(function(x){ return x.id; });
    var prox = PASSOS[ids.indexOf(p.estado) + 1];
    return !!(prox && !etapaHabilitada(prox.id));
  }

  function htmlProposta(p){
    if(!p){
      return '<h2 class="sec">Proposta em andamento</h2>' +
        aviso('Nenhuma proposta aberta. Crie uma abaixo — ela nasce em ' +
              '<strong>Rascunho</strong> e não altera o teto vigente.');
    }
    var acoes = acoesDoEstado(p.estado).map(function(a){
      return '<button class="btn' + (a.primaria ? ' primary' : '') +
             '" type="button" data-transicao="' + a.rota + '">' + esc(a.rotulo) + '</button>';
    }).join('');

    var avisoSimulacao = (p.estado === 'simulacao' && !congelada(p))
      ? '<div class="aviso-simulado"><span class="ico" data-ico="alert-triangle"></span>' +
        '<span><strong>Cenário simulado — ainda não aplicado.</strong> Os valores ' +
        'abaixo são estimativa sob premissa de volume constante.</span></div>'
      : '';

    var recorteTxt = (p.canal || 'todos os canais') + ' · ' + (p.categoria || 'todas as categorias');
    return '<h2 class="sec">Proposta em andamento</h2>' +
      '<div class="cartao">' +
        htmlStepper(p.estado) +
        avisoSimulacao +
        '<div class="kpis" style="margin-top:var(--space-4)">' +
          kpi('Teto proposto', pct(p.teto_pct, 1), recorteTxt) +
          kpi('Estado', estadoExibido(p),
              'criada em ' + esc(dataHora(p.criada_em))) +
          kpi('Responsável', p.responsavel) +
        '</div>' +
        (acoes ? '<div class="acao-linha">' + acoes +
                 '<label class="campo campo-quem"><span>Quem está fazendo isto</span>' +
                 '<input type="text" id="polQuem" autocomplete="off" ' +
                 'placeholder="' + (p.estado === 'aprovacao'
                   ? 'Quem aprova — não pode ser ' + esc(quemPropos(p))
                   : 'Nome de quem responde') + '"></label></div>'
               : (congelada(p) ? ''
                  : aviso('Fim do fluxo. O acompanhamento fica em ' +
                          '<strong>Monitoramento</strong>.'))) +
        '<div id="polAviso"></div>' +
      '</div>';
  }

  /* ------------------------------------------------ comparação de cenários */
  function htmlCenarios(cen){
    if(!cen || !cen.cenarios) return '';
    var colunas = cen.cenarios.map(function(x){
      if(x.erro){
        return '<div class="cenario"><span class="eyebrow">Teto ' + pct(x.teto_pct, 0) +
               '</span><div class="vazio erro">' + esc(x.erro) + '</div></div>';
      }
      var destaque = (propostaAberta && Math.round(propostaAberta.teto_pct) === Math.round(x.teto_pct))
        ? ' is-proposto' : '';
      var anual = x.preservado_anualizado_reais;
      return '<div class="cenario' + destaque + '">' +
        '<div class="cenario-topo"><span class="eyebrow">Teto ' + pct(x.teto_pct, 0) + '</span>' +
        (destaque ? '<span class="cenario-marca">Recomendado</span>' : '') + '</div>' +
        '<span class="cenario-valor">' + brl(anual != null ? anual : x.preservado_reais) + '</span>' +
        '<span class="cenario-unidade">potencialmente preservado' +
          (anual != null ? ' por ano' : ' no recorte') + '</span>' +
        '<dl class="cenario-lista">' +
          '<dt>Pedidos afetados</dt><dd>' + pct(x.pct_pedidos_afetados) +
            ' · ' + num(x.pedidos_afetados) + '</dd>' +
          '<dt>Ponto de equilíbrio</dt><dd>' + pct(x.ponto_de_equilibrio_pct) + '</dd>' +
          '<dt>Ganho na margem</dt><dd>' + pp(x.ganho_margem_pp, 3) + '</dd>' +
        '</dl>' +
        '</div>';
    }).join('');

    return '<h2 class="sec">Comparação de cenários</h2>' +
      '<p class="meta">Novembro fora do recorte · ' +
      esc(cen.definicao_ponto_de_equilibrio) + '.</p>' +
      '<div class="cenario-grade">' + colunas + '</div>' +
      aviso('<strong>Potencialmente preservado, não apurado:</strong> ' +
            esc(cen.nota));
  }

  /* ---------------------------------------------------------- vigente */
  function htmlVigente(v, impacto){
    if(!v){
      return aviso('Nenhuma política vale para este recorte — o agente exige o ' +
                   'teto na própria pergunta.');
    }
    return '<div class="kpis">' +
      kpi('Teto de desconto vigente', pct(v.teto_pct, 1),
          (v.canal || 'todos os canais') + ' · ' + (v.categoria || 'todas as categorias')) +
      kpi('Responsável', v.responsavel) +
      kpi('Em vigor desde', data(v.vigencia)) + '</div>' + htmlImpacto(impacto);
  }

  /* Um teto sem o efeito dele é cadastro, não decisão: esta é a conta
     determinística de quantos pedidos a regra toca e quanto de margem ela
     preserva, sob premissa de volume constante. */
  function htmlImpacto(imp, titulo){
    if(!imp) return '';
    var rec = imp.recorte || {};
    var onde = (rec.canal || 'todos os canais') + ' · ' + (rec.categoria || 'todas as categorias');
    return '<h2 class="sec">' + (titulo || 'O que este teto faz') + '</h2>' +
      '<div class="kpis">' +
        kpi('Pedidos acima do teto', num(imp.pedidos_afetados),
            pct(imp.pct_pedidos_afetados) + ' dos ' + num(imp.pedidos_no_recorte) +
            ' pedidos de ' + onde) +
        kpi('Margem potencialmente preservada', brl(imp.margem_recuperada_reais),
            'desconto no grupo cai de ' + brl(imp.desconto_atual_no_grupo) +
            ' para ' + brl(imp.desconto_pos_teto_no_grupo)) +
        kpi('Ganho na margem consolidada', pp(imp.ganho_margem_pp, 3),
            brl(imp.margem_atual_reais) + ' → ' + brl(imp.margem_pos_teto_reais)) +
      '</div>';
  }

  /* Quem propôs: o primeiro passo do histórico, não o campo `responsavel` —
     esse é o dono da REGRA e pode ser outra pessoa. */
  function quemPropos(p){
    var h = (p && p.historico) || [];
    return (h.length && h[0].quem) || (p && p.responsavel) || '';
  }

  /* Fila de aprovação. Sem ela, "aguardando aprovação" é um estado que só quem
     abriu a proposta enxerga — e aprovação que ninguém vê é aprovação que a
     própria pessoa acaba dando. */
  function htmlFilaAprovacao(fila){
    if(!etapaHabilitada('aprovacao')) return '';
    if(!fila || !fila.length) return '';
    var linhas = fila.map(function(p){
      return '<tr><td>' + pct(p.teto_pct, 1) + '</td>' +
        '<td class="alvo">' + esc((p.canal || 'todos') + ' · ' + (p.categoria || 'todas')) + '</td>' +
        '<td>' + esc(p.proposta_por || quemPropos(p)) + '</td>' +
        '<td class="acao-celula"><button class="btn primary" type="button" data-abrir="' +
          esc(p.id) + '">Revisar</button></td></tr>';
    }).join('');
    return '<h2 class="sec">Aguardando aprovação</h2>' +
      '<p class="meta">A aprovação é de outra pessoa: quem propôs não aprova.</p>' +
      '<div class="cartao"><table class="tab">' +
      '<tr><th>Teto</th><th>Recorte</th><th>Proposta por</th>' +
      '<th class="acao-celula">Ação</th></tr>' + linhas + '</table></div>';
  }

  function htmlPolitica(d, props, cen){
    var consulta = '<div class="recorte">' +
      '<label class="campo"><span>Canal</span><select id="recCanal">' +
        opcoes(listas.canais, 'Todos os canais', recorte.canal) + '</select></label>' +
      '<label class="campo"><span>Categoria</span><select id="recCategoria">' +
        opcoes(listas.categorias, 'Todas as categorias', recorte.categoria) + '</select></label>' +
      '</div>';

    var form = '<h2 class="sec">Nova proposta</h2><div class="cartao">' +
      '<form id="polForm" class="form">' +
        '<label class="campo"><span>Canal</span><select name="canal">' +
          opcoes(listas.canais, 'Todos os canais', recorte.canal) + '</select></label>' +
        '<label class="campo"><span>Categoria</span><select name="categoria">' +
          opcoes(listas.categorias, 'Todas as categorias', recorte.categoria) + '</select></label>' +
        '<label class="campo"><span>Teto de desconto (%)</span>' +
          '<input name="teto_pct" type="number" min="0" max="100" step="0.5" ' +
          'placeholder="20" required></label>' +
        '<label class="campo"><span>Responsável</span>' +
          '<input name="responsavel" type="text" placeholder="Nome de quem propõe" required></label>' +
        campoDataHTML('polVigencia', 'Vigência a partir de') +
        '<div class="campo acao">' +
          '<button class="btn primary" type="submit">Salvar rascunho</button>' +
        '</div>' +
      '</form>' +
      '<div id="polAvisoNovo"></div>' +
      '</div>';

    var outras = (props || []).filter(function(p){
      return !propostaAberta || p.id !== propostaAberta.id; });
    var lista = outras.length
      ? '<h2 class="sec">Outras propostas</h2><div class="cartao"><table class="tab">' +
        '<tr><th>Teto</th><th>Recorte</th><th>Responsável</th>' +
        '<th class="status-celula">Estado</th><th class="acao-celula">Ação</th></tr>' +
        outras.map(function(p){
          return '<tr><td>' + pct(p.teto_pct, 1) + '</td>' +
            '<td class="alvo">' + esc((p.canal || 'todos') + ' · ' + (p.categoria || 'todas')) + '</td>' +
            '<td>' + esc(p.responsavel) + '</td>' +
            '<td class="status-celula">' + esc((PASSOS.filter(function(x){ return x.id === p.estado; })[0] || {}).rotulo || p.estado) + '</td>' +
            '<td class="acao-celula"><button class="btn" type="button" data-abrir="' +
              esc(p.id) + '">Abrir</button></td></tr>';
        }).join('') + '</table></div>'
      : '';

    // Histórico COMPLETO, não o do recorte: filtrado, dava a impressão de que
    // as políticas dos outros recortes tinham sumido do arquivo.
    var h = d.historico_completo || d.historico || [];
    var hist = '<h2 class="sec">Histórico de políticas aplicadas</h2><div class="cartao">' + (h.length
      ? '<table class="tab"><tr><th>Vigente desde</th><th>Canal</th><th>Categoria</th>' +
        '<th>Responsável</th><th class="num">Teto</th></tr>' +
        h.map(function(e){
          return '<tr><td>' + esc(data(e.vigencia)) + '</td><td>' + esc(e.canal || 'todos') +
            '</td><td>' + esc(e.categoria || 'todas') + '</td><td>' + esc(e.responsavel) +
            '</td><td class="num">' + pct(e.teto_pct, 1) + '</td></tr>';
        }).join('') + '</table>'
      : '<div class="vazio">Nenhuma política aplicada ainda.</div>') + '</div>';

    return htmlFilaAprovacao(filaAprovacao) +
      htmlProposta(propostaAberta) +
      htmlCenarios(cen) +
      '<h2 class="sec">Vigente agora</h2>' +
      consulta + '<div id="polVigente">' + htmlVigente(d.vigente, d.impacto) + '</div>' +
      form + lista + hist;
  }

  function ligarPolitica(){
    ['recCanal', 'recCategoria'].forEach(function(id){
      var campo = el(id);
      if(!campo) return;
      campo.addEventListener('change', function(){
        recorte.canal = el('recCanal').value;
        recorte.categoria = el('recCategoria').value;
        carregarPolitica();
      });
    });

    // Transições do fluxo. Cada uma leva QUEM está fazendo — sem isso a API
    // recusa, e é essa recusa que garante o registro de responsabilidade.
    document.querySelectorAll('[data-transicao]').forEach(function(b){
      b.addEventListener('click', function(){
        if(!propostaAberta) return;
        var quem = (el('polQuem') && el('polQuem').value || '').trim();
        var alvo = el('polAviso');
        if(!quem){
          if(alvo) alvo.innerHTML = '<div class="erro-box">Informe quem está fazendo esta transição.</div>';
          return;
        }
        b.disabled = true;
        pegar('/api/politica/' + encodeURIComponent(propostaAberta.id) + '/' +
              b.getAttribute('data-transicao'), {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ quem: quem })
        }).then(function(p){
          propostaAberta = p;
          carregarPolitica();
          // A tela de monitoramento passa a ter o que mostrar quando a
          // proposta fica ativa: força a recarga na próxima visita.
          carregado.monitoramento = false;
        }).catch(function(e){
          b.disabled = false;
          if(alvo) alvo.innerHTML = '<div class="erro-box">' + esc(e.message) + '</div>';
        });
      });
    });

    document.querySelectorAll('[data-abrir]').forEach(function(b){
      b.addEventListener('click', function(){
        propostaAberta = { id: b.getAttribute('data-abrir') };
        carregarPolitica();
      });
    });

    var form = el('polForm');
    if(!form) return;
    ligarCampoData('polVigencia');

    form.addEventListener('submit', function(ev){
      ev.preventDefault();
      var botao = form.querySelector('button[type=submit]');
      var f = new FormData(form);
      botao.disabled = true;
      pegar('/api/politica/propostas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          canal: f.get('canal') || null,
          categoria: f.get('categoria') || null,
          teto_pct: Number(f.get('teto_pct')),
          responsavel: f.get('responsavel'),
          // O campo é DD/MM/AAAA na tela; para a API vai o AAAA-MM-DD de sempre.
          vigencia: isoDoCampo('polVigencia') || null
        })
      }).then(function(p){
        propostaAberta = p;
        carregarPolitica();
      }).catch(function(e){
        botao.disabled = false;
        var a = el('polAvisoNovo');
        if(a) a.innerHTML = '<div class="erro-box">' + esc(e.message) + '</div>';
      });
    });
  }

  /* ====================================================== monitoramento
     Honestidade antes de funcionalidade: enquanto nenhuma política foi
     aprovada, não existe teste rodando, e a tela DIZ isso. A regra de parada
     aparece mesmo assim porque é configuração — ela existe antes do teste.
     Os campos de resultado ficam explicitamente indisponíveis: preenchê-los
     com estimativa seria apresentar simulação como resultado apurado. */
  function carregarMonitoramento(){
    var alvo = el('monConteudo');
    alvo.innerHTML = carregando();
    pegar('/api/monitoramento')
      .then(function(d){ alvo.innerHTML = htmlMonitoramento(d); ligarMonitoramento(); })
      .catch(function(e){ alvo.innerHTML = falha(e); });
  }

  // Campo sem dado NÃO recebe travessão discreto: recebe o motivo de estar
  // vazio, para ninguém ler ausência como zero.
  function kpiIndisponivel(rotulo, motivo){
    return '<div class="kpi"><div class="kpi-lbl">' + esc(rotulo) + '</div>' +
           '<span class="kpi-val-vazio" aria-label="sem valor"></span>' +
           '<div class="kpi-ctx">' + esc(motivo) + '</div></div>';
  }

  function htmlRegraDeParada(regra, desenhoDoTeste){
    if(!regra) return '';
    // O n do documento do case e o n que a base exige são números diferentes,
    // e a diferença é informação: a linha de conferência mostra os dois lado a
    // lado em vez de deixar a tela afirmar um e calcular o outro.
    var conferencia = '';
    if(desenhoDoTeste && desenhoDoTeste.unidades){
      var porPedido = desenhoDoTeste.unidades.filter(function(u){
        return u.unidade === 'pedido';
      })[0];
      if(porPedido){
        conferencia = '<tr><td>Conferido contra a base</td><td>' +
          num(porPedido.n_por_grupo) + ' pedidos por grupo</td></tr>';
      }
    }
    // O veredicto só existe quando há dado medido; sem ele, a regra é só a
    // configuração — e é assim que ela aparece.
    var veredicto = regra.veredicto
      ? '<tr><td>Veredicto agora</td><td>' +
        '<span class="badge ' + (regra.veredicto === 'parar' ? 'negative' :
          (regra.veredicto === 'continuar' ? 'positive' : 'neutral')) + '">' +
        '<i class="badge-dot"></i>' + esc(regra.veredicto) + '</span> ' +
        esc(regra.explicacao || '') + '</td></tr>'
      : '';
    return '<h2 class="sec">Regra de parada</h2>' +
      '<div class="cartao"><table class="tab">' +
        '<tr><th>Item</th><th>Valor</th></tr>' +
        '<tr><td>Critério de parada</td><td>' + esc(regra.criterio) + '</td></tr>' +
        '<tr><td>Duração mínima</td><td>' + num(regra.duracao_minima_semanas) + ' semanas</td></tr>' +
        '<tr><td>Amostra mínima por grupo</td><td>' + num(regra.amostra_minima_por_grupo) + ' pedidos</td></tr>' +
        '<tr><td>Significância</td><td>' + pct(regra.significancia * 100, 0) +
          ' de probabilidade de falso positivo</td></tr>' +
        conferencia +
        veredicto +
        '<tr><td>Origem</td><td>' + esc(regra.fonte) + '</td></tr>' +
      '</table></div>';
  }

  function htmlMonitoramento(d){
    var aguardando = d.estado === 'aguardando';
    var p = d.proposta;
    propostaEmTeste = p;

    // Título: o que está em teste, com a pílula de status ao lado.
    definirTitulo('monitoramento', 'Monitoramento de políticas',
      p ? 'Teto de desconto — ' + pct(p.teto_pct, 0) +
          (p.canal ? ', ' + p.canal : ', todos os canais')
        : 'Nenhuma política em teste ainda', '');
    var cabeca = el('head-monitoramento');
    if(cabeca){
      var pill = cabeca.querySelector('.mon-status');
      if(!pill){
        pill = document.createElement('span');
        pill.className = 'mon-status';
        cabeca.appendChild(pill);
      }
      pill.className = 'mon-status' + (aguardando ? '' : ' ativa');
      pill.innerHTML = '<span class="achado-ponto"></span>' +
        (aguardando ? esc(d.titulo || 'Sem política em teste')
                   : 'Política ' + esc(d.estado));
    }

    var cabecalho = '<div class="mon-faixa"><span class="ico" data-ico="clock"></span>' +
      '<span>' + esc(d.explicacao) + '</span></div>' +
      (aguardando
        ? '<div class="acao-linha"><button class="btn" type="button" data-ir="politica">' +
          'Abrir fluxo de políticas</button></div>'
        : '');

    var proposta = '';
    if(d.proposta){

      proposta = '<h2 class="sec">Proposta em teste</h2><div class="cartao">' +
        htmlStepper(p.estado) +
        '<div class="kpis" style="margin-top:var(--space-4)">' +
          kpi('Teto aplicado', pct(p.teto_pct, 1),
              (p.canal || 'todos os canais') + ' · ' + (p.categoria || 'todas as categorias')) +
          kpi('Aprovada por', (p.politica_aplicada || {}).responsavel || p.responsavel) +
          kpi('Em vigor desde', data((p.politica_aplicada || {}).vigencia)) +
        '</div></div>';
    }

    var r = d.resultados || {};
    var res = d.resultado_experimento || {};
    var motivo = esc(d.por_que_sem_numeros || 'sem dado do experimento');
    // Versão curta para o rodapé dos KPIs: o motivo longo já está no
    // parágrafo da seção, e repeti-lo quatro vezes só afasta os rótulos.
    var motivoCurto = d.experimento ? 'sem pedido na janela do teste'
                                    : 'nenhum experimento desenhado';
    var temDado = !!res.disponivel;

    var resultados = '<h2 class="sec">Resultado do teste</h2>' +
      '<p class="meta">' + (temDado
        ? 'Medido na janela ' + esc(data(res.janela[0])) + ' a ' + esc(data(res.janela[1])) +
          ' · ' + num(res.pedidos_na_janela) + ' pedidos · ' +
          num(res.unidades_controle) + ' no controle e ' + num(res.unidades_teste) +
          ' no teste, por aleatorização de ' + esc(res.unidade) + '.'
        : motivo) + '</p>' +
      '<div class="kpis">' +
        (r.margem_preservada_real_reais != null
          ? kpi('Margem preservada (medida)', brl(r.margem_preservada_real_reais),
                'diferença entre os grupos na janela')
          : kpiIndisponivel('Margem preservada (medida)', motivoCurto)) +
        (r.volume_grupo_controle != null
          ? kpi('Volume — controle', num(Math.round(r.volume_grupo_controle * 100) / 100),
                'pedidos por unidade')
          : kpiIndisponivel('Volume — controle', motivoCurto)) +
        (r.volume_grupo_teste != null
          ? kpi('Volume — com teto', num(Math.round(r.volume_grupo_teste * 100) / 100),
                'pedidos por unidade')
          : kpiIndisponivel('Volume — com teto', motivoCurto)) +
        (r.diferenca_relativa_pct != null
          ? kpi('Diferença', pct(r.diferenca_relativa_pct),
                'p = ' + (r.p_valor != null
                  ? Number(r.p_valor).toFixed(4).replace('.', ',') : '—'))
          : kpiIndisponivel('Diferença vs. controle', motivoCurto)) +
      '</div>' +
      '';

    return cabecalho + proposta + htmlExperimento(d) + resultados +
           htmlRegraDeParada(d.regra_de_parada, d.desenho);
  }

  /* O desenho do experimento: semente, unidade de aleatorização e janela. É o
     que permite a alguém conferir a atribuição depois — sem isso, "grupo de
     controle" é palavra, não método. */
  function htmlExperimento(d){
    var e = d.experimento;
    if(!e){
      return '<h2 class="sec">Teste A/B</h2>' +
        aviso('Sem grupo de controle, o ganho do teto continua sendo ' +
              '<strong>estimativa</strong>.') +
        (d.proposta ? htmlFormExperimento(d.proposta) : '');
    }
    return '<h2 class="sec">Teste A/B</h2>' + htmlAcoesExperimento(e);
  }

  /* Ciclo de vida do experimento. Cada transição leva QUEM — a API recusa sem
     isso, e é essa recusa que produz o registro de responsabilidade. Encerrar
     exige MOTIVO pelo mesmo motivo: parar um teste sem dizer por quê apaga a
     única informação que a parada carrega. */
  function htmlAcoesExperimento(e){
    if(e.estado === 'encerrado'){
      return '<div class="cartao">' + aviso('Teste encerrado em ' +
        esc(data(e.encerrado_em)) + ' — motivo: ' + esc(e.motivo_encerramento || '—')) +
        '</div>';
    }
    var campos =
      '<label class="campo"><span>Quem</span>' +
      '<input type="text" id="expQuem" placeholder="nome de quem responde"></label>';
    var acao = e.estado === 'planejado'
      ? '<label class="campo"><span>Início (opcional)</span>' +
        '<input type="text" id="expInicio" placeholder="DD/MM/AAAA"></label>' +
        '<div class="campo acao"><button class="btn primary" type="button" ' +
        'data-exp="iniciar" data-id="' + esc(e.id) + '">Iniciar teste</button></div>'
      : '<label class="campo"><span>Motivo</span>' +
        '<input type="text" id="expMotivo" placeholder="por que está parando"></label>' +
        '<div class="campo acao"><button class="btn" type="button" ' +
        'data-exp="encerrar" data-id="' + esc(e.id) + '">Encerrar teste</button></div>';
    return '<div class="cartao"><div class="form">' + campos + acao + '</div>' +
      '<div id="expAviso"></div></div>';
  }

  /* Desenhar o experimento é uma DECISÃO registrada, não efeito colateral de
     aprovar a política: tem dono, data e semente, e é isso que torna a
     atribuição auditável depois. Por isso o formulário é explícito. */
  function htmlFormExperimento(p){
    return '<div class="cartao">' +
      '<p class="p">Desenhar o teste para o teto de ' + pct(p.teto_pct, 1) + '.</p>' +
      '<div class="form">' +
        '<label class="campo"><span>Responsável</span>' +
        '<input type="text" id="expResp" placeholder="quem desenha"></label>' +
        '<label class="campo"><span>Unidade</span>' +
        '<select id="expUnidade">' +
          '<option value="cliente">Cliente — mede volume</option>' +
          '<option value="pedido">Pedido — mede margem</option>' +
        '</select></label>' +
        '<label class="campo"><span>Duração (dias)</span>' +
        '<input type="text" id="expDias" value="30"></label>' +
        '<div class="campo acao"><button class="btn primary" type="button" ' +
        'data-exp="criar">Desenhar teste A/B</button></div>' +
      '</div><div id="expAviso"></div></div>';
  }

  function ligarMonitoramento(){
    document.querySelectorAll('#monConteudo [data-ir]').forEach(function(b){
      b.addEventListener('click', function(){ navegar(b.getAttribute('data-ir')); });
    });
    if(el('expInicio')) ligarCampoData('expInicio');

    document.querySelectorAll('#monConteudo [data-exp]').forEach(function(b){
      b.addEventListener('click', function(){ acaoExperimento(b); });
    });
  }

  function acaoExperimento(b){
    var alvo = el('expAviso');
    function erro(msg){
      if(alvo) alvo.innerHTML = '<div class="erro-box">' + esc(msg) + '</div>';
    }
    var acao = b.getAttribute('data-exp');
    var rota, corpo;

    if(acao === 'criar'){
      var resp = (el('expResp') && el('expResp').value || '').trim();
      var dias = Number(el('expDias') && el('expDias').value);
      if(!resp) return erro('Informe quem está desenhando o teste.');
      if(!(dias > 0)) return erro('A duração precisa ser um número de dias maior que zero.');
      if(!propostaEmTeste) return erro('Nenhuma proposta em teste para associar ao experimento.');
      rota = '/api/experimento';
      corpo = {
        proposta_id: propostaEmTeste.id,
        teto_pct: propostaEmTeste.teto_pct,
        responsavel: resp,
        unidade: el('expUnidade').value,
        duracao_dias: dias,
        canal: propostaEmTeste.canal || null,
        categoria: propostaEmTeste.categoria || null
      };
    } else {
      var quem = (el('expQuem') && el('expQuem').value || '').trim();
      if(!quem) return erro('Informe quem está fazendo esta transição.');
      rota = '/api/experimento/' + encodeURIComponent(b.getAttribute('data-id')) +
             '/' + acao;
      corpo = { quem: quem };
      if(acao === 'iniciar'){
        corpo.inicio = el('expInicio') ? (isoDoCampo('expInicio') || null) : null;
      }
      if(acao === 'encerrar'){
        var motivo = (el('expMotivo') && el('expMotivo').value || '').trim();
        if(!motivo) return erro('Encerrar um teste exige o motivo declarado.');
        corpo.motivo = motivo;
      }
    }

    b.disabled = true;
    pegar(rota, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify(corpo) })
      .then(function(){ carregarMonitoramento(); })
      .catch(function(e){ b.disabled = false; erro(e.message); });
  }

  /* Aviso de configuração: sem chave e sem mock, o chat não responde — melhor
     dizer isso na navegação do que deixar a pessoa descobrir no erro. */
  pegar('/api/health').then(function(h){
    if(h.etapas_habilitadas) etapasHabilitadas = h.etapas_habilitadas;
    if(h.ok) return;
    el('avisoConfig').innerHTML =
      '<div class="erro-box">ELOAGENTS_API_KEY não configurada — o chat não vai ' +
      'responder. Relatório, auditoria e política funcionam normalmente.</div>';
  }).catch(function(){});

  mostrar('visao');
})();
