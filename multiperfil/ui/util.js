"use strict";
// Utilitários sem estado: ícones, DOM, datas, toast. Nenhum dado da API passa por innerHTML.

const ICONES = {
  grade: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  pulso: '<path d="M3 12h4l2.5-6 5 12 2.5-6h4"/>',
  estrela: '<path d="m12 3.5 2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z"/>',
  mais: '<path d="M12 5v14M5 12h14"/>',
  play: '<path d="M8 5.5v13a.8.8 0 0 0 1.2.7l10.4-6.5a.8.8 0 0 0 0-1.4L9.2 4.8A.8.8 0 0 0 8 5.5z"/>',
  parar: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  radar: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><path d="M12 12 18 6"/>',
  lixo: '<path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13M10 11v5M14 11v5"/>',
  lupa: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  esq: '<path d="m14.5 6-6 6 6 6"/>',
  dir: '<path d="m9.5 6 6 6-6 6"/>',
  pontos: '<circle cx="12" cy="5.5" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="12" cy="18.5" r="1.3"/>',
  alerta: '<path d="M12 4 2.8 19.5h18.4z"/><path d="M12 10v4.5M12 17.2v.1"/>',
  copiar: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8"/>',
  lapis: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
};

/** Ícone SVG a partir de constante interna (nunca de dado externo). */
function icone(nome) {
  const span = document.createElement("span");
  span.className = "ico";
  span.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONES[nome]}</svg>`;
  return span;
}

/** Troca os `<span data-ico>` estáticos do HTML pelo SVG correspondente. */
function preencherIcones(raiz) {
  raiz.querySelectorAll("[data-ico]").forEach((alvo) => {
    alvo.replaceWith(icone(alvo.dataset.ico));
  });
}

/** createElement com atributos e filhos; strings viram nós de texto. */
function el(tag, atributos = {}, filhos = []) {
  const no = document.createElement(tag);
  for (const [chave, valor] of Object.entries(atributos)) {
    if (valor === undefined || valor === null || valor === false) continue;
    if (chave === "class") no.className = valor;
    else if (chave === "texto") no.textContent = valor;
    else if (chave.startsWith("on")) no.addEventListener(chave.slice(2), valor);
    else if (valor === true) no.setAttribute(chave, "");
    else no.setAttribute(chave, String(valor));
  }
  for (const filho of [].concat(filhos)) {
    if (filho === null || filho === undefined || filho === false) continue;
    no.append(typeof filho === "string" ? document.createTextNode(filho) : filho);
  }
  return no;
}

const UNIDADES = [
  [60, "segundo", "segundos"],
  [60, "minuto", "minutos"],
  [24, "hora", "horas"],
  [7, "dia", "dias"],
];

function dataCompleta(iso) {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" });
}

/** "há 5 segundos", "há 1 dia"; a partir de 7 dias, dd/mm/aaaa. */
function dataRelativa(iso) {
  if (!iso) return "—";
  const data = new Date(iso);
  let valor = Math.max(0, Math.floor((Date.now() - data.getTime()) / 1000));
  for (const [limite, singular, plural] of UNIDADES) {
    if (valor < limite) return `há ${valor} ${valor === 1 ? singular : plural}`;
    valor = Math.floor(valor / limite);
  }
  return data.toLocaleDateString("pt-BR");
}

/** Nome livre → id aceito pela API: minúsculas, sem acento, espaços viram hífen. */
function idDoNome(nome) {
  return nome
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)
    .replace(/-+$/, "");
}

function toast(texto, erro = false, duracaoMs = erro ? 6000 : 3200) {
  const caixa = el("div", { class: erro ? "toast erro" : "toast", texto });
  document.getElementById("toasts").append(caixa);
  setTimeout(() => {
    caixa.classList.add("sai");
    setTimeout(() => caixa.remove(), 300);
  }, duracaoMs);
}

/** Cópia síncrona pelo `execCommand`; precisa rodar dentro do clique do usuário. */
function copiarPorSelecao(texto) {
  const area = el("textarea", { readonly: true, style: "position:fixed;left:-9999px;top:0" });
  area.value = texto;
  document.body.append(area);
  area.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    area.remove();
  }
}

/**
 * Copia para a área de transferência. O WebView2 do pywebview pode negar
 * `navigator.clipboard`, então tenta primeiro o `execCommand` (síncrono, ainda
 * dentro do gesto do usuário) e só depois a API assíncrona. Se as duas falham,
 * mostra o texto num aviso para cópia manual.
 */
async function copiarTexto(texto, rotulo) {
  if (copiarPorSelecao(texto)) {
    toast(rotulo);
    return;
  }
  try {
    await navigator.clipboard.writeText(texto);
    toast(rotulo);
  } catch {
    toast(`Copie o endereço: ${texto}`, false, 15000);
  }
}
