# MultiPerfil v2 — troca para fingerprint-chromium: plano de implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development
> (recomendado) ou superpowers:executing-plans para executar tarefa por tarefa. Passos
> com checkbox (`- [ ]`).

**Objetivo:** o sidecar abre um fingerprint-chromium por perfil (pasta persistente, seed
fixa, fuso do proxy, proxy com senha via repassador local) e devolve o endereço CDP para
scripts Playwright externos (`connect_over_cdp`), como o Multilogin.

**Por que v2:** o portão 1 mostrou que o modo servidor do Camoufox trava de forma
intermitente e não aceita perfil persistente (issues abertas #253, #553). O portão 2
aprovou o fingerprint-chromium: login persiste, fingerprint estável por seed e diferente
entre seeds, ciclo de 9 s (Camoufox: 47–67 s), fechamento limpo. Resultados medidos no
fim de `2026-09-25-multiperfil-sidecar.md`.

**Substitui** as tarefas 1, 5, 6, 7, 8 e 9 do plano do sidecar. Continuam valendo, com os
ajustes abaixo: `proxy.py`, `estado.py`, `repositorio.py` e seus testes.

**Stack:** Python 3.13, fingerprint-chromium 148.0.7778.215 (em `navegador/`, fora do
git), Playwright 1.62 (sync + async), pproxy 2.7.9, FastAPI, uvicorn, httpx, pytest.
`camoufox[geoip]` continua **só** por `camoufox.ip.public_ip` e
`camoufox.geolocation.get_geolocation` (IP de saída → país e fuso).

**Check:** `.venv\Scripts\python -m pytest -q`

## Fatos verificados que sustentam o desenho (2026-09-25)

1. Flags do fingerprint-chromium (README do projeto): `--fingerprint=<seed 32 bits>`,
   `--fingerprint-platform=windows|linux|macos`, `--timezone`, `--lang`, `--accept-lang`,
   `--proxy-server` (**sem suporte a senha**), `--user-data-dir`. Medido: mesma seed ⇒
   mesmo canvas/GPU/núcleos; seeds diferentes ⇒ diferentes.
2. pproxy: `-l http://127.0.0.1:<porta>` escuta sem senha; `-r esquema://host:porta##<arquivo>`
   lê `usuario:senha` do arquivo (código `pproxy/server.py`, trecho `url.fragment`), então
   a senha não aparece na linha de comando. TLS até o proxy é `http+ssl`.
3. Fechar pelo CDP (`Browser.close`) faz o Chromium gravar cookies e sair em ~0,3 s.
4. Playwright: `browser.close()` num navegador conectado por CDP só desconecta.
5. Fechar a janela na mão é uso normal de app desktop: código de saída 0 ⇒ `fechado`,
   não `erro`. Só saída ≠ 0 vira `erro`.

## Arquivos

```
multiperfil/
  fingerprint.py      REMOVER (config congelado do Camoufox não existe mais)
  repositorio.py      MUDAR: Perfil ganha seed e idioma, perde config
  rede.py             NOVO: porta livre, esperar porta abrir
  repassador.py       NOVO: pproxy por perfil, credencial em arquivo
  lancador.py         REESCREVER: Chromium + CDP
  api.py              NOVO (substitui a tarefa 7 antiga)
  __main__.py         NOVO
  cliente.py          NOVO
prototipo/
  spike_login.py, spike_login_sonda.py, diagnostico_passos.py   REMOVER (Camoufox)
  spike_chromium.py   MANTER (referência do portão 2) — passa a importar a sonda inline
tests/
  test_fingerprint.py REMOVER
  test_repositorio.py MUDAR
  test_rede.py, test_repassador.py, test_lancador.py (reescrito), test_api.py
```

---

### Tarefa 11: Perfil com seed e idioma; tirar o Camoufox do caminho

**Arquivos:** modificar `multiperfil/repositorio.py`, `tests/test_repositorio.py`,
`prototipo/spike_chromium.py`; remover `multiperfil/fingerprint.py`,
`tests/test_fingerprint.py`, `prototipo/spike_login.py`, `prototipo/spike_login_sonda.py`,
`prototipo/diagnostico_passos.py`.

- [ ] **Passo 1:** em `tests/test_repositorio.py`, trocar o helper e o teste de atualizar,
  e acrescentar a validação de idioma:

```python
def _perfil(pid: str = "canal-a") -> Perfil:
    return Perfil(
        id=pid,
        nome="Canal A",
        sistema="windows",
        proxy=Proxy("socks5", "h", 1080, "u", "p@ss"),
        seed=123456,
        idioma="pt-BR",
        notas="",
    )


def test_criar_obter_listar(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    obtido = repo.obter("canal-a")
    assert obtido.proxy == Proxy("socks5", "h", 1080, "u", "p@ss")
    assert (obtido.seed, obtido.idioma) == (123456, "pt-BR")
    assert [p.id for p in repo.listar()] == ["canal-a"]


def test_atualizar_nao_toca_na_seed(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    repo.atualizar("canal-a", nome="Novo", proxy=Proxy("http", "x", 1), idioma="en-US", notas="n")
    p = repo.obter("canal-a")
    assert (p.nome, p.proxy, p.idioma, p.notas, p.seed) == (
        "Novo", Proxy("http", "x", 1), "en-US", "n", 123456)


@pytest.mark.parametrize("idioma", ["", "portugues", "pt_BR", "PT-br", "pt-BR;q=1"])
def test_idioma_invalido(tmp_path, idioma):
    repo = Repositorio(tmp_path / "p.db")
    with pytest.raises(ValueError):
        repo.criar(Perfil("a", "A", "windows", Proxy("http", "h", 1), 1, idioma, ""))
```

Remover `test_atualizar_nao_toca_no_config` (substituído). Os demais testes do arquivo
continuam, usando o novo `_perfil`.

- [ ] **Passo 2:** rodar `.venv\Scripts\python -m pytest tests/test_repositorio.py -q` —
  FALHA (`Perfil` não aceita `seed`).

- [ ] **Passo 3:** em `multiperfil/repositorio.py`:
  - remover `from multiperfil.fingerprint import Config`;
  - acrescentar `PADRAO_IDIOMA = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")` e

```python
def validar_idioma(idioma: str) -> str:
    if not PADRAO_IDIOMA.match(idioma):
        raise ValueError("idioma deve ser como pt-BR, en-US ou pt")
    return idioma
```

  - `Perfil` passa a ser `id, nome, sistema, proxy, seed: int, idioma: str, notas`;
  - esquema:

```python
ESQUEMA = """
CREATE TABLE IF NOT EXISTS perfis (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    sistema TEXT NOT NULL,
    proxy TEXT NOT NULL,
    seed INTEGER NOT NULL,
    idioma TEXT NOT NULL,
    notas TEXT NOT NULL,
    criado_em TEXT NOT NULL
)
"""
```

  - `_de_linha` lê `seed=linha["seed"], idioma=linha["idioma"]` no lugar de `config`;
  - `criar` chama `validar_idioma(perfil.idioma)` e grava
    `(perfil.id, perfil.nome, perfil.sistema, url_completa(perfil.proxy), perfil.seed,
    perfil.idioma, perfil.notas, agora)` com `INSERT INTO perfis VALUES (?, ?, ?, ?, ?, ?, ?, ?)`;
  - `atualizar(self, perfil_id, *, nome, proxy, idioma, notas)` valida o idioma e faz
    `UPDATE perfis SET nome = ?, proxy = ?, idioma = ?, notas = ? WHERE id = ?`.

  Não há banco em uso (nenhum `dados/perfis.db` foi criado), então não há migração.

- [ ] **Passo 4:** remover os arquivos Camoufox listados acima (`git rm`). Em
  `prototipo/spike_chromium.py`, trocar a linha `SONDA = Path(...)...` pela sonda inline:

```python
SONDA = """() => {
  const c = document.createElement('canvas'); const g = c.getContext('2d');
  g.font = '16px Arial'; g.fillText('MultiPerfil', 2, 20);
  return {ua: navigator.userAgent, tela: [screen.width, screen.height],
          janela: [innerWidth, innerHeight], fuso: Intl.DateTimeFormat().resolvedOptions().timeZone,
          idioma: navigator.language, canvas: c.toDataURL()};
}"""
```

- [ ] **Passo 5:** `.venv\Scripts\python -m pytest -q` — tudo verde **exceto**
  `tests/test_lancador.py`, que ainda importa `multiperfil.fingerprint` via lançador
  antigo. Remover também `multiperfil/lancador.py` e `tests/test_lancador.py` neste
  passo (a tarefa 13 os recria). Esperado: verde.

- [ ] **Passo 6: Commit** — `refactor: perfil com seed e idioma; remove o caminho Camoufox`

---

### Tarefa 12: `rede.py` e `repassador.py`

**Arquivos:** criar `multiperfil/rede.py`, `multiperfil/repassador.py`, `tests/test_rede.py`,
`tests/test_repassador.py`; adicionar `pproxy==2.7.9` em `pyproject.toml` (dependências).

- [ ] **Passo 1: Testes**

`tests/test_rede.py`:

```python
import socket
import subprocess
import sys

import pytest

from multiperfil.rede import ErroRede, esperar_porta, porta_livre


def test_porta_livre_esta_livre():
    porta = porta_livre()
    with socket.socket() as s:
        s.bind(("127.0.0.1", porta))


def test_esperar_porta_que_abre():
    with socket.socket() as servidor:
        servidor.bind(("127.0.0.1", 0))
        servidor.listen()
        processo = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
        try:
            esperar_porta(servidor.getsockname()[1], processo, prazo_s=2)
        finally:
            processo.kill()


def test_esperar_porta_falha_se_processo_morre():
    processo = subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"])
    with pytest.raises(ErroRede, match="código 3"):
        esperar_porta(porta_livre(), processo, prazo_s=5)
```

`tests/test_repassador.py` (ponta a ponta sem internet: um pproxy "remoto" com senha na
frente de um servidor HTTP local):

```python
import http.server
import socket
import subprocess
import sys
import threading

import pytest

from multiperfil.proxy import Proxy
from multiperfil.rede import esperar_porta, porta_livre
from multiperfil.repassador import Repassador, uri_remota


class _Ok(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture
def destino():
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Ok)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield servidor.server_address[1]
    servidor.shutdown()


@pytest.fixture
def remoto_com_senha():
    porta = porta_livre()
    processo = subprocess.Popen(
        [sys.executable, "-m", "pproxy", "-l", f"http://127.0.0.1:{porta}#ana:segredo"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    esperar_porta(porta, processo, prazo_s=10)
    yield porta
    processo.kill()
    processo.wait()


def _get_via(porta_proxy: int, porta_destino: int) -> bytes:
    with socket.create_connection(("127.0.0.1", porta_proxy), timeout=10) as s:
        s.sendall(f"GET http://127.0.0.1:{porta_destino}/ HTTP/1.1\r\n"
                  f"Host: 127.0.0.1:{porta_destino}\r\nConnection: close\r\n\r\n".encode())
        resposta = b""
        while dados := s.recv(4096):
            resposta += dados
    return resposta


def test_uri_remota_sem_senha_na_uri(tmp_path):
    auth = tmp_path / "a.auth"
    assert uri_remota(Proxy("http", "h", 1, "u", "s"), auth) == f"http://h:1##{auth}"
    assert uri_remota(Proxy("socks5", "h", 1), None) == "socks5://h:1"
    assert uri_remota(Proxy("https", "h", 1), None) == "http+ssl://h:1"


def test_encaminha_com_senha_e_limpa_arquivo(tmp_path, destino, remoto_com_senha):
    repassador = Repassador(tmp_path)
    porta = repassador.abrir("t", Proxy("http", "127.0.0.1", remoto_com_senha, "ana", "segredo"))
    assert (tmp_path / "t.auth").exists()
    assert _get_via(porta, destino).endswith(b"ok")
    repassador.fechar("t")
    assert not (tmp_path / "t.auth").exists()


def test_senha_errada_nao_passa(tmp_path, destino, remoto_com_senha):
    repassador = Repassador(tmp_path)
    porta = repassador.abrir("t", Proxy("http", "127.0.0.1", remoto_com_senha, "ana", "errada"))
    try:
        assert not _get_via(porta, destino).endswith(b"ok")
    finally:
        repassador.fechar("t")


def test_abrir_duas_vezes_troca_o_processo(tmp_path, remoto_com_senha):
    repassador = Repassador(tmp_path)
    proxy = Proxy("http", "127.0.0.1", remoto_com_senha, "ana", "segredo")
    primeira = repassador.abrir("t", proxy)
    segunda = repassador.abrir("t", proxy)
    assert primeira != segunda
    repassador.fechar("t")
```

- [ ] **Passo 2:** rodar — FALHA (`ModuleNotFoundError`).

- [ ] **Passo 3: `multiperfil/rede.py`**

```python
"""Portas locais: achar uma livre e esperar um processo começar a escutar nela."""

from __future__ import annotations

import socket
import subprocess
import time


class ErroRede(Exception):
    pass


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def esperar_porta(porta: int, processo: subprocess.Popen, prazo_s: float) -> None:
    """Espera `porta` aceitar conexão; falha na hora se o processo dono morrer."""
    limite = time.monotonic() + prazo_s
    while time.monotonic() < limite:
        if (codigo := processo.poll()) is not None:
            raise ErroRede(f"processo saiu com código {codigo} antes de escutar na porta {porta}")
        try:
            with socket.create_connection(("127.0.0.1", porta), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise ErroRede(f"porta {porta} não abriu em {prazo_s}s")
```

- [ ] **Passo 4: `multiperfil/repassador.py`**

```python
"""Proxy local sem senha na frente do proxy real: o Chromium não aceita proxy com senha.

Usa pproxy. A credencial vai num arquivo que o pproxy lê (`##arquivo`), nunca na linha
de comando — que qualquer processo da máquina consegue listar. O arquivo some ao fechar.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from multiperfil.proxy import Proxy
from multiperfil.rede import esperar_porta, porta_livre

PRAZO_S = 10
ESQUEMA_PPROXY = {"http": "http", "https": "http+ssl", "socks5": "socks5"}


def uri_remota(proxy: Proxy, arquivo_auth: Path | None) -> str:
    base = f"{ESQUEMA_PPROXY[proxy.esquema]}://{proxy.host}:{proxy.porta}"
    return f"{base}##{arquivo_auth}" if arquivo_auth else base


class Repassador:
    """Um pproxy por perfil aberto. Chamador serializa por perfil_id (estado.Registro)."""

    def __init__(self, pasta: Path) -> None:
        self._pasta = pasta
        self._processos: dict[str, subprocess.Popen] = {}

    def _escrever_auth(self, perfil_id: str, proxy: Proxy) -> Path | None:
        if not proxy.usuario:
            return None
        self._pasta.mkdir(parents=True, exist_ok=True)
        arquivo = self._pasta / f"{perfil_id}.auth"
        arquivo.write_text(f"{proxy.usuario}:{proxy.senha or ''}", encoding="utf-8")
        return arquivo

    def abrir(self, perfil_id: str, proxy: Proxy) -> int:
        self.fechar(perfil_id)
        porta = porta_livre()
        remoto = uri_remota(proxy, self._escrever_auth(perfil_id, proxy))
        processo = subprocess.Popen(  # nosec - argv fixo, sem shell
            [sys.executable, "-m", "pproxy", "-l", f"http://127.0.0.1:{porta}", "-r", remoto],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self._processos[perfil_id] = processo
        try:
            esperar_porta(porta, processo, PRAZO_S)
        except Exception:
            self.fechar(perfil_id)
            raise
        return porta

    def fechar(self, perfil_id: str) -> None:
        processo = self._processos.pop(perfil_id, None)
        if processo is not None:
            processo.kill()
            processo.wait()
        (self._pasta / f"{perfil_id}.auth").unlink(missing_ok=True)
```

- [ ] **Passo 5:** `pyproject.toml`: acrescentar `"pproxy==2.7.9",  # Chromium não aceita
  proxy com senha` nas dependências. Rodar `.venv\Scripts\python -m pytest -q` — verde.

- [ ] **Passo 6: Commit** — `feat: repassador local de proxy com credencial em arquivo`

---

### Tarefa 13: `lancador.py` — Chromium + CDP

**Arquivos:** criar `multiperfil/lancador.py`, `tests/test_lancador.py`

- [ ] **Passo 1: Testes (partes puras)**

```python
from pathlib import Path

from multiperfil.lancador import argumentos_chrome, comando_matar_arvore
from multiperfil.proxy import Proxy
from multiperfil.repositorio import Perfil


def _perfil(idioma: str = "pt-BR") -> Perfil:
    return Perfil("canal-a", "A", "windows", Proxy("http", "h", 1, "u", "segredo"), 4242, idioma, "")


def test_argumentos_chrome():
    args = argumentos_chrome(Path("C:/nav/chrome.exe"), Path("C:/dados/perfis/canal-a"),
                             _perfil(), "Europe/Bratislava", porta_proxy=7001, porta_cdp=9222)
    assert args[0] == str(Path("C:/nav/chrome.exe"))
    for esperado in [
        f"--user-data-dir={Path('C:/dados/perfis/canal-a')}",
        "--fingerprint=4242",
        "--fingerprint-platform=windows",
        "--timezone=Europe/Bratislava",
        "--lang=pt-BR",
        "--accept-lang=pt-BR,pt",
        "--proxy-server=http://127.0.0.1:7001",
        "--remote-debugging-port=9222",
        "--no-first-run",
    ]:
        assert esperado in args
    assert not any("segredo" in a for a in args)


def test_accept_lang_sem_regiao_nao_repete():
    args = argumentos_chrome(Path("c.exe"), Path("p"), _perfil("pt"), "UTC", 1, 2)
    assert "--accept-lang=pt" in args


def test_comando_matar_arvore():
    assert comando_matar_arvore(123, "nt") == ["taskkill", "/pid", "123", "/T", "/F"]
    assert comando_matar_arvore(123, "posix") is None
```

- [ ] **Passo 2:** rodar — FALHA.

- [ ] **Passo 3: Implementação**

```python
"""Sobe e fecha um fingerprint-chromium por perfil e devolve o endereço CDP.

Pasta de perfil persistente (login e cache ficam entre aberturas), seed fixa por perfil,
fuso do IP do proxy, e o proxy entra pelo repassador local (Chromium não aceita senha).
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Protocol

from playwright.sync_api import Error as ErroPlaywright
from playwright.sync_api import sync_playwright

from multiperfil.proxy import Proxy
from multiperfil.rede import esperar_porta, porta_livre
from multiperfil.repositorio import Perfil

log = logging.getLogger("multiperfil.lancador")

PRAZO_ABRIR_S = 30
PRAZO_FECHAR_S = 15


class ErroLancamento(Exception):
    pass


class RepassadorProto(Protocol):
    def abrir(self, perfil_id: str, proxy: Proxy) -> int: ...
    def fechar(self, perfil_id: str) -> None: ...


def argumentos_chrome(executavel: Path, pasta_perfil: Path, perfil: Perfil, fuso: str,
                      porta_proxy: int, porta_cdp: int) -> list[str]:
    base = perfil.idioma.split("-")[0]
    aceitos = f"{perfil.idioma},{base}" if "-" in perfil.idioma else perfil.idioma
    return [
        str(executavel),
        f"--user-data-dir={pasta_perfil}",
        f"--fingerprint={perfil.seed}",
        f"--fingerprint-platform={perfil.sistema}",
        f"--timezone={fuso}",
        f"--lang={perfil.idioma}",
        f"--accept-lang={aceitos}",
        f"--proxy-server=http://127.0.0.1:{porta_proxy}",
        f"--remote-debugging-port={porta_cdp}",
        "--no-first-run",
        "--no-default-browser-check",
    ]


def comando_matar_arvore(pid: int, sistema: str) -> list[str] | None:
    """No Windows matar o pai não mata os filhos; taskkill /T derruba a árvore."""
    return ["taskkill", "/pid", str(pid), "/T", "/F"] if sistema == "nt" else None


def _matar_forcado(processo: subprocess.Popen) -> None:
    comando = comando_matar_arvore(processo.pid, os.name)
    if comando is None:
        processo.kill()
    else:
        subprocess.run(comando, check=False, capture_output=True)
    processo.wait()


def _pedir_fechamento(url_cdp: str) -> None:
    """Browser.close pelo CDP: o Chromium grava cookies e cache antes de sair."""
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(url_cdp, timeout=5000)
        browser.new_browser_cdp_session().send("Browser.close")


class Lancador:
    """Um Chromium por perfil. O chamador serializa por perfil_id (estado.Registro)."""

    def __init__(self, executavel: Path, pasta_perfis: Path, repassador: RepassadorProto) -> None:
        self._executavel = executavel
        self._pasta_perfis = pasta_perfis
        self._repassador = repassador
        self._abertos: dict[str, tuple[subprocess.Popen, str]] = {}

    def abrir(self, perfil: Perfil, fuso: str) -> str:
        if not self._executavel.exists():
            raise ErroLancamento(f"navegador não encontrado em {self._executavel}")
        porta_proxy = self._repassador.abrir(perfil.id, perfil.proxy)
        porta_cdp = porta_livre()
        args = argumentos_chrome(self._executavel, self._pasta_perfis / perfil.id, perfil,
                                 fuso, porta_proxy, porta_cdp)
        try:
            processo = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self._repassador.fechar(perfil.id)
            raise
        url = f"http://127.0.0.1:{porta_cdp}"
        self._abertos[perfil.id] = (processo, url)
        try:
            esperar_porta(porta_cdp, processo, PRAZO_ABRIR_S)
        except Exception:
            self.fechar(perfil.id)
            raise
        return url

    def vivo(self, perfil_id: str) -> bool:
        aberto = self._abertos.get(perfil_id)
        return aberto is not None and aberto[0].poll() is None

    def codigo_saida(self, perfil_id: str) -> int | None:
        """None = rodando ou desconhecido."""
        aberto = self._abertos.get(perfil_id)
        return aberto[0].poll() if aberto else None

    def fechar(self, perfil_id: str) -> None:
        aberto = self._abertos.pop(perfil_id, None)
        try:
            if aberto is not None and aberto[0].poll() is None:
                self._fechar_processo(perfil_id, *aberto)
        finally:
            self._repassador.fechar(perfil_id)

    def _fechar_processo(self, perfil_id: str, processo: subprocess.Popen, url: str) -> None:
        try:
            _pedir_fechamento(url)
            processo.wait(timeout=PRAZO_FECHAR_S)
        except (ErroPlaywright, subprocess.TimeoutExpired) as erro:
            log.warning("[%s] não fechou limpo (%s), encerrando à força", perfil_id, erro)
            _matar_forcado(processo)
```

- [ ] **Passo 4:** `.venv\Scripts\python -m pytest -q` — verde.

- [ ] **Passo 5: Commit** — `feat: lancador do fingerprint-chromium com CDP`

---

### Tarefa 14: `api.py`

**Arquivos:** criar `multiperfil/api.py`, `tests/test_api.py`

- [ ] **Passo 1: Testes**

```python
import pytest
from fastapi.testclient import TestClient

from multiperfil.api import Dependencias, criar_app
from multiperfil.estado import Registro
from multiperfil.proxy import ErroProxy, ResultadoProxy
from multiperfil.repositorio import Repositorio


class LancadorFalso:
    def __init__(self) -> None:
        self.abertos: dict[str, int | None] = {}
        self.fusos: list[str] = []

    def abrir(self, perfil, fuso: str) -> str:
        self.fusos.append(fuso)
        self.abertos[perfil.id] = None
        return f"http://127.0.0.1:9/{perfil.id}"

    def vivo(self, perfil_id: str) -> bool:
        return perfil_id in self.abertos and self.abertos[perfil_id] is None

    def codigo_saida(self, perfil_id: str) -> int | None:
        return self.abertos.get(perfil_id)

    def fechar(self, perfil_id: str) -> None:
        self.abertos.pop(perfil_id, None)


def _proxy_ok(proxy):
    return ResultadoProxy("5.6.7.8", "SK", "Europe/Bratislava", 120)


def _proxy_morto(proxy):
    raise ErroProxy("proxy http://u:***@h:1 não respondeu")


@pytest.fixture
def montar(tmp_path):
    def _montar(testar=_proxy_ok):
        lancador = LancadorFalso()
        deps = Dependencias(
            repo=Repositorio(tmp_path / "p.db"),
            lancador=lancador,
            registro=Registro(),
            pasta_perfis=tmp_path / "perfis",
            nova_seed=lambda: 777,
            testar_proxy=testar,
        )
        return TestClient(criar_app(deps)), lancador, deps
    return _montar


NOVO = {"id": "canal-a", "nome": "Canal A", "proxy": "http://u:segredo@h:1"}


def test_criar_com_padroes_e_listar_sem_senha(montar):
    cliente, _, deps = montar()
    assert cliente.post("/perfis", json=NOVO).status_code == 201
    perfil = cliente.get("/perfis").json()[0]
    assert perfil["proxy"] == "http://u:***@h:1"
    assert (perfil["sistema"], perfil["idioma"], perfil["status"]) == ("windows", "pt-BR", "fechado")
    assert deps.repo.obter("canal-a").seed == 777
    assert "segredo" not in cliente.get("/perfis").text


def test_criar_duplicado_409_e_invalidos_422(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    assert cliente.post("/perfis", json=NOVO).status_code == 409
    assert cliente.post("/perfis", json={**NOVO, "id": "b", "proxy": "lixo"}).status_code == 422
    assert cliente.post("/perfis", json={**NOVO, "id": "c", "idioma": "xx_YY"}).status_code == 422
    assert cliente.post("/perfis", json={**NOVO, "id": "Com Espaço"}).status_code == 422


def test_abrir_usa_fuso_do_proxy_e_devolve_cdp(montar):
    cliente, lancador, _ = montar()
    cliente.post("/perfis", json=NOVO)
    r = cliente.post("/perfis/canal-a/abrir")
    assert r.status_code == 200
    assert r.json() == {"cdp": "http://127.0.0.1:9/canal-a"}
    assert lancador.fusos == ["Europe/Bratislava"]
    assert cliente.get("/perfis/canal-a/status").json()["status"] == "aberto"


def test_abrir_duas_vezes_409_com_cdp(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    r = cliente.post("/perfis/canal-a/abrir")
    assert r.status_code == 409
    assert r.json()["detail"]["cdp"] == "http://127.0.0.1:9/canal-a"


def test_proxy_morto_nao_abre(montar):
    cliente, lancador, _ = montar(testar=_proxy_morto)
    cliente.post("/perfis", json=NOVO)
    assert cliente.post("/perfis/canal-a/abrir").status_code == 502
    assert lancador.abertos == {}
    assert cliente.get("/perfis/canal-a/status").json()["status"] == "fechado"


def test_janela_fechada_na_mao_vira_fechado(montar):
    cliente, lancador, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    lancador.abertos["canal-a"] = 0
    assert cliente.get("/perfis/canal-a/status").json()["status"] == "fechado"
    assert "canal-a" not in lancador.abertos


def test_navegador_que_quebrou_vira_erro(montar):
    cliente, lancador, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    lancador.abertos["canal-a"] = 5
    corpo = cliente.get("/perfis/canal-a/status").json()
    assert corpo["status"] == "erro"
    assert "5" in corpo["erro"]


def test_editar_e_remover_bloqueados_enquanto_aberto(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    edicao = {"nome": "X", "proxy": "http://h:2", "idioma": "en-US", "notas": ""}
    assert cliente.patch("/perfis/canal-a", json=edicao).status_code == 409
    assert cliente.delete("/perfis/canal-a").status_code == 409
    assert cliente.post("/perfis/canal-a/fechar").json() == {"status": "fechado"}
    assert cliente.patch("/perfis/canal-a", json=edicao).json()["idioma"] == "en-US"


def test_remover_apaga_pasta_do_perfil(montar):
    cliente, _, deps = montar()
    cliente.post("/perfis", json=NOVO)
    pasta = deps.pasta_perfis / "canal-a"
    pasta.mkdir(parents=True)
    (pasta / "Cookies").write_text("x")
    assert cliente.delete("/perfis/canal-a").status_code == 204
    assert not pasta.exists()


def test_perfil_inexistente_404(montar):
    cliente, _, _ = montar()
    assert cliente.post("/perfis/nada/abrir").status_code == 404
```

- [ ] **Passo 2:** rodar — FALHA.

- [ ] **Passo 3: Implementação**

```python
"""API local. Serve a janela do app e os scripts — os dois são só clientes disto."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from multiperfil.estado import PerfilJaAberto, Registro, Status
from multiperfil.proxy import ErroProxy, Proxy, ResultadoProxy, descrever, parse_proxy
from multiperfil.repositorio import Perfil, PerfilExiste, PerfilInexistente, Repositorio, validar_id


class LancadorProto(Protocol):
    def abrir(self, perfil: Perfil, fuso: str) -> str: ...
    def vivo(self, perfil_id: str) -> bool: ...
    def codigo_saida(self, perfil_id: str) -> int | None: ...
    def fechar(self, perfil_id: str) -> None: ...


@dataclass(frozen=True)
class Dependencias:
    repo: Repositorio
    lancador: LancadorProto
    registro: Registro
    pasta_perfis: Path
    nova_seed: Callable[[], int]
    testar_proxy: Callable[[Proxy], ResultadoProxy]


class NovoPerfil(BaseModel):
    id: str
    nome: str
    proxy: str
    sistema: str = "windows"
    idioma: str = "pt-BR"
    notas: str = ""


class EdicaoPerfil(BaseModel):
    nome: str
    proxy: str
    idioma: str
    notas: str = ""


def _saida(perfil: Perfil, registro: Registro) -> dict:
    return {"id": perfil.id, "nome": perfil.nome, "sistema": perfil.sistema,
            "proxy": descrever(perfil.proxy), "idioma": perfil.idioma, "notas": perfil.notas,
            "status": registro.status(perfil.id).status}


def _exigir_fechado(deps: Dependencias, perfil_id: str) -> None:
    if deps.registro.ocupado(perfil_id):
        raise HTTPException(409, "feche o perfil antes de editar ou remover")


def _conferir_processo(deps: Dependencias, perfil_id: str) -> None:
    """Janela fechada na mão (código 0) é uso normal; só código ≠ 0 é erro."""
    if deps.registro.status(perfil_id).status is not Status.ABERTO or deps.lancador.vivo(perfil_id):
        return
    codigo = deps.lancador.codigo_saida(perfil_id)
    deps.lancador.fechar(perfil_id)
    if codigo == 0:
        deps.registro.liberar(perfil_id)
    else:
        deps.registro.marcar_erro(perfil_id, f"o navegador terminou com código {codigo}")


def criar_app(deps: Dependencias) -> FastAPI:
    app = FastAPI(title="MultiPerfil")

    @app.exception_handler(PerfilInexistente)
    def _404(_: Request, erro: PerfilInexistente) -> JSONResponse:
        return JSONResponse({"detail": f"perfil {erro.args[0]} não existe"}, status_code=404)

    @app.exception_handler(ValueError)
    def _422(_: Request, erro: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(erro)}, status_code=422)

    _rotas_cadastro(app, deps)
    _rotas_sessao(app, deps)
    return app


def _rotas_cadastro(app: FastAPI, deps: Dependencias) -> None:
    @app.get("/perfis")
    def listar() -> list[dict]:
        perfis = deps.repo.listar()
        for perfil in perfis:
            _conferir_processo(deps, perfil.id)
        return [_saida(p, deps.registro) for p in perfis]

    @app.post("/perfis", status_code=201)
    def criar(novo: NovoPerfil) -> dict:
        perfil = Perfil(validar_id(novo.id), novo.nome, novo.sistema, parse_proxy(novo.proxy),
                        deps.nova_seed(), novo.idioma, novo.notas)
        try:
            deps.repo.criar(perfil)
        except PerfilExiste:
            raise HTTPException(409, f"perfil {novo.id} já existe") from None
        return _saida(perfil, deps.registro)

    @app.patch("/perfis/{perfil_id}")
    def editar(perfil_id: str, edicao: EdicaoPerfil) -> dict:
        _exigir_fechado(deps, perfil_id)
        deps.repo.atualizar(perfil_id, nome=edicao.nome, proxy=parse_proxy(edicao.proxy),
                            idioma=edicao.idioma, notas=edicao.notas)
        return _saida(deps.repo.obter(perfil_id), deps.registro)

    @app.delete("/perfis/{perfil_id}", status_code=204)
    def remover(perfil_id: str) -> Response:
        _exigir_fechado(deps, perfil_id)
        deps.repo.remover(perfil_id)
        pasta = deps.pasta_perfis / perfil_id
        if pasta.exists():
            shutil.rmtree(pasta)  # login e cookies do perfil: apagar o perfil apaga tudo
        return Response(status_code=204)

    @app.post("/perfis/{perfil_id}/testar-proxy")
    def testar_proxy(perfil_id: str) -> dict:
        try:
            return vars(deps.testar_proxy(deps.repo.obter(perfil_id).proxy))
        except ErroProxy as erro:
            raise HTTPException(502, str(erro)) from None


def _rotas_sessao(app: FastAPI, deps: Dependencias) -> None:
    @app.post("/perfis/{perfil_id}/abrir")
    def abrir(perfil_id: str) -> dict:
        perfil = deps.repo.obter(perfil_id)
        _conferir_processo(deps, perfil_id)
        try:
            deps.registro.reservar(perfil_id)
        except PerfilJaAberto as erro:
            raise HTTPException(409, {"erro": str(erro), "cdp": erro.ws}) from None
        try:
            fuso = deps.testar_proxy(perfil.proxy).fuso
            cdp = deps.lancador.abrir(perfil, fuso)
        except Exception as erro:
            deps.registro.liberar(perfil_id)
            raise HTTPException(502 if isinstance(erro, ErroProxy) else 500, str(erro)) from None
        deps.registro.marcar_aberto(perfil_id, cdp)
        return {"cdp": cdp}

    @app.post("/perfis/{perfil_id}/fechar")
    def fechar(perfil_id: str) -> dict:
        deps.repo.obter(perfil_id)
        deps.lancador.fechar(perfil_id)
        deps.registro.liberar(perfil_id)
        return {"status": Status.FECHADO}

    @app.get("/perfis/{perfil_id}/status")
    def status(perfil_id: str) -> dict:
        deps.repo.obter(perfil_id)
        _conferir_processo(deps, perfil_id)
        sessao = deps.registro.status(perfil_id)
        return {"status": sessao.status, "cdp": sessao.ws, "erro": sessao.erro}
```

Nota para o implementador: o campo `Sessao.ws` de `estado.py` passa a guardar a URL
CDP; renomear para `endereco` é refactor fora do escopo — não faça.

- [ ] **Passo 4:** `.venv\Scripts\python -m pytest -q` — verde.

- [ ] **Passo 5: Commit** — `feat: API local de perfis (Chromium/CDP)`

---

### Tarefa 15: `__main__.py`, dependências e CLAUDE.md

**Arquivos:** criar `multiperfil/__main__.py`; modificar `pyproject.toml`, `CLAUDE.md`

- [ ] **Passo 1: `multiperfil/__main__.py`**

```python
"""`python -m multiperfil` — sobe a API em 127.0.0.1:8800 com as dependências reais."""

import logging
import os
import secrets
from pathlib import Path

import uvicorn
from camoufox.geolocation import get_geolocation
from camoufox.ip import public_ip

from multiperfil.api import Dependencias, criar_app
from multiperfil.estado import Registro
from multiperfil.lancador import Lancador
from multiperfil.proxy import testar
from multiperfil.repassador import Repassador
from multiperfil.repositorio import Repositorio

PORTA = 8800
NAVEGADOR_PADRAO = "navegador/ungoogled-chromium_148.0.7778.215-1.1_windows_x64/chrome.exe"


def montar_dependencias(dados: Path, navegador: Path) -> Dependencias:
    pasta_perfis = dados / "perfis"
    return Dependencias(
        repo=Repositorio(dados / "perfis.db"),
        lancador=Lancador(navegador, pasta_perfis, Repassador(dados / "repassadores")),
        registro=Registro(),
        pasta_perfis=pasta_perfis,
        nova_seed=lambda: secrets.randbelow(2**31 - 1) + 1,
        testar_proxy=lambda proxy: testar(proxy, public_ip, get_geolocation),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    dados = Path(os.environ.get("MULTIPERFIL_DADOS", "dados")).resolve()
    navegador = Path(os.environ.get("MULTIPERFIL_NAVEGADOR", NAVEGADOR_PADRAO)).resolve()
    uvicorn.run(criar_app(montar_dependencias(dados, navegador)), host="127.0.0.1", port=PORTA)


if __name__ == "__main__":
    main()
```

`montar_dependencias` fica separado de `main` porque a janela do app (plano seguinte)
reusa a mesma montagem.

- [ ] **Passo 2:** `pyproject.toml` — trocar o comentário do camoufox para
  `# só public_ip e get_geolocation (IP de saída → país e fuso)`. `CLAUDE.md` — trocar a
  primeira regra por:

```markdown
- Navegador: fingerprint-chromium em `navegador/` (fora do git; baixar do release
  adryfish/fingerprint-chromium e conferir o SHA-256). `--proxy-server` não aceita senha:
  todo proxy passa pelo `repassador.py`, com a credencial em arquivo, nunca em argv.
- camoufox fica só por `public_ip`/`get_geolocation`; nada de `camoufox.server`.
```

- [ ] **Passo 3: Verificação ao vivo** (controlador, com o proxy de `dados/proxy.txt`):
  subir `python -m multiperfil` em segundo plano; `POST /perfis` com o proxy; `abrir`
  devolve `cdp`; `status` = `aberto`; `fechar` fecha a janela em < 2 s; nenhum
  `chrome.exe` com caminho em `MultiPerfil` sobra; a senha não aparece no log do servidor
  nem em nenhuma resposta.

- [ ] **Passo 4: Commit** — `feat: servidor real do sidecar (Chromium)`

---

### Tarefa 16: `cliente.py` — helper para os scripts

**Arquivos:** criar `multiperfil/cliente.py`, `prototipo/teste_cliente.py`

- [ ] **Passo 1: `multiperfil/cliente.py`**

```python
"""Uso num script de publicação:

    async with async_playwright() as pw:
        async with abrir_perfil("canal-a", pw) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            ...

O login e o cache ficam na pasta do perfil; ao sair do bloco o perfil é fechado pela
API (Browser.close pelo CDP), com ou sem erro no meio.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from playwright.async_api import BrowserContext, Playwright

URL_PADRAO = "http://127.0.0.1:8800"


class ErroPerfil(Exception):
    pass


def _checar(resposta: httpx.Response) -> dict:
    if resposta.is_error:
        raise ErroPerfil(f"{resposta.status_code}: {resposta.text}")
    return resposta.json()


@asynccontextmanager
async def abrir_perfil(
    perfil_id: str, pw: Playwright, url: str = URL_PADRAO
) -> AsyncIterator[BrowserContext]:
    async with httpx.AsyncClient(base_url=url, timeout=120) as http:
        dados = _checar(await http.post(f"/perfis/{perfil_id}/abrir"))
        try:
            browser = await pw.chromium.connect_over_cdp(dados["cdp"])
            yield browser.contexts[0]
        finally:
            _checar(await http.post(f"/perfis/{perfil_id}/fechar"))
```

- [ ] **Passo 2: `prototipo/teste_cliente.py`**

```python
"""Com `python -m multiperfil` rodando e o perfil `teste` criado."""

import asyncio
import sys

from playwright.async_api import async_playwright

from multiperfil.cliente import abrir_perfil


async def main(perfil_id: str) -> None:
    async with async_playwright() as pw:
        async with abrir_perfil(perfil_id, pw) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto("https://ipinfo.io/json")
            print(await page.inner_text("body"))


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "teste"))
```

- [ ] **Passo 3: Verificação ao vivo** (controlador): com o servidor da tarefa 15 e o
  perfil criado, rodar o script — JSON do ipinfo com IP/país **do proxy**; janela fecha
  no fim; status volta a `fechado`.

- [ ] **Passo 4: Commit** — `feat: helper abrir_perfil (CDP) para scripts Playwright`

---

## Verificação ao vivo (2026-09-25, tarefas 15 e 16)

Serviço real + proxy da Eslováquia: criar 201 (senha mascarada); abrir 1,3 s → `cdp`;
segundo abrir 409 com o mesmo `cdp`; fechar 1,3 s (inclui subir o driver do Playwright —
não justifica dependência de websocket); senha ausente de todas as respostas e do log;
zero `chrome.exe`/pproxy órfãos; `.auth` apagado. `prototipo/teste_cliente.py`: ipinfo viu
IP/país/fuso do proxy (SK, Europe/Bratislava); ciclo completo 9 s.

## Depois deste plano

Plano separado: janela desktop em pywebview (lista de perfis com status, criar/editar com
campo de proxy e idioma, botões testar/abrir/fechar), aberta por atalho com duplo clique,
reusando `montar_dependencias`.
