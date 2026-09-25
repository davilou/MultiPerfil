# MultiPerfil — janela desktop (pywebview) no estilo Multilogin: plano

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development
> (recomendado) ou superpowers:executing-plans. Passos com checkbox (`- [ ]`).

**Objetivo:** app desktop aberto por atalho (sem terminal) com a lista de perfis no
layout do Multilogin, sobre a API que já existe.

**Arquitetura:** um processo só (`python -m multiperfil.app`): a API FastAPI sobe numa
thread (uvicorn em 127.0.0.1:8800) e serve também a página `multiperfil/ui/`; o
pywebview abre uma janela nela. A página não tem lógica de negócio: chama as mesmas rotas
dos scripts. Fechar a janela fecha os perfis abertos (limpo, pelo CDP) e encerra.

**Decisões do Davi (2026-09-25):** layout inspirado no Multilogin (print de referência);
pastas e tags ficam para depois; atalho na Área de Trabalho; a conta logada no portão 2
vira o perfil "Conta Eslováquia" (mesma seed, mesmo login).

**Check:** `.venv\Scripts\python -m pytest -q`

## Referência visual (print do Multilogin enviado pelo Davi)

- Barra lateral esquerda: "All profiles 4", "Running profiles 3", "Favorites"; abaixo,
  pastas (fora do escopo agora).
- Barra de ferramentas: botão azul "+ Create", ícones de ação que operam nos selecionados
  (iniciar, parar, editar, remover…), busca à direita.
- Tabela: checkbox, estrela (favorito), botão de estado (▶ azul = iniciar; ■ vermelho num
  quadrado claro = rodando/parar), Profile name, colunas de dados, Last start, Last edit,
  Created, menu ⋮ por linha. Rodapé com "Rows per page" e paginação.
- Visual claro: fundo cinza muito claro, cartões brancos com canto arredondado, azul de
  destaque (#1a5cff aprox.), tipografia sans 13–14 px, linhas finas.

---

### Tarefa 17: repositório — favorito, datas e último teste de proxy

**Arquivos:** `multiperfil/repositorio.py`, `tests/test_repositorio.py`

Colunas novas: `favorito INTEGER NOT NULL DEFAULT 0`, `editado_em TEXT`,
`ultimo_inicio TEXT`, `pais TEXT`, `ip_saida TEXT`. Existe um `dados/perfis.db` de teste
(tabela sem essas colunas), então há **migração**: ao abrir o banco, `PRAGMA
table_info(perfis)` e `ALTER TABLE perfis ADD COLUMN ...` para cada coluna que faltar.

- [ ] **Passo 1: Testes** (acrescentar em `tests/test_repositorio.py`)

```python
import sqlite3


def test_datas_e_favorito_no_ciclo(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    p = repo.obter("canal-a")
    assert p.favorito is False and p.ultimo_inicio is None
    assert p.criado_em and p.editado_em == p.criado_em
    repo.definir_favorito("canal-a", True)
    repo.registrar_inicio("canal-a", "2026-09-25T12:00:00+00:00")
    repo.registrar_teste("canal-a", ip="5.6.7.8", pais="SK")
    p = repo.obter("canal-a")
    assert (p.favorito, p.ultimo_inicio, p.ip_saida, p.pais) == (
        True, "2026-09-25T12:00:00+00:00", "5.6.7.8", "SK")


def test_atualizar_muda_editado_em(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    antes = repo.obter("canal-a").editado_em
    repo.atualizar("canal-a", nome="Novo", proxy=Proxy("http", "x", 1), idioma="pt-BR", notas="")
    assert repo.obter("canal-a").editado_em > antes


def test_migra_banco_antigo_sem_perder_perfil(tmp_path):
    caminho = tmp_path / "p.db"
    con = sqlite3.connect(caminho)
    con.execute("""CREATE TABLE perfis (id TEXT PRIMARY KEY, nome TEXT NOT NULL,
        sistema TEXT NOT NULL, proxy TEXT NOT NULL, seed INTEGER NOT NULL,
        idioma TEXT NOT NULL, notas TEXT NOT NULL, criado_em TEXT NOT NULL)""")
    con.execute("INSERT INTO perfis VALUES ('velho','Velho','windows','http://h:1',7,'pt-BR','',"
                "'2026-09-25T10:00:00+00:00')")
    con.commit()
    con.close()
    p = Repositorio(caminho).obter("velho")
    assert (p.seed, p.favorito, p.editado_em) == (7, False, "2026-09-25T10:00:00+00:00")


@pytest.mark.parametrize("metodo,args", [
    ("definir_favorito", (True,)), ("registrar_inicio", ("x",)),
])
def test_marcadores_em_perfil_inexistente(tmp_path, metodo, args):
    with pytest.raises(PerfilInexistente):
        getattr(Repositorio(tmp_path / "p.db"), metodo)("nada", *args)
```

- [ ] **Passo 2:** rodar — FALHA.

- [ ] **Passo 3: Implementação** em `multiperfil/repositorio.py`:

```python
COLUNAS_NOVAS: tuple[tuple[str, str], ...] = (
    ("favorito", "INTEGER NOT NULL DEFAULT 0"),
    ("editado_em", "TEXT"),
    ("ultimo_inicio", "TEXT"),
    ("pais", "TEXT"),
    ("ip_saida", "TEXT"),
)


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Perfil:
    id: str
    nome: str
    sistema: str
    proxy: Proxy
    seed: int
    idioma: str
    notas: str
    favorito: bool = False
    criado_em: str = ""
    editado_em: str = ""
    ultimo_inicio: str | None = None
    pais: str | None = None
    ip_saida: str | None = None


def _migrar(con: sqlite3.Connection) -> None:
    """Banco criado antes destas colunas ganha as que faltam; editado_em = criado_em."""
    existentes = {linha["name"] for linha in con.execute("PRAGMA table_info(perfis)")}
    for nome, tipo in COLUNAS_NOVAS:
        if nome not in existentes:
            con.execute(f"ALTER TABLE perfis ADD COLUMN {nome} {tipo}")
    con.execute("UPDATE perfis SET editado_em = criado_em WHERE editado_em IS NULL")
```

  - `ESQUEMA` inclui as 5 colunas (mesmos tipos); `__init__` executa `ESQUEMA` e depois
    `_migrar(con)`;
  - `_de_linha` preenche `favorito=bool(linha["favorito"])`, `criado_em`, `editado_em`,
    `ultimo_inicio`, `pais`, `ip_saida`;
  - `criar` passa a usar INSERT com **colunas nomeadas** (`INSERT INTO perfis (id, nome,
    sistema, proxy, seed, idioma, notas, criado_em, editado_em) VALUES (...)`), com
    `criado_em = editado_em = agora_iso()`;
  - `atualizar` também grava `editado_em = agora_iso()`;
  - métodos novos, todos com `PerfilInexistente` quando `rowcount == 0`:

```python
    def _alterar(self, perfil_id: str, sql: str, valores: tuple) -> None:
        with closing(self._conectar()) as con, con:
            cursor = con.execute(sql, (*valores, perfil_id))
        if cursor.rowcount == 0:
            raise PerfilInexistente(perfil_id)

    def definir_favorito(self, perfil_id: str, favorito: bool) -> None:
        self._alterar(perfil_id, "UPDATE perfis SET favorito = ? WHERE id = ?", (int(favorito),))

    def registrar_inicio(self, perfil_id: str, quando: str) -> None:
        self._alterar(perfil_id, "UPDATE perfis SET ultimo_inicio = ? WHERE id = ?", (quando,))

    def registrar_teste(self, perfil_id: str, *, ip: str, pais: str | None) -> None:
        self._alterar(perfil_id, "UPDATE perfis SET ip_saida = ?, pais = ? WHERE id = ?", (ip, pais))
```

  `atualizar` e `remover` passam a usar `_alterar` também (mesmo comportamento).

- [ ] **Passo 4:** `.venv\Scripts\python -m pytest -q` — verde.
- [ ] **Passo 5: Commit** — `feat: perfil com favorito, datas e ultimo teste de proxy`

---

### Tarefa 18: API — favorito, datas, senha preservada na edição, página

**Arquivos:** `multiperfil/api.py`, `tests/test_api.py`

- [ ] **Passo 1: Testes** (acrescentar em `tests/test_api.py`)

```python
def test_saida_tem_campos_da_tabela(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    p = cliente.get("/perfis").json()[0]
    for campo in ("favorito", "criado_em", "editado_em", "ultimo_inicio", "pais", "ip_saida", "cdp"):
        assert campo in p
    assert p["cdp"] is None


def test_abrir_registra_inicio_teste_e_cdp_na_lista(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    p = cliente.get("/perfis").json()[0]
    assert p["ultimo_inicio"] and (p["pais"], p["ip_saida"]) == ("SK", "5.6.7.8")
    assert p["cdp"] == "http://127.0.0.1:9/canal-a"


def test_testar_proxy_registra_pais(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/testar-proxy")
    assert cliente.get("/perfis").json()[0]["pais"] == "SK"


def test_favorito(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    assert cliente.put("/perfis/canal-a/favorito", json={"favorito": True}).json()["favorito"] is True
    assert cliente.put("/perfis/nada/favorito", json={"favorito": True}).status_code == 404


def test_editar_com_proxy_mascarado_mantem_senha(montar):
    cliente, _, deps = montar()
    cliente.post("/perfis", json=NOVO)
    mascarado = cliente.get("/perfis").json()[0]["proxy"]
    edicao = {"nome": "Novo", "proxy": mascarado, "idioma": "pt-BR", "notas": ""}
    assert cliente.patch("/perfis/canal-a", json=edicao).status_code == 200
    assert deps.repo.obter("canal-a").proxy.senha == "segredo"


def test_pagina_do_app(montar):
    cliente, _, _ = montar()
    r = cliente.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
```

- [ ] **Passo 2:** rodar — FALHA.

- [ ] **Passo 3: Implementação** em `multiperfil/api.py`:
  - `_saida` acrescenta `favorito`, `criado_em`, `editado_em`, `ultimo_inicio`, `pais`,
    `ip_saida` e `cdp` (= `registro.status(id).ws` quando `aberto`, senão `None`);
  - `abrir`: guardar o `ResultadoProxy`, chamar `deps.repo.registrar_teste(perfil_id,
    ip=r.ip, pais=r.pais)` e, depois de abrir, `deps.repo.registrar_inicio(perfil_id,
    agora_iso())`;
  - `testar-proxy`: também `registrar_teste`;
  - rota nova:

```python
class Favorito(BaseModel):
    favorito: bool

    @app.put("/perfis/{perfil_id}/favorito")
    def favoritar(perfil_id: str, corpo: Favorito) -> dict:
        deps.repo.definir_favorito(perfil_id, corpo.favorito)
        return _saida(deps.repo.obter(perfil_id), deps.registro)
```

  - `editar`: a tela nunca recebe a senha; se `edicao.proxy == descrever(atual.proxy)`,
    manter `atual.proxy` em vez de fazer parse:

```python
        atual = deps.repo.obter(perfil_id)
        proxy = atual.proxy if edicao.proxy == descrever(atual.proxy) else parse_proxy(edicao.proxy)
```

  - servir a página: `PASTA_UI = Path(__file__).parent / "ui"`; em `criar_app`, depois das
    rotas, `app.mount("/", StaticFiles(directory=PASTA_UI, html=True), name="ui")`
    (`from fastapi.staticfiles import StaticFiles`). Criar `multiperfil/ui/index.html`
    mínimo (`<!doctype html><title>MultiPerfil</title>`) para o teste; a tarefa 19 o
    substitui.

- [ ] **Passo 4:** `.venv\Scripts\python -m pytest -q` — verde.
- [ ] **Passo 5: Commit** — `feat: API com favorito, datas, senha preservada e pagina do app`

---

### Tarefa 19: a página (`multiperfil/ui/`)

**Arquivos:** `multiperfil/ui/index.html`, `multiperfil/ui/estilo.css`, `multiperfil/ui/app.js`

Implementador: carregar a skill `frontend-design` (ou `interface-design`) antes de
escrever. HTML/CSS/JS puros, sem framework, sem CDN (o app roda offline; a janela é
local). Cada arquivo abaixo de 400 linhas; funções JS abaixo de 50 linhas.

**Contrato com a API** (tudo em `127.0.0.1:8800`, mesma origem da página):
`GET /perfis` · `POST /perfis` {id, nome, proxy, sistema, idioma, notas} ·
`PATCH /perfis/{id}` {nome, proxy, idioma, notas} · `DELETE /perfis/{id}` ·
`PUT /perfis/{id}/favorito` {favorito} · `POST /perfis/{id}/abrir` → {cdp} ·
`POST /perfis/{id}/fechar` · `POST /perfis/{id}/testar-proxy` → {ip, pais, fuso,
latencia_ms}. Erros vêm como `{"detail": "..."}` (ou `detail.erro` no 409 de abrir).

**Layout (seguir a referência visual acima):**
1. Cabeçalho: logo/nome "MultiPerfil".
2. Barra lateral: "Todos os perfis N", "Rodando N", "Favoritos N" (filtros; contadores
   ao vivo).
3. Barra de ferramentas: botão azul **+ Criar**; ações sobre os selecionados: ▶ Abrir,
   ■ Fechar, Testar proxy, Remover (desabilitadas sem seleção); campo **Buscar** à
   direita (filtra por nome, notas, país).
4. Tabela: ☐ | ☆/★ | botão de estado | **Nome** | **Proxy** (bandeira/sigla do país +
   `ip_saida`, e abaixo o proxy mascarado em cinza) | **Notas** | **SO** (windows/macos/
   linux) | **Idioma** | **Último início** | **Última edição** | **Criado** | ⋮.
   - Botão de estado: `fechado` ▶ azul (abrir); `abrindo` spinner; `aberto` ■ vermelho
     em quadrado vermelho-claro (fechar); `erro` ⚠ vermelho com a mensagem no `title`.
   - Datas relativas em pt-BR ("há 5 segundos", "há 1 dia"); acima de 7 dias,
     `dd/mm/aaaa`. Data completa no `title`.
   - Menu ⋮: Copiar endereço CDP (só quando aberto), Editar, Testar proxy, Remover.
5. Rodapé: "Linhas por página" (10/25/50) e "1–4 de 4" com ‹ ›.

**Modais:** Criar/Editar com Nome (id gerado do nome: minúsculas, sem acento, espaços →
hífen; mostrado abaixo em cinza; só na criação), Proxy (uma linha; placeholder com os
formatos aceitos), Idioma (select: pt-BR, en-US, es-ES, de-DE, fr-FR, sk-SK + "outro"
livre), SO (select), Notas. Erro da API aparece no próprio modal. Na edição, o campo proxy
vem com o valor **mascarado** e uma dica "deixe como está para manter a senha".
Remover pede confirmação: "Apaga o perfil e o login salvo nele. Não dá para desfazer."

**Comportamento:**
- Atualiza a lista a cada 2 s (`GET /perfis`) sem perder seleção, busca, página nem
  menu aberto.
- Abrir/fechar: estado otimista `abrindo`, e erro vira aviso (toast) com o `detail`.
- Testar proxy: toast "SK · 196.44.x.x · 1,9 s" ou o erro.
- Copiar CDP: `navigator.clipboard.writeText` + toast "Endereço copiado".
- Nada de `innerHTML` com dado vindo da API (nome/notas são texto livre): montar com
  `textContent`/`createElement`.
- Estado vazio: "Nenhum perfil ainda" + botão Criar.

- [ ] **Passo 1:** escrever os três arquivos.
- [ ] **Passo 2: Verificação no navegador** (controlador): subir `python -m multiperfil`,
  abrir `http://127.0.0.1:8800/` no painel do navegador, e percorrer: criar perfil,
  editar (senha preservada), favoritar, filtrar, buscar, abrir/fechar, testar proxy,
  copiar CDP, remover. Screenshot comparado com a referência.
- [ ] **Passo 3: Commit** — `feat: pagina do app no estilo Multilogin`

---

### Tarefa 20: `app.py` — janela pywebview

**Arquivos:** `multiperfil/app.py`; `pyproject.toml` (+ `pywebview==6.2.1`)

- [ ] **Passo 1: Implementação**

```python
"""App desktop: API numa thread + janela pywebview. Fechar a janela fecha tudo.

Rodar: .venv\\Scripts\\pythonw -m multiperfil.app   (pythonw: sem janela de terminal)
"""

from __future__ import annotations

import logging
import os
import socket
import threading
from pathlib import Path

import uvicorn
import webview

from multiperfil.__main__ import NAVEGADOR_PADRAO, PORTA, montar_dependencias
from multiperfil.api import criar_app

RAIZ = Path(__file__).resolve().parent.parent
log = logging.getLogger("multiperfil.app")


def porta_ocupada(porta: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", porta)) == 0


def main() -> None:
    os.chdir(RAIZ)  # o atalho pode abrir com outra pasta de trabalho
    dados = RAIZ / "dados"
    logging.basicConfig(filename=dados / "app.log", level=logging.INFO,
                        format="%(asctime)s %(name)s %(message)s")
    if porta_ocupada(PORTA):
        webview.create_window("MultiPerfil", html="<p style='font:14px sans-serif;padding:24px'>"
                              "O MultiPerfil já está aberto (porta 8800 em uso).</p>",
                              width=420, height=160)
        webview.start()
        return
    deps = montar_dependencias(dados, (RAIZ / NAVEGADOR_PADRAO).resolve())
    servidor = uvicorn.Server(uvicorn.Config(criar_app(deps), host="127.0.0.1", port=PORTA,
                                             log_config=None))
    threading.Thread(target=servidor.run, daemon=True).start()
    janela = webview.create_window("MultiPerfil", f"http://127.0.0.1:{PORTA}/",
                                   width=1400, height=860, min_size=(1000, 600))
    janela.events.closed += lambda: _encerrar(deps, servidor)
    webview.start()


def _encerrar(deps, servidor: uvicorn.Server) -> None:
    for perfil in deps.repo.listar():
        if deps.registro.ocupado(perfil.id):
            deps.lancador.fechar(perfil.id)
            deps.registro.liberar(perfil.id)
    servidor.should_exit = True


if __name__ == "__main__":
    main()
```

Nota: a janela carrega a página antes do uvicorn terminar de subir? `uvicorn` sobe em
~0,3 s e o WebView2 leva mais que isso para iniciar; se na verificação aparecer página
de erro, esperar a porta com `rede.esperar_porta`-equivalente antes de `create_window`
(medir antes de mudar).

- [ ] **Passo 2:** instalar `pywebview==6.2.1` no venv e acrescentar ao `pyproject.toml`
  com o comentário `# janela desktop (usa o WebView2 do Windows)`.
- [ ] **Passo 3: Verificação** (controlador): `pythonw -m multiperfil.app` abre a janela
  com a lista; abrir um perfil; fechar a janela ⇒ o Chromium do perfil fecha e o processo
  sai; segunda instância mostra o aviso.
- [ ] **Passo 4: Commit** — `feat: janela desktop do MultiPerfil`

---

### Tarefa 21: atalho na Área de Trabalho e importação da "Conta Eslováquia"

**Arquivos:** `ferramentas/criar_atalho.py`, `ferramentas/importar_spike.py`

- [ ] **Passo 1: `ferramentas/criar_atalho.py`** — cria `MultiPerfil.lnk` na Área de
  Trabalho do usuário (pasta real via `[Environment]::GetFolderPath('Desktop')`, que
  cobre Desktop redirecionado pelo OneDrive) apontando para
  `<raiz>\.venv\Scripts\pythonw.exe` com argumentos `-m multiperfil.app`, pasta de
  trabalho `<raiz>`. Implementar chamando PowerShell com `WScript.Shell`
  (`CreateShortcut`), argv em lista (sem shell), caminhos passados por variável de
  ambiente para o script PowerShell não precisar de aspas escapadas.
- [ ] **Passo 2: `ferramentas/importar_spike.py`** — cria o perfil `conta-eslovaquia`
  ("Conta Eslováquia") direto pelo `Repositorio`, com a **seed de
  `dados/spike-chromium/seed.txt`** (o fingerprint que o Google já viu), proxy de
  `dados/proxy.txt`, idioma `pt-BR`, SO `windows`; copia `dados/spike-chromium/perfil`
  para `dados/perfis/conta-eslovaquia` (falha se o destino existir). Não apaga a origem.
- [ ] **Passo 3: Verificação** (controlador): rodar os dois; pelo app, abrir "Conta
  Eslováquia" ⇒ Studio abre já logado. Só então apagar `dados/spike-chromium`,
  `dados/spike` (sessão Camoufox obsoleta) e os `.log` dos spikes, e remover o perfil
  `teste` pelo app.
- [ ] **Passo 5: Commit** — `feat: atalho do app e importacao da conta do portao 2`
