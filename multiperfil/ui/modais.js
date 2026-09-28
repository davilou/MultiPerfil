"use strict";
// Sobreposições: modal de criar/editar, confirmação e menu ⋮ flutuante.

const IDIOMAS = ["pt-BR", "en-US", "es-ES", "de-DE", "fr-FR", "sk-SK"];
const SISTEMAS = ["windows", "macos", "linux"];
const DICA_PROXY = "http://usuario:senha@host:porta · host:porta:usuario:senha · socks5://host:porta";

function mostrarModal(conteudo, aoFechar = () => {}) {
  const veu = el("div", { class: "veu" }, el("div", { class: "modal", role: "dialog" }, conteudo));
  const fechar = () => {
    if (!veu.isConnected) return;
    veu.remove();
    document.removeEventListener("keydown", aoTeclar);
    aoFechar();
  };
  function aoTeclar(evento) {
    if (evento.key === "Escape") fechar();
  }
  veu.addEventListener("mousedown", (evento) => {
    if (evento.target === veu) fechar();
  });
  document.addEventListener("keydown", aoTeclar);
  document.body.append(veu);
  return fechar;
}

function campo(rotulo, controle, dica) {
  return el("label", { class: "campo" }, [el("span", { texto: rotulo }), controle,
    dica ? el("small", { texto: dica }) : null]);
}

function seletor(opcoes, valor) {
  const select = el("select", {}, opcoes.map((op) => el("option", { value: op, texto: op })));
  select.value = valor;
  return select;
}

/** Select de idioma com "outro" que libera um campo livre. */
function campoIdioma(valor) {
  const conhecido = IDIOMAS.includes(valor);
  const select = el("select", {}, [...IDIOMAS, "outro"].map((op) => el("option", { value: op, texto: op })));
  select.value = conhecido ? valor : "outro";
  const livre = el("input", { placeholder: "ex.: it-IT", value: conhecido ? "" : valor });
  livre.hidden = conhecido;
  select.addEventListener("change", () => {
    livre.hidden = select.value !== "outro";
    if (!livre.hidden) livre.focus();
  });
  const bloco = el("div", { class: "campo-idioma" }, [select, livre]);
  livre.style.marginTop = "6px";
  return { bloco, ler: () => (select.value === "outro" ? livre.value.trim() : select.value) };
}

function camposPerfil(perfil) {
  const nome = el("input", { value: perfil ? perfil.nome : "", placeholder: "Ex.: Conta Eslováquia", maxlength: 80 });
  const idPrevia = el("small", { texto: perfil ? `id: ${perfil.id}` : "id: —" });
  if (!perfil) {
    nome.addEventListener("input", () => {
      idPrevia.textContent = `id: ${idDoNome(nome.value) || "—"}`;
    });
  }
  const proxy = el("input", { value: perfil ? perfil.proxy : "", placeholder: DICA_PROXY, spellcheck: "false" });
  const sistema = seletor(SISTEMAS, perfil ? perfil.sistema : "windows");
  sistema.disabled = Boolean(perfil);
  const idioma = campoIdioma(perfil ? perfil.idioma : "pt-BR");
  const notas = el("textarea", { placeholder: "Opcional" });
  notas.value = perfil ? perfil.notas : "";
  return { nome, idPrevia, proxy, sistema, idioma, notas };
}

function mostrarChecagem(alvo, tipo, texto) {
  alvo.className = `checagem ${tipo}`;
  alvo.textContent = texto;
}

/** Campo de proxy com "Checar proxy": testa sem salvar e mostra o resultado embaixo. */
function campoProxy(c, perfil) {
  const resultado = el("small", { class: "checagem" });
  const botao = el("button", { class: "btn-sec btn-checar", type: "button", texto: "Checar proxy" });
  botao.addEventListener("click", async () => {
    const texto = c.proxy.value.trim();
    if (!texto) return mostrarChecagem(resultado, "erro", "Cole o proxy antes de checar.");
    botao.disabled = true;
    mostrarChecagem(resultado, "", "Checando o proxy…");
    try {
      const r = await api.checarProxy(texto, perfil ? perfil.id : null);
      mostrarChecagem(resultado, "ok", `Proxy funcionando: ${textoTeste(r)} · ${r.fuso}`);
    } catch (falha) {
      mostrarChecagem(resultado, "erro", falha.message);
    } finally {
      botao.disabled = false;
    }
  });
  c.proxy.addEventListener("input", () => mostrarChecagem(resultado, "", ""));
  return el("div", {}, [el("div", { class: "linha-proxy" }, [c.proxy, botao]), resultado]);
}

function lerCampos(c, perfil) {
  const dados = { nome: c.nome.value.trim(), proxy: c.proxy.value.trim(),
    idioma: c.idioma.ler(), notas: c.notas.value.trim() };
  if (!perfil) {
    dados.id = idDoNome(dados.nome);
    dados.sistema = c.sistema.value;
  }
  return dados;
}

/** Criar (perfil = null) ou editar. `aoSalvar(dados)` lança Error com a mensagem da API. */
function modalPerfil(perfil, aoSalvar) {
  const c = camposPerfil(perfil);
  const erro = el("div", { class: "erro-modal" });
  erro.hidden = true;
  const salvar = el("button", { class: "btn-primario", type: "submit", texto: perfil ? "Salvar" : "Criar perfil" });
  const form = el("form", {}, [
    el("h2", { texto: perfil ? `Editar ${perfil.nome}` : "Novo perfil" }),
    campo("Nome", el("div", {}, [c.nome, c.idPrevia])),
    campo("Proxy", campoProxy(c, perfil), perfil ? "Deixe como está para manter a senha." : null),
    el("div", { class: "linha-2" }, [campo("Idioma", c.idioma.bloco), campo("SO", c.sistema)]),
    campo("Notas", c.notas),
    erro,
    el("div", { class: "modal-acoes" }, [
      el("button", { class: "btn-sec", type: "button", texto: "Cancelar", onclick: () => fechar() }),
      salvar,
    ]),
  ]);
  const fechar = mostrarModal(form);
  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    salvar.disabled = true;
    try {
      await aoSalvar(lerCampos(c, perfil));
      fechar();
    } catch (falha) {
      erro.textContent = falha.message;
      erro.hidden = false;
      salvar.disabled = false;
    }
  });
  c.nome.focus();
}

/** Resolve true se confirmado; Esc, clique fora ou Cancelar resolvem false. */
function confirmar(titulo, texto, rotulo) {
  return new Promise((resolver) => {
    let confirmado = false;
    const ok = el("button", { class: "btn-perigo", texto: rotulo,
      onclick: () => { confirmado = true; fechar(); } });
    const fechar = mostrarModal([
      el("h2", { texto: titulo }),
      el("p", { texto: texto }),
      el("div", { class: "modal-acoes" }, [
        el("button", { class: "btn-sec", texto: "Cancelar", onclick: () => fechar() }), ok,
      ]),
    ], () => resolver(confirmado));
    ok.focus();
  });
}

/** Menu ⋮ fora da tabela, para sobreviver ao redesenho de 2 s. */
function mostrarMenu(ancora, itens, aoFechar) {
  const menu = el("div", { class: "menu", role: "menu" }, itens.map((item) => (item === "-"
    ? el("hr")
    : el("button", { class: item.perigo ? "perigo" : null, onclick: () => { fechar(); item.acao(); } },
      [icone(item.icone), item.rotulo]))));
  document.body.append(menu);
  const caixa = ancora.getBoundingClientRect();
  const altura = menu.offsetHeight;
  const topo = caixa.bottom + altura + 8 > innerHeight ? caixa.top - altura - 4 : caixa.bottom + 4;
  menu.style.top = `${Math.max(8, topo)}px`;
  menu.style.left = `${Math.max(8, caixa.right - menu.offsetWidth)}px`;
  function fora(evento) {
    if (!menu.contains(evento.target) && !evento.target.closest(".menu-btn")) fechar();
  }
  function fechar() {
    menu.remove();
    document.removeEventListener("mousedown", fora);
    aoFechar();
  }
  setTimeout(() => document.addEventListener("mousedown", fora));
  return fechar;
}
