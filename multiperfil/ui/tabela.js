"use strict";
// Desenho das linhas da tabela. Recebe perfis prontos e callbacks; não guarda estado.

function celulaData(iso) {
  const td = el("td", { class: "data", texto: dataRelativa(iso) });
  if (iso) td.title = dataCompleta(iso);
  return td;
}

function botaoEstado(perfil, acoes) {
  const status = perfil.status;
  if (status === "abrindo") {
    return el("button", { class: "estado abrindo", title: "Abrindo…", disabled: true },
      el("span", { class: "giro" }));
  }
  const config = {
    fechado: ["", "play", "Abrir"],
    aberto: ["aberto", "parar", "Fechar"],
    erro: ["erro", "alerta", perfil.erro || "Erro"],
  }[status] || ["", "play", "Abrir"];
  const [classe, nomeIcone, titulo] = config;
  return el("button", {
    class: `estado ${classe}`.trim(),
    title: titulo,
    "aria-label": status === "aberto" ? "Fechar perfil" : "Abrir perfil",
    onclick: () => acoes.alternarEstado(perfil),
  }, icone(nomeIcone));
}

function celulaProxy(perfil) {
  const sigla = perfil.pais
    ? el("span", { class: "pais", texto: perfil.pais.toUpperCase() })
    : el("span", { class: "pais sem", texto: "??", title: "Proxy ainda não testado" });
  const topo = el("div", { class: "proxy-topo" }, [
    sigla,
    el("span", { class: "ip", texto: perfil.ip_saida || "sem teste" }),
  ]);
  const url = el("div", { class: "proxy-url", texto: perfil.proxy, title: perfil.proxy });
  return el("td", {}, [topo, url]);
}

function celulasIniciais(perfil, ctx) {
  const marcado = ctx.selecionados.has(perfil.id);
  const check = el("input", {
    type: "checkbox",
    "aria-label": `Selecionar ${perfil.nome}`,
    onchange: () => ctx.acoes.alternarSelecao(perfil.id),
  });
  check.checked = marcado;
  const fav = el("button", {
    class: perfil.favorito ? "fav on" : "fav",
    title: perfil.favorito ? "Tirar dos favoritos" : "Favoritar",
    onclick: () => ctx.acoes.favoritar(perfil),
  }, icone("estrela"));
  return [
    el("td", { class: "c-check" }, check),
    el("td", { class: "c-fav" }, fav),
    el("td", { class: "c-estado" }, botaoEstado(perfil, ctx.acoes)),
  ];
}

function linhaPerfil(perfil, ctx) {
  const nome = el("td", { class: "nome" }, [perfil.nome, el("small", { texto: perfil.id })]);
  const notas = el("td", { class: "notas", texto: perfil.notas || "", title: perfil.notas || null });
  const menu = el("button", {
    class: ctx.menuAberto === perfil.id ? "menu-btn ativo" : "menu-btn",
    title: "Mais ações",
    onclick: (evento) => ctx.acoes.abrirMenu(perfil.id, evento.currentTarget),
  }, icone("pontos"));
  const linha = el("tr", { class: ctx.selecionados.has(perfil.id) ? "sel" : null }, [
    ...celulasIniciais(perfil, ctx),
    nome,
    celulaProxy(perfil),
    notas,
    el("td", { class: "so", texto: perfil.sistema }),
    el("td", { texto: perfil.idioma }),
    celulaData(perfil.ultimo_inicio),
    celulaData(perfil.editado_em),
    celulaData(perfil.criado_em),
    el("td", { class: "c-menu" }, menu),
  ]);
  linha.dataset.id = perfil.id;
  return linha;
}

function desenharVazio(caixa, semNenhum, aoCriar) {
  caixa.replaceChildren();
  if (semNenhum) {
    caixa.append(
      el("strong", { texto: "Nenhum perfil ainda" }),
      el("span", { texto: "Crie o primeiro para abrir um navegador com proxy e login próprios." }),
      el("button", { class: "btn-primario", onclick: aoCriar }, [icone("mais"), "Criar"]),
    );
  } else {
    caixa.append(el("strong", { texto: "Nada encontrado" }),
      el("span", { texto: "Nenhum perfil bate com o filtro ou a busca." }));
  }
}

/** Redesenha o corpo; `ctx` = {selecionados, menuAberto, acoes, totalGeral}. */
function desenharTabela(perfis, ctx) {
  const corpo = document.getElementById("corpo");
  const vazio = document.getElementById("vazio");
  corpo.replaceChildren(...perfis.map((perfil) => linhaPerfil(perfil, ctx)));
  vazio.hidden = perfis.length > 0;
  if (!perfis.length) desenharVazio(vazio, ctx.totalGeral === 0, ctx.acoes.criar);
}
