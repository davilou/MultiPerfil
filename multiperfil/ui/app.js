"use strict";
// Estado da página, filtros, paginação e ações. Atualiza a lista a cada 2 s.

const estado = {
  perfis: [],
  filtro: "todos",
  busca: "",
  pagina: 0,
  porPagina: 10,
  selecionados: new Set(),
  otimista: new Map(), // id → "abrindo" enquanto abrir/fechar está em curso
  menuAberto: null,
  fecharMenu: null,
  carregando: false,
};

const $ = (id) => document.getElementById(id);
const AVISO_REMOVER = "Apaga o perfil e o login salvo nele. Não dá para desfazer.";

function perfisVistos() {
  return estado.perfis.map((p) => (estado.otimista.has(p.id) ? { ...p, status: estado.otimista.get(p.id) } : p));
}

function passaFiltro(perfil) {
  if (estado.filtro === "rodando") return perfil.status === "aberto" || perfil.status === "abrindo";
  if (estado.filtro === "favoritos") return perfil.favorito;
  return true;
}

function passaBusca(perfil) {
  const termo = estado.busca.trim().toLowerCase();
  if (!termo) return true;
  return [perfil.nome, perfil.notas, perfil.pais, perfil.id]
    .some((texto) => (texto || "").toLowerCase().includes(termo));
}

function atualizarContadores(perfis) {
  $("n-todos").textContent = perfis.length;
  $("n-rodando").textContent = perfis.filter((p) => p.status === "aberto" || p.status === "abrindo").length;
  $("n-favoritos").textContent = perfis.filter((p) => p.favorito).length;
}

function atualizarFerramentas(pagina) {
  const n = estado.selecionados.size;
  for (const id of ["acao-abrir", "acao-fechar", "acao-testar", "acao-remover"]) $(id).disabled = n === 0;
  $("n-selecionados").textContent = n ? `${n} selecionado${n > 1 ? "s" : ""}` : "";
  const todos = $("check-todos");
  const marcados = pagina.filter((p) => estado.selecionados.has(p.id)).length;
  todos.checked = pagina.length > 0 && marcados === pagina.length;
  todos.indeterminate = marcados > 0 && marcados < pagina.length;
}

function atualizarRodape(total) {
  const inicio = estado.pagina * estado.porPagina;
  const fim = Math.min(total, inicio + estado.porPagina);
  $("faixa").textContent = `${total ? inicio + 1 : 0}–${fim} de ${total}`;
  $("pag-ant").disabled = estado.pagina === 0;
  $("pag-prox").disabled = fim >= total;
}

function desenhar() {
  const todos = perfisVistos();
  const visiveis = todos.filter((p) => passaFiltro(p) && passaBusca(p));
  const ultimaPagina = Math.max(0, Math.ceil(visiveis.length / estado.porPagina) - 1);
  estado.pagina = Math.min(estado.pagina, ultimaPagina);
  const inicio = estado.pagina * estado.porPagina;
  const pagina = visiveis.slice(inicio, inicio + estado.porPagina);
  atualizarContadores(todos);
  desenharTabela(pagina, {
    selecionados: estado.selecionados, menuAberto: estado.menuAberto,
    acoes, totalGeral: todos.length,
  });
  atualizarFerramentas(pagina);
  atualizarRodape(visiveis.length);
}

async function carregar() {
  if (estado.carregando) return;
  estado.carregando = true;
  try {
    estado.perfis = await api.listar();
    const existentes = new Set(estado.perfis.map((p) => p.id));
    for (const id of estado.selecionados) if (!existentes.has(id)) estado.selecionados.delete(id);
    desenhar();
  } catch (erro) {
    toast(`Não foi possível atualizar a lista: ${erro.message}`, true);
  } finally {
    estado.carregando = false;
  }
}

function perfilPorId(id) {
  return estado.perfis.find((p) => p.id === id);
}

/** Roda `tarefa(perfil)` em cada id, mostra erro por perfil e recarrega no fim. */
async function emCada(ids, tarefa) {
  await Promise.all(ids.map(async (id) => {
    const perfil = perfilPorId(id);
    if (!perfil) return;
    try {
      await tarefa(perfil);
    } catch (erro) {
      toast(`${perfil.nome}: ${erro.message}`, true);
    }
  }));
  await carregar();
}

async function comOtimismo(perfil, chamada) {
  estado.otimista.set(perfil.id, "abrindo");
  desenhar();
  try {
    await chamada(perfil.id);
  } finally {
    estado.otimista.delete(perfil.id);
  }
}

const abrirVarios = (ids) => emCada(ids, (p) => (p.status === "aberto" ? null : comOtimismo(p, api.abrir)));
const fecharVarios = (ids) => emCada(ids, (p) => (p.status === "aberto" ? comOtimismo(p, api.fechar) : null));

function textoTeste(r) {
  const segundos = (r.latencia_ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 });
  return `${r.pais || "??"} · ${r.ip} · ${segundos} s`;
}

const testarVarios = (ids) => emCada(ids, async (p) => {
  toast(`${p.nome}: testando proxy…`);
  toast(`${p.nome}: ${textoTeste(await api.testarProxy(p.id))}`);
});

async function removerVarios(ids) {
  const titulo = ids.length === 1
    ? `Remover ${(perfilPorId(ids[0]) || { nome: ids[0] }).nome}?`
    : `Remover ${ids.length} perfis?`;
  if (!(await confirmar(titulo, AVISO_REMOVER, "Remover"))) return;
  await emCada(ids, (p) => api.remover(p.id));
  ids.forEach((id) => estado.selecionados.delete(id));
  desenhar();
}

function itensMenu(perfil) {
  const itens = [];
  if (perfil.status === "aberto" && perfil.cdp) {
    itens.push({ rotulo: "Copiar endereço CDP", icone: "copiar", acao: () => copiarTexto(perfil.cdp, "Endereço copiado") }, "-");
  }
  itens.push(
    { rotulo: "Editar", icone: "lapis", acao: () => acoes.editar(perfil) },
    { rotulo: "Testar proxy", icone: "radar", acao: () => testarVarios([perfil.id]) },
    "-",
    { rotulo: "Remover", icone: "lixo", perigo: true, acao: () => removerVarios([perfil.id]) },
  );
  return itens;
}

const acoes = {
  alternarSelecao(id) {
    if (!estado.selecionados.delete(id)) estado.selecionados.add(id);
    desenhar();
  },
  favoritar(perfil) {
    emCada([perfil.id], (p) => api.favoritar(p.id, !p.favorito));
  },
  alternarEstado(perfil) {
    if (perfil.status === "aberto") fecharVarios([perfil.id]);
    else abrirVarios([perfil.id]);
  },
  abrirMenu(id, ancora) {
    const mesmo = estado.menuAberto === id;
    if (estado.fecharMenu) estado.fecharMenu();
    const perfil = perfisVistos().find((p) => p.id === id);
    if (mesmo || !perfil) return;
    estado.menuAberto = id;
    estado.fecharMenu = mostrarMenu(ancora, itensMenu(perfil), () => {
      estado.menuAberto = null;
      estado.fecharMenu = null;
      desenhar();
    });
    desenhar();
  },
  criar() {
    modalPerfil(null, async (dados) => {
      const novo = await api.criar(dados);
      toast(`Perfil ${novo.nome} criado`);
      await carregar();
    });
  },
  editar(perfil) {
    modalPerfil(perfil, async (dados) => {
      await api.editar(perfil.id, dados);
      toast("Alterações salvas");
      await carregar();
    });
  },
};

function ligarFiltros() {
  document.querySelectorAll(".filtro").forEach((botao) => {
    botao.addEventListener("click", () => {
      document.querySelectorAll(".filtro").forEach((b) => b.classList.toggle("ativo", b === botao));
      estado.filtro = botao.dataset.filtro;
      estado.pagina = 0;
      desenhar();
    });
  });
  $("busca").addEventListener("input", (evento) => {
    estado.busca = evento.target.value;
    estado.pagina = 0;
    desenhar();
  });
}

function idsDaPagina() {
  return [...document.querySelectorAll("#corpo tr")].map((linha) => linha.dataset.id);
}

function ligarFerramentas() {
  const selecionados = () => [...estado.selecionados];
  $("btn-criar").addEventListener("click", acoes.criar);
  $("acao-abrir").addEventListener("click", () => abrirVarios(selecionados()));
  $("acao-fechar").addEventListener("click", () => fecharVarios(selecionados()));
  $("acao-testar").addEventListener("click", () => testarVarios(selecionados()));
  $("acao-remover").addEventListener("click", () => removerVarios(selecionados()));
  $("check-todos").addEventListener("change", (evento) => {
    idsDaPagina().forEach((id) => (evento.target.checked
      ? estado.selecionados.add(id) : estado.selecionados.delete(id)));
    desenhar();
  });
}

function ligarPaginacao() {
  $("por-pagina").addEventListener("change", (evento) => {
    estado.porPagina = Number(evento.target.value);
    estado.pagina = 0;
    desenhar();
  });
  $("pag-ant").addEventListener("click", () => { estado.pagina -= 1; desenhar(); });
  $("pag-prox").addEventListener("click", () => { estado.pagina += 1; desenhar(); });
}

function iniciar() {
  preencherIcones(document);
  ligarFiltros();
  ligarFerramentas();
  ligarPaginacao();
  carregar();
  setInterval(carregar, 2000);
}

iniciar();
