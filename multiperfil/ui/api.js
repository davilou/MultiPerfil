"use strict";
// Cliente da API local (mesma origem). Erros viram Error com a mensagem do `detail`.

function mensagemDoDetalhe(detalhe, status) {
  if (typeof detalhe === "string") return detalhe;
  if (Array.isArray(detalhe)) {
    return detalhe.map((item) => item.msg || JSON.stringify(item)).join("; ");
  }
  if (detalhe && typeof detalhe === "object" && detalhe.erro) return detalhe.erro;
  return `erro ${status}`;
}

async function pedir(metodo, caminho, corpo) {
  const opcoes = { method: metodo, headers: {} };
  if (corpo !== undefined) {
    opcoes.headers["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify(corpo);
  }
  let resposta;
  try {
    resposta = await fetch(caminho, opcoes);
  } catch {
    throw new Error("sem conexão com o servidor local");
  }
  if (resposta.status === 204) return null;
  const dados = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    throw new Error(mensagemDoDetalhe(dados && dados.detail, resposta.status));
  }
  return dados;
}

const caminhoPerfil = (id) => `/perfis/${encodeURIComponent(id)}`;

const api = {
  listar: () => pedir("GET", "/perfis"),
  criar: (dados) => pedir("POST", "/perfis", dados),
  editar: (id, dados) => pedir("PATCH", caminhoPerfil(id), dados),
  remover: (id) => pedir("DELETE", caminhoPerfil(id)),
  favoritar: (id, favorito) => pedir("PUT", `${caminhoPerfil(id)}/favorito`, { favorito }),
  abrir: (id) => pedir("POST", `${caminhoPerfil(id)}/abrir`),
  fechar: (id) => pedir("POST", `${caminhoPerfil(id)}/fechar`),
  testarProxy: (id) => pedir("POST", `${caminhoPerfil(id)}/testar-proxy`),
  checarProxy: (proxy, perfilId) => pedir("POST", "/proxy/testar", { proxy, perfil_id: perfilId }),
};
