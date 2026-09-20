(function(){
  "use strict";

  /* =========================================================
     MODO DEMONSTRAÇÃO
     -----------------------------------------------------------
     MOCK_MODE = true faz o chat responder com textos simulados,
     gerados aqui no front-end, sem nenhuma chamada de rede.

     Para ligar ao backend real:
       1) Troque MOCK_MODE para false.
       2) Implemente a função sendToBackend(message, history) mais
          abaixo, apontando para o endpoint do seu agente.
     ========================================================= */
  var MOCK_MODE = false;

  var root = document.documentElement;
  // A rolagem das mensagens é a do painel de chat, não a da tela de fundo:
  // a ferramenta aberta continua rolando por conta própria atrás dele.
  var scrollArea = document.getElementById('chatScroll');
  var chatPanel = document.getElementById('chatPanel');
  var chatCorpo = document.getElementById('chatCorpo');
  var chatHostTela = document.getElementById('chatHostTela');
  var chatFab = document.getElementById('chatFab');
  var chatFechar = document.getElementById('chatFechar');
  var chatExpandir = document.getElementById('chatExpandir');
  var emptyState = document.getElementById('emptyState');
  var msgList = document.getElementById('msgList');
  var input = document.getElementById('composerInput');
  var sendBtn = document.getElementById('sendBtn');
  var themeBtn = document.getElementById('themeBtn');
  var newChatBtn = document.getElementById('newChatBtn');
  var dismissBanner = document.getElementById('dismissBanner');
  var demoBanner = document.getElementById('demoBanner');

  var history = []; // {role: 'user'|'assistant', content: string}

  // O aviso de "modo demonstração" é HTML estático — sem isso ele aparece
  // mesmo com o backend real já ligado (MOCK_MODE=false), o que confunde
  // quem abre o chat depois. Remove automaticamente quando não é mock.
  if(!MOCK_MODE && demoBanner){
    demoBanner.remove();
  }

  /* ---------------- Painel de chat ----------------
     O chat não é mais uma tela: é um painel que desliza por cima da
     ferramenta aberta. Abrir e fechar não troca de tela — mas a tela vigente
     é guardada mesmo assim, para o caso de a navegação acontecer com o painel
     aberto: ao fechar, volta-se para onde a pessoa estava. */
  var viewAntesDoChat = null;
  var emModoTela = false;      // conversa hospedada na tela própria do agente
  var timerDeFechar = null;

  // O estado vem da classe, não do atributo `hidden`: entre o fim do clique e
  // o fim da animação de saída o painel ainda está no fluxo, mas já fechado.
  function chatAberto(){
    return !!chatPanel && chatPanel.classList.contains('open');
  }
  function abrirChat(){
    // Na tela do próprio agente não há o que sobrepor: a conversa já está ali.
    if(!chatPanel || chatAberto() || emModoTela) return;
    var painel = window.MarginGuardPainel;
    viewAntesDoChat = painel ? painel.viewAtual() : null;
    clearTimeout(timerDeFechar);
    chatPanel.hidden = false;
    // O 'open' entra num quadro à parte para a transição de entrada acontecer:
    // elemento que nasce sem `hidden` e com a classe junto aparece sem deslizar.
    requestAnimationFrame(function(){ chatPanel.classList.add('open'); });
    chatFab.setAttribute('aria-expanded', 'true');
    input.focus();
    scrollToBottom();
  }
  /* `restaurar` só é falso quando quem fechou foi a própria navegação (a
     pessoa clicou em outra ferramenta com o painel aberto) — aí a tela nova é
     a que deve ficar, não a anterior. */
  function fecharChat(restaurar){
    if(!chatPanel || !chatAberto()) return;
    chatPanel.classList.remove('open');
    clearTimeout(timerDeFechar);
    // `hidden` só depois da animação de saída; antes disso o painel sumiria
    // de uma vez em vez de deslizar.
    timerDeFechar = setTimeout(function(){
      if(!chatPanel.classList.contains('open')) chatPanel.hidden = true;
    }, 240);
    chatFab.setAttribute('aria-expanded', 'false');
    chatFab.focus();
    var painel = window.MarginGuardPainel;
    if(restaurar !== false && painel && viewAntesDoChat &&
       painel.viewAtual() !== viewAntesDoChat){
      painel.mostrar(viewAntesDoChat);
    }
    viewAntesDoChat = null;
  }

  if(chatFab) chatFab.addEventListener('click', function(){
    chatAberto() ? fecharChat() : abrirChat();
  });
  if(chatFechar) chatFechar.addEventListener('click', function(){ fecharChat(); });
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape' && chatAberto()) fecharChat();
  });

  /* ---------------- Duas casas, uma conversa ----------------
     O agente é destino (tela própria) E atalho (botão flutuante). Em vez de
     duas instâncias do chat com históricos separados, o CORPO do chat é
     movido entre os dois hospedeiros: mover um nó no DOM preserva os
     ouvintes e o estado, então a conversa continua exatamente onde estava ao
     trocar de forma. É isso que sustenta "acessível de qualquer tela" sem
     partir a conversa em duas. */
  // (declarada junto do estado do painel, mais acima)

  function modoTela(ligar){
    if(!chatCorpo || !chatHostTela || emModoTela === !!ligar) return;
    emModoTela = !!ligar;
    if(emModoTela){
      fecharChat(false);                 // o flutuante some; a tela assume
      chatHostTela.appendChild(chatCorpo);
    } else {
      chatPanel.appendChild(chatCorpo);
    }
    document.body.classList.toggle('chat-em-tela', emModoTela);
    if(emModoTela){ input.focus(); scrollToBottom(); }
  }

  // Do painel flutuante para a tela cheia, levando a conversa junto.
  if(chatExpandir) chatExpandir.addEventListener('click', function(){
    if(window.MarginGuardPainel) window.MarginGuardPainel.mostrar('marginguard');
  });

  // A navegação entre as telas vive em painel.js; ele fecha o painel flutuante
  // e alterna o modo de tela por estas funções, em vez de duplicar a lógica.
  window.MarginGuardUI = {
    abrirChat: abrirChat, fecharChat: fecharChat, chatAberto: chatAberto,
    modoTela: modoTela
  };

  /* ---------------- Tema ----------------
     O claro é o tema do produto: `prefers-color-scheme` do sistema NÃO é
     consultado aqui de propósito. Quem estiver com o sistema no escuro abre
     o MarginGuard no claro do mesmo jeito; o escuro só entra pelo toggle.
     A escolha fica guardada e volta na próxima visita. */
  var CHAVE_TEMA = 'marginguard:tema';

  function temaGuardado(){
    try {
      var t = window.localStorage.getItem(CHAVE_TEMA);
      return (t === 'dark' || t === 'light') ? t : null;
    } catch(e){ return null; }   // localStorage bloqueado (aba anônima, política)
  }
  function guardarTema(t){
    try { window.localStorage.setItem(CHAVE_TEMA, t); } catch(e){ /* sem persistir */ }
  }
  function currentEffectiveTheme(){
    return root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  }
  function aplicarTema(t){
    root.setAttribute('data-theme', t);
    themeBtn.setAttribute('aria-pressed', t === 'dark' ? 'true' : 'false');
    themeBtn.title = t === 'dark' ? 'Voltar ao tema claro' : 'Mudar para o tema escuro';
  }

  aplicarTema(temaGuardado() || 'light');
  themeBtn.addEventListener('click', function(){
    var proximo = currentEffectiveTheme() === 'dark' ? 'light' : 'dark';
    aplicarTema(proximo);
    guardarTema(proximo);
  });

  /* ---------------- Composer ---------------- */
  function autoResize(){
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 140) + 'px';
  }
  input.addEventListener('input', function(){
    autoResize();
    sendBtn.disabled = input.value.trim().length === 0;
  });
  input.addEventListener('keydown', function(e){
    if(e.key === 'Enter' && !e.shiftKey){
      e.preventDefault();
      trySend();
    }
  });
  sendBtn.addEventListener('click', trySend);

  document.querySelectorAll('.suggestion').forEach(function(btn){
    btn.addEventListener('click', function(){
      input.value = btn.getAttribute('data-prompt');
      sendBtn.disabled = false;
      trySend();
    });
  });

  newChatBtn.addEventListener('click', function(){
    history = [];
    msgList.innerHTML = '';
    msgList.hidden = true;
    emptyState.style.display = 'flex';
    input.value = '';
    autoResize();
    sendBtn.disabled = true;
  });

  dismissBanner.addEventListener('click', function(){
    demoBanner.remove();
  });

  function trySend(){
    var text = input.value.trim();
    if(!text) return;
    input.value = '';
    autoResize();
    sendBtn.disabled = true;
    addUserMessage(text);
    requestReply(text);
  }

  /* ---------------- Renderização de mensagens ---------------- */
  function escapeHtml(str){
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  /* ---------------- Caracteres especiais (LaTeX solto) ----------------
     O modelo às vezes escreve estatística em LaTeX ("$R^2 = 0{,}85$",
     "\times 10^{-19}", "\%"). Isso é limpo antes de renderizar.

     Expoente e índice precisam virar <sup>/<sub>, mas renderMarkdownLite
     escapa o HTML depois — então aqui eles saem como marcas de controle
     (invisíveis e não escapáveis) e viram tag em aplicarSupSub(), já no
     fim do pipeline. Middot (·), travessão (—) e seta (→) são pontuação
     de marca e não são tocados. */
  var MARCA_SUP_ABRE = '', MARCA_SUP_FECHA = '';
  var MARCA_SUB_ABRE = '', MARCA_SUB_FECHA = '';

  /* Sintaxe que só existe em fórmula: barra invertida de comando, expoente,
     índice, ou a vírgula decimal escapada. É o que separa "$3,09 \times
     10^{-19}$" (fórmula) de "R$ 241 mil, com p-valor $" (moeda). */
  var TEM_MATEMATICA = /[\\^_]|\{,\}/;

  /* Remove SÓ os pares de "$" que delimitam fórmula de verdade.
     Um "$" sozinho nunca some, e um par cujo miolo não tem sintaxe matemática
     fica intacto — é moeda ("R$ 241 mil"). Quando o par é recusado, a varredura
     recomeça do "$" seguinte, e não depois dele: senão o "$" de "R$" consumiria
     o "$" que de fato abre a fórmula, e a conta apareceria com os cifrões. */
  function removerDelimitadoresDeFormula(t){
    var saida = '';
    var i = 0;
    while(i < t.length){
      var abre = t.indexOf('$', i);
      if(abre === -1) break;
      var fecha = t.indexOf('$', abre + 1);
      if(fecha === -1) break;
      var miolo = t.slice(abre + 1, fecha);
      if(miolo.indexOf('\n') === -1 && TEM_MATEMATICA.test(miolo)){
        saida += t.slice(i, abre) + miolo;
        i = fecha + 1;
      } else {
        saida += t.slice(i, abre + 1);   // o "$" fica onde está
        i = abre + 1;
      }
    }
    return saida + t.slice(i);
  }

  function limparLatex(raw){
    var t = String(raw == null ? '' : raw);
    // Delimitadores de fórmula somem; o conteúdo entre eles permanece.
    t = t.replace(/\$\$([\s\S]*?)\$\$/g, function(tudo, miolo){
      return TEM_MATEMATICA.test(miolo) ? miolo : tudo;
    });
    t = removerDelimitadoresDeFormula(t);
    // Comandos que são, na prática, pontuação de texto.
    t = t.replace(/\\times/g, '×');
    t = t.replace(/\\%/g, '%');
    // Vírgula decimal escapada em LaTeX: 0{,}85 → 0,85
    t = t.replace(/\{,\}/g, ',');
    // Expoentes e índices.
    t = t.replace(/\^\{([^}]*)\}/g, MARCA_SUP_ABRE + '$1' + MARCA_SUP_FECHA);
    t = t.replace(/\^(-?[0-9A-Za-zÀ-ÿ]+)/g, MARCA_SUP_ABRE + '$1' + MARCA_SUP_FECHA);
    t = t.replace(/_\{([^}]*)\}/g, MARCA_SUB_ABRE + '$1' + MARCA_SUB_FECHA);
    return t;
  }

  function aplicarSupSub(html){
    return html
      .split(MARCA_SUP_ABRE).join('<sup>').split(MARCA_SUP_FECHA).join('</sup>')
      .split(MARCA_SUB_ABRE).join('<sub>').split(MARCA_SUB_FECHA).join('</sub>');
  }

  // Pipeline completo de texto do agente: limpa LaTeX → markdown → sup/sub.
  function renderTexto(raw){
    return aplicarSupSub(renderMarkdownLite(limparLatex(raw)));
  }

  // Suporte leve a markdown: **negrito**, quebras de linha e listas com "- "
  function renderMarkdownLite(raw){
    var escaped = escapeHtml(raw);
    var lines = escaped.split('\n');
    var html = '';
    var inList = false;
    lines.forEach(function(line){
      var trimmed = line.trim();
      if(trimmed.indexOf('- ') === 0){
        if(!inList){ html += '<ul>'; inList = true; }
        html += '<li>' + trimmed.slice(2) + '</li>';
      } else {
        if(inList){ html += '</ul>'; inList = false; }
        if(trimmed.length){ html += '<p>' + trimmed + '</p>'; }
      }
    });
    if(inList) html += '</ul>';
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    return html || '<p></p>';
  }

  function showMsgList(){
    if(emptyState.style.display !== 'none'){
      emptyState.style.display = 'none';
      msgList.hidden = false;
    }
  }

  function scrollToBottom(){
    scrollArea.scrollTop = scrollArea.scrollHeight;
  }

  function addUserMessage(text){
    showMsgList();
    history.push({role:'user', content:text});
    var el = document.createElement('div');
    el.className = 'msg user';
    el.innerHTML =
      '<div class="msg-col"><div class="bubble"></div></div>';
    el.querySelector('.bubble').innerHTML = renderMarkdownLite(text);
    msgList.appendChild(el);
    scrollToBottom();
  }

  function addTypingIndicator(){
    var el = document.createElement('div');
    el.className = 'msg assistant';
    el.id = 'typingRow';
    el.innerHTML =
      '<div class="msg-col"><div class="bubble typing"><span></span><span></span><span></span></div></div>';
    msgList.appendChild(el);
    scrollToBottom();
    return el;
  }

  function assistantIconSvg(){
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.5 6.5l2.8 2.8M14.7 14.7l2.8 2.8M6.5 17.5l2.8-2.8M14.7 9.3l2.8-2.8"/></svg>';
  }

  /* ---------------- Formato canônico da resposta ----------------
     A resposta final chega sempre como "FATO:", "INFERÊNCIA:",
     "RECOMENDAÇÃO:" e "FORÇA DA EVIDÊNCIA:" — o backend normaliza antes
     de devolver, então aqui não há tratamento de variação de markdown
     nem de acento. Devolve null quando o texto não está nesse formato
     (erro de rede, aviso do front): nesse caso a bolha é o texto inteiro. */
  function separarSecoes(texto){
    var mapa = {
      'FATO': 'fato',
      'INFERÊNCIA': 'inferencia',
      'RECOMENDAÇÃO': 'recomendacao',
      'FORÇA DA EVIDÊNCIA': 'forca'
    };
    var re = /(^|\n)[ \t]*(FATO|INFERÊNCIA|RECOMENDAÇÃO|FORÇA DA EVIDÊNCIA)[ \t]*:/g;
    var marcas = [];
    var m;
    while((m = re.exec(texto)) !== null){
      marcas.push({
        chave: mapa[m[2]],
        inicioMarca: m.index + (m[1] ? m[1].length : 0),
        inicioTexto: m.index + m[0].length
      });
    }
    if(!marcas.length) return null;
    var out = { fato:'', inferencia:'', recomendacao:'', forca:'' };
    for(var i = 0; i < marcas.length; i++){
      var fim = (i + 1 < marcas.length) ? marcas[i + 1].inicioMarca : texto.length;
      out[marcas[i].chave] = texto.slice(marcas[i].inicioTexto, fim).trim();
    }
    return out;
  }

  /* ---------------- Cinco campos de leitura ----------------
     O backend continua com o contrato de QUATRO seções (FATO / INFERÊNCIA /
     RECOMENDAÇÃO / FORÇA DA EVIDÊNCIA) — é ele que sustenta o guardrail de
     verificação numérica e os testes de aceite, e não foi tocado.

     A exibição é que reetiqueta e divide: a premissa, que o modelo escreve
     dentro da RECOMENDAÇÃO prefixada por "PREMISSA:", vira campo próprio.
     São nomes de tela, não de contrato.

         FATO               → Resposta   (corpo da bolha, sempre visível)
         RECOMENDAÇÃO       → Recomendação (callout, sempre visível)
         PREMISSA:          → Premissa   (atrás do toggle)
         INFERÊNCIA         → Impacto    (atrás do toggle)
         FORÇA DA EVIDÊNCIA → Evidência  (badge, atrás do toggle) */

  /* A cláusula de premissa começa em "PREMISSA:" e termina onde começa o
     próximo elemento obrigatório da recomendação (Controle ou Dono) ou o
     parágrafo acaba. O limite importa: sem ele, a premissa engolia o controle
     e o dono, que são elementos separados e precisam continuar na
     recomendação. Sem o prefixo — modelo antigo, resposta fora do padrão — a
     recomendação fica inteira e o campo Premissa não aparece. */
  var RE_PREMISSA = /(^|\n|\.\s+)PREMISSA\s*:\s*([\s\S]*?)(?=\s(?:controle|dono)\s*:|\n\s*\n|$)/i;

  function separarPremissa(recomendacao){
    var texto = String(recomendacao || '');
    var m = RE_PREMISSA.exec(texto);
    if(!m) return { recomendacao: texto.trim(), premissa: '' };
    var premissa = (m[2] || '').trim();
    var resto = (texto.slice(0, m.index) + (m[1] === '\n' || m[1] === '' ? '' : m[1]) +
                 texto.slice(m.index + m[0].length)).trim();
    return { recomendacao: resto || texto.trim(), premissa: premissa };
  }

  // Badge de evidência — espelha components/display/Badge.jsx.
  function tomDaForca(forca){
    var t = String(forca || '').toUpperCase();
    if(t.indexOf('FORTE') !== -1) return 'positive';
    if(t.indexOf('MODERADA') !== -1) return 'warning';
    if(t.indexOf('FRACA') !== -1) return 'negative';
    return 'neutral';
  }

  /* ---------------- Trilha de auditoria ----------------
     Dois níveis, de propósito. Primeiro uma frase em linguagem de negócio
     dizendo COMO a resposta foi calculada — é o que um leitor executivo
     precisa para confiar no número. Só depois, atrás de outro toggle, o nome
     de função e os parâmetros, que é o que um auditor precisa para repetir a
     conta. A trilha não sumiu: ganhou uma porta de entrada legível. */

  // Como cada ferramenta se lê em português. Chave = nome no motor.
  var FERRAMENTA_EM_PORTUGUES = {
    margem_consolidada: 'apurando a margem consolidada da base',
    margem_na_janela: 'apurando a margem da janela e a do período anterior',
    margem_por_dimensao: 'abrindo a margem por dimensão',
    pedidos_margem_negativa: 'levantando os pedidos com margem negativa',
    simular_teto_desconto: 'simulando o teto de desconto',
    simular_desconto_em_segmento: 'simulando desconto no segmento',
    simular_reajuste_preco: 'simulando reajuste de preço',
    custo_assimetria_frete: 'medindo a assimetria de frete entre canais',
    regra_frete_por_limiar: 'simulando a regra de frete por limiar',
    politica_frete_por_canal: 'consultando a política de frete por canal',
    impacto_devolucoes: 'medindo o impacto das devoluções',
    perda_pos_pedido: 'abrindo a perda depois do pedido',
    pendencias_antigas: 'levantando as pendências antigas',
    tabela_faixas_desconto: 'comparando as faixas de desconto',
    pedidos_acima_do_teto: 'contando os pedidos acima do teto',
    cenarios_reducao_desconto: 'comparando cenários de redução de desconto',
    kpis_do_teto: 'apurando os KPIs do teto',
    caso_base_do_plano: 'montando o caso-base do plano',
    consultar_politica_desconto: 'consultando a política de desconto vigente',
    classificar_evidencia: 'classificando a força da evidência',
    qui_quadrado_independencia: 'testando independência por qui-quadrado',
    teste_t_welch: 'comparando médias por teste t de Welch',
    anova_um_fator: 'comparando grupos por ANOVA',
    regressao_linear_multipla: 'ajustando uma regressão linear múltipla',
    indice_sazonalidade: 'medindo a sazonalidade',
    tendencia_ajustada_sazonalidade: 'medindo a tendência ajustada por sazonalidade',
    comparar_periodos: 'comparando dois períodos',
    dispersao_componentes_entre_canais: 'medindo a dispersão entre canais',
    ranking_roas_canais: 'ordenando os canais por ROAS',
    cobertura_de_dados: 'verificando a cobertura dos dados',
    relatorio_auditoria_dados: 'rodando as checagens de qualidade da base',
    verificar_consistencia_categorica: 'cruzando duas colunas categóricas'
  };

  // Os parâmetros que valem a pena aparecer numa frase de negócio.
  function parametrosEmPortugues(p){
    if(!p) return '';
    var partes = [];
    if(p.teto_pct != null) partes.push('teto de ' + p.teto_pct + '%');
    if(p.canal) partes.push('no canal ' + p.canal);
    if(p.categoria) partes.push('na categoria ' + p.categoria);
    if(p.dimensao) partes.push('por ' + p.dimensao);
    if(p.ano) partes.push('em ' + p.ano);
    if(p.dias) partes.push('numa janela de ' + p.dias + ' dias');
    if(p.excluir_meses && p.excluir_meses.length){
      var MES = ['janeiro','fevereiro','março','abril','maio','junho','julho',
                 'agosto','setembro','outubro','novembro','dezembro'];
      partes.push('com ' + p.excluir_meses.map(function(m){
        return MES[m - 1] || ('mês ' + m); }).join(' e ') + ' fora');
    }
    if(p.limiar_frete_gratis != null) partes.push('com frete grátis a partir de R$ ' + p.limiar_frete_gratis);
    return partes.join(', ');
  }

  /* A frase que abre a trilha. Junta as ferramentas na ordem em que rodaram,
     em português, sem nome de função. */
  function frasePasso(p){
    var base = FERRAMENTA_EM_PORTUGUES[p.ferramenta] || ('usando ' + p.ferramenta);
    var params = parametrosEmPortugues(p.parametros);
    return base + (params ? ' (' + params + ')' : '');
  }

  function fraseDeNegocio(passos){
    if(!passos.length) return 'Nenhuma ferramenta foi executada nesta consulta.';
    var frases = [];
    passos.forEach(function(p){
      var f = frasePasso(p);
      if(frases.indexOf(f) === -1) frases.push(f);   // não repete a mesma leitura
    });
    var texto = frases.length === 1 ? frases[0]
      : frases.slice(0, -1).join('; ') + '; e ' + frases[frases.length - 1];
    return 'Calculado ' + texto + '.';
  }

  function montarTrilha(traceId, destino){
    destino.innerHTML = '<p class="trilha-meta">Carregando trilha…</p>';
    fetch('/api/trace/' + encodeURIComponent(traceId))
      .then(function(res){
        if(!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function(trace){
        var passos = (trace.passos || []).filter(function(p){
          return p.tipo === 'acao' && p.ferramenta;
        });

        // Nível 1: a leitura de negócio.
        var html = '<p class="trilha-frase">' + escapeHtml(fraseDeNegocio(passos)) + '</p>' +
          '<p class="trilha-meta">trace ' + escapeHtml(trace.id || traceId) +
          ' · ' + passos.length + ' chamada(s)' +
          (trace.duracao_s != null ? ' · ' + escapeHtml(String(trace.duracao_s)) + 's' : '') +
          '</p>';

        // Nível 2: o detalhe técnico, para quem vai repetir a conta.
        if(passos.length){
          html += '<details class="trilha-tecnica"><summary>Ver chamadas técnicas</summary><ol>';
          passos.forEach(function(p){
            var params = (p.parametros && Object.keys(p.parametros).length)
              ? JSON.stringify(p.parametros) : '{}';
            html += '<li><span class="trilha-ferramenta">' + escapeHtml(p.ferramenta) + '</span> ' +
                    '<span class="trilha-param">' + escapeHtml(params) + '</span>' +
                    (p.origem ? ' <span class="trilha-param">· ' + escapeHtml(p.origem) + '</span>' : '') +
                    '</li>';
          });
          html += '</ol></details>';
        }
        destino.innerHTML = html;
      })
      .catch(function(err){
        destino.innerHTML = '<p class="trilha-erro">Não foi possível carregar a trilha: ' +
          escapeHtml(err && err.message ? err.message : String(err)) + '</p>';
      });
  }

  /* Monta, abaixo da bolha, o que não é a Resposta: o callout de Recomendação
     (sempre visível) e o painel com Impacto, Premissa, Evidência e trilha. */
  function montarPartesDaResposta(col, secoes, traceId){
    var partido = separarPremissa(secoes.recomendacao);

    if(partido.recomendacao){
      var callout = document.createElement('div');
      callout.className = 'callout-rec';
      callout.innerHTML =
        '<div class="callout-rec-label">Recomendação</div>' +
        '<div class="callout-rec-body">' + renderTexto(partido.recomendacao) + '</div>';
      col.appendChild(callout);
    }

    var temBase = !!(secoes.inferencia || partido.premissa || secoes.forca || traceId);
    if(!temBase) return;

    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'base-toggle';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.textContent = '[ VER BASE DA RESPOSTA ]';

    var painel = document.createElement('div');
    painel.className = 'base-panel';
    painel.hidden = true;

    function secao(rotulo, corpoHtml){
      var d = document.createElement('div');
      d.className = 'base-secao';
      d.innerHTML = '<div class="base-label">' + rotulo + '</div>' + corpoHtml;
      painel.appendChild(d);
    }

    // INFERÊNCIA vira "Impacto": o que o número significa para o negócio.
    if(secoes.inferencia){
      secao('Impacto', '<div class="base-texto">' + renderTexto(secoes.inferencia) + '</div>');
    }

    // A premissa sai da recomendação e ganha campo próprio — é a condição sob
    // a qual o valor vale, e some quando fica no meio de um parágrafo.
    if(partido.premissa){
      secao('Premissa', '<div class="base-texto">' + renderTexto(partido.premissa) + '</div>');
    }

    if(secoes.forca){
      // A força quase sempre vem como "FORTE, sustentada pelo teste de ...":
      // o badge fica só com a palavra de tom (rótulo curto, como manda o
      // Badge.jsx) e a justificativa desce como texto de apoio. Sem isso a
      // frase inteira dentro da pill estica a coluna e rola a página.
      var forca = limparLatex(secoes.forca);
      var corte = /^\s*(FORTE|MODERADA|FRACA)\b[\s,:;.\-–—]*/i.exec(forca);
      var rotulo = corte ? corte[1].toUpperCase() : forca;
      var detalhe = corte ? forca.slice(corte[0].length).trim() : '';
      if(detalhe) detalhe = detalhe.charAt(0).toUpperCase() + detalhe.slice(1);

      secao('Evidência',
        '<div><span class="badge ' + tomDaForca(secoes.forca) + '">' +
          '<i class="badge-dot"></i>' + escapeHtml(rotulo) +
        '</span></div>' +
        (detalhe ? '<div class="base-texto">' + renderTexto(detalhe) + '</div>' : ''));
    }

    if(traceId){
      var trilhaBtn = document.createElement('button');
      trilhaBtn.type = 'button';
      trilhaBtn.className = 'trilha-toggle';
      trilhaBtn.setAttribute('aria-expanded', 'false');
      trilhaBtn.textContent = 'Ver trilha de auditoria completa';

      var trilha = document.createElement('div');
      trilha.className = 'trilha';
      trilha.hidden = true;
      var carregada = false;

      trilhaBtn.addEventListener('click', function(){
        trilha.hidden = !trilha.hidden;
        trilhaBtn.setAttribute('aria-expanded', trilha.hidden ? 'false' : 'true');
        if(!trilha.hidden && !carregada){
          carregada = true;
          montarTrilha(traceId, trilha);
        }
      });

      painel.appendChild(trilhaBtn);
      painel.appendChild(trilha);
    }

    toggle.addEventListener('click', function(){
      painel.hidden = !painel.hidden;
      toggle.setAttribute('aria-expanded', painel.hidden ? 'false' : 'true');
      toggle.textContent = painel.hidden ? '[ VER BASE DA RESPOSTA ]' : '[ OCULTAR BASE DA RESPOSTA ]';
      scrollToBottom();
    });

    col.appendChild(toggle);
    col.appendChild(painel);
  }

  function addAssistantMessage(fullText, traceId){
    var row = document.createElement('div');
    row.className = 'msg assistant';
    row.innerHTML =
      '<div class="msg-col">' +
        '<div class="msg-rotulo">Resposta</div>' +
        '<div class="bubble"><span class="cursor"></span></div>' +
        '<div class="msg-meta"><button class="copy-btn" type="button">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>' +
          '<span>Copiar</span>' +
        '</button></div>' +
      '</div>';
    msgList.appendChild(row);

    var bubble = row.querySelector('.bubble');
    var col = row.querySelector('.msg-col');
    var meta = row.querySelector('.msg-meta');
    var copyBtn = row.querySelector('.copy-btn');
    copyBtn.addEventListener('click', function(){
      // Copia a resposta inteira (as quatro seções), não só o que está visível.
      var tmp = document.createElement('div');
      tmp.innerHTML = renderTexto(fullText);
      navigator.clipboard && navigator.clipboard.writeText(tmp.textContent).catch(function(){});
      copyBtn.querySelector('span').textContent = 'Copiado';
      setTimeout(function(){ copyBtn.querySelector('span').textContent = 'Copiar'; }, 1500);
    });

    // O corpo da bolha é o FATO; o resto vira callout e painel de base.
    // Fora do formato canônico (erro, aviso do front), a bolha é o texto todo.
    var secoes = separarSecoes(fullText);
    var corpo = secoes ? (secoes.fato || fullText) : fullText;

    // efeito de "digitação" revelando o texto progressivamente
    var words = corpo.split(' ');
    var i = 0;
    var acc = '';
    var interval = setInterval(function(){
      acc += (i === 0 ? '' : ' ') + words[i];
      bubble.innerHTML = renderTexto(acc) ;
      var cursor = document.createElement('span');
      cursor.className = 'cursor';
      bubble.appendChild(cursor);
      i++;
      scrollToBottom();
      if(i >= words.length){
        clearInterval(interval);
        bubble.innerHTML = renderTexto(acc);
        // O histórico guarda a resposta original e completa — é ela que volta
        // para o agente na próxima pergunta.
        history.push({role:'assistant', content: fullText});
        if(secoes){
          var extras = document.createElement('div');
          extras.className = 'msg-extras';
          col.insertBefore(extras, meta);
          montarPartesDaResposta(extras, secoes, traceId);
        }
        scrollToBottom();
      }
    }, 28);
  }

  /* ---------------- Lógica de resposta ---------------- */
  function requestReply(userText){
    var typingRow = addTypingIndicator();
    var delay = 650 + Math.random() * 700;

    var handleReply = function(replyText, traceId){
      typingRow.remove();
      addAssistantMessage(replyText, traceId);
    };

    if(MOCK_MODE){
      setTimeout(function(){
        handleReply(getMockReply(userText));
      }, delay);
    } else {
      sendToBackend(userText, history)
        .then(function(data){ handleReply(data.reply, data.trace_id); })
        .catch(function(err){
          handleReply('Não foi possível obter uma resposta do agente agora. Detalhe técnico: ' + (err && err.message ? err.message : err));
        });
    }
  }

  function getMockReply(userText){
    var t = userText.toLowerCase();
    if(t.indexOf('campanha') !== -1 || t.indexOf('marketplace') !== -1 && t.indexOf('desconto') !== -1 || t.indexOf('simul') !== -1){
      return 'Esta é uma resposta simulada para fins de demonstração do front-end — os números abaixo vêm do case, não de uma simulação em tempo real.\n\n' +
        '**Campanha de 30% no Marketplace — novembro:**\n' +
        '- Novembro opera com volume 87% acima da média do ano e concentra 19,4% de todo desconto acima de 25%\n' +
        '- O canal já paga frete em 100% dos pedidos, o que reduz a margem em 3,61 p.p. antes mesmo do desconto\n' +
        '- Um desconto de 30% leva parte do portfólio abaixo do piso de contribuição\n\n' +
        '**Recomendação:** limitar a 20% e resolver a assimetria de frete primeiro. Quando o agente real estiver conectado, essa simulação será recalculada a partir da base viva de custos e frete.';
    }
    if(t.indexOf('piso') !== -1 || t.indexOf('margem negativa') !== -1){
      return 'Esta é uma resposta simulada para fins de demonstração do front-end.\n\n' +
        '**Pedidos abaixo do piso de margem (dado do diagnóstico):**\n' +
        '- 427 pedidos com margem negativa hoje\n' +
        '- 82% desses pedidos são de valor abaixo de R$ 100\n' +
        '- Nenhuma concessão pode gerar margem negativa sem aprovação específica\n\n' +
        'No agente real, esta lista seria recalculada diariamente a partir do motor financeiro determinístico.';
    }
    if(t.indexOf('frete') !== -1){
      return 'Esta é uma resposta simulada para fins de demonstração do front-end.\n\n' +
        '**Assimetria de frete no Marketplace (dado do diagnóstico):**\n' +
        '- Marketplace paga frete em 100% dos pedidos, contra cerca de 20% nos demais canais\n' +
        '- Isso reduz a margem do canal em 3,61 p.p.\n' +
        '- Representa R$ 134 mil em frete que não seria pago em outro canal\n\n' +
        'É a variável com maior dispersão entre canais (coeficiente de variação de 98,3%) — por isso é o segundo pilar do MarginGuard, ao lado da governança de desconto.';
    }
    if(t.indexOf('teste') !== -1 || t.indexOf('moda') !== -1 || t.indexOf('elasticidade') !== -1 || t.indexOf('causal') !== -1){
      return 'Esta é uma resposta simulada para fins de demonstração do front-end.\n\n' +
        '**Teste de desconto em Moda (30% → 20%), dado ilustrativo do desenho experimental:**\n' +
        '- 1.340 pedidos por grupo, 4 semanas de duração\n' +
        '- Sem diferença estatisticamente significativa na conversão (p = 0,34)\n' +
        '- Margem por pedido R$ 61 maior no grupo com desconto de 20%, sem perda de volume detectável\n\n' +
        'Esta é a validação causal prevista para a Fase 4 do roadmap, depois que a governança de desconto e frete estiver estabilizada.';
    }
    if(t.indexOf('risco') !== -1){
      return 'Esta é uma resposta simulada para fins de demonstração do front-end.\n\n' +
        '**Riscos priorizados (do plano de guardrails):**\n' +
        '- Reduzir desconto ou frete e perder volume — mitigado com teste controlado\n' +
        '- Cálculo financeiro feito pela IA — mitigado com motor determinístico validado pelo Financeiro\n' +
        '- Confundir correlação com causalidade — tratado como estimativa até haver experimento\n\n' +
        'O agente real traria a lista completa de riscos e controles do case.';
    }
    return 'Recebi sua pergunta: "' + userText + '".\n\n' +
      'Esta é uma resposta simulada, só para você visualizar o comportamento da interface. Quando o backend estiver pronto, troque `MOCK_MODE` para `false` e implemente `sendToBackend()` para receber respostas reais do agente MarginGuard.';
  }

  /* =========================================================
     INTEGRAÇÃO COM O BACKEND
     -----------------------------------------------------------
     Implemente esta função para falar com o seu agente.
     Ela deve devolver uma Promise que resolve com um objeto
     { reply: string, trace_id: string } — o texto completo da
     resposta e o identificador do trace, usado pela trilha de
     auditoria em GET /api/trace/{trace_id}.

     Exemplo simples (resposta não-streamada):

     function sendToBackend(message, history) {
       return fetch('/api/chat', {
         method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         body: JSON.stringify({ message: message, history: history })
       })
       .then(function(res){
         if (!res.ok) throw new Error('HTTP ' + res.status);
         return res.json();
       })
       .then(function(data){ return data.reply; });
     }

     Exemplo com streaming (Server-Sent Events / chunks de texto):

     function sendToBackend(message, history) {
       return fetch('/api/chat/stream', {
         method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         body: JSON.stringify({ message: message, history: history })
       }).then(function(res){
         var reader = res.body.getReader();
         var decoder = new TextDecoder();
         var full = '';
         function read(){
           return reader.read().then(function(chunk){
             if (chunk.done) return full;
             full += decoder.decode(chunk.value, { stream: true });
             return read();
           });
         }
         return read();
       });
     }
  ========================================================= */
  function sendToBackend(message, history){
    // Investigação real (motor determinístico + ReAct) pode levar
    // 30-90s por pergunta — não é lentidão de rede, é latência do
    // gateway EloAgents por passo. Sem timeout artificial aqui.
    return fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: message, history: history })
    })
    .then(function(res){
      if (!res.ok){
        return res.json().catch(function(){ return {}; }).then(function(body){
          throw new Error(body.detail || ('HTTP ' + res.status));
        });
      }
      return res.json();
    })
    // O trace_id vem junto da resposta e é o que permite abrir a trilha de
    // auditoria depois, em GET /api/trace/{trace_id}.
    .then(function(data){ return { reply: data.reply, trace_id: data.trace_id }; });
  }

  autoResize();
})();
