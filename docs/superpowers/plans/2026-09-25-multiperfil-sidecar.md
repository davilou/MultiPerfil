# MultiPerfil — Sidecar Python: plano de implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development
> (recomendado) ou superpowers:executing-plans para executar tarefa por tarefa. Os passos
> usam checkbox (`- [ ]`).

**Objetivo:** serviço local que guarda perfis (proxy + fingerprint congelado), abre um
Camoufox por perfil e devolve o endpoint `ws://` para scripts Playwright externos.

**Arquitetura:** lógica pura (fingerprint, proxy, estado) separada do I/O (SQLite,
processo do navegador, HTTP). O navegador sobe pelo mesmo mecanismo do `launch_server`
do Camoufox (Node + `launchServer.js`), mas com o config trocado pelo congelado do
perfil. O login persiste em `storage_state` por perfil.

**Stack:** Python 3.13, camoufox 0.5.6 (fixado), Playwright 1.62, FastAPI, uvicorn,
httpx, pytest.

**Fora deste plano:** o app Tauri (plano separado, depois do sidecar; exige Rust).

---

## O que foi verificado no código do Camoufox 0.5.6 (2026-09-25)

Estes fatos sustentam o desenho. Se a versão do camoufox mudar, reconfira antes.

1. `camoufox.server.launch_server` **recusa** `persistent_context`/`user_data_dir`
   ("Playwright cannot serve a persistent context over a websocket endpoint"). Por isso
   o login vive em `storage_state` (plano B da spec virou o único).
2. `launch_options()` sorteia **a cada chamada**: seeds de canvas/áudio/fontes, subconjunto
   de fontes e vozes, e algumas chaves opcionais (`screen.availLeft`, `screen.availTop`,
   `navigator.maxTouchPoints`, `navigator.globalPrivacyControl`). Medido: passar o config
   de volta em `config=` estabiliza as chaves presentes, mas as opcionais continuam
   aparecendo e sumindo entre aberturas. Por isso o lançador **substitui** o config
   final pelo congelado, em vez de confiar em `config=`.
3. O config vai para o Firefox em variáveis `CAMOU_CONFIG_1..N`, JSON cortado em blocos
   de 2047 caracteres no Windows.
4. `launch_server` envia `base64(orjson(to_camel_case_dict(opções)))` + `\n` pelo stdin de
   `node launchServer.js <pasta do driver>`; fechar o stdin encerra o navegador; o
   endpoint sai no stdout na linha `Websocket endpoint: ws://...` (com códigos ANSI).
5. `camoufox.ip.public_ip(url_proxy)` usa `requests` (PySocks instalado → SOCKS funciona)
   e lança `camoufox.exceptions.InvalidIP` quando nenhum serviço responde.
6. `camoufox.geolocation.get_geolocation(ip)` devolve `Geolocation` com `timezone` e
   `locale.region`.

## Estrutura de arquivos

```
MultiPerfil/
  pyproject.toml            dependências fixadas + config do pytest
  CLAUDE.md                 comando de check do projeto
  .gitignore
  multiperfil/
    __init__.py
    fingerprint.py          PURO: extrair/congelar/reaplicar o config do Camoufox
    proxy.py                PURO + teste de proxy: parse, máscara, formato Playwright
    estado.py               PURO: registro de perfis abertos e trava
    repositorio.py          SQLite de perfis
    lancador.py             I/O: sobe/fecha o processo do navegador
    api.py                  FastAPI (recebe dependências por parâmetro)
    __main__.py             `python -m multiperfil` sobe o servidor real
    cliente.py              helper para os scripts: `abrir_perfil`
  prototipo/
    spike_login.py          prova manual: login Google persiste e fingerprint não muda
  tests/
    test_fingerprint.py
    test_proxy.py
    test_estado.py
    test_repositorio.py
    test_lancador.py
    test_api.py
```

Comando de check (todas as tarefas): `.venv\Scripts\python -m pytest -q`

---

### Tarefa 0: Andaime do projeto

**Arquivos:** criar `pyproject.toml`, `CLAUDE.md`, `.gitignore`, `multiperfil/__init__.py`

- [ ] **Passo 1: `pyproject.toml`**

```toml
[project]
name = "multiperfil"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "camoufox[geoip]==0.5.6",   # fixado: o lançador usa internos de camoufox.server
    "fastapi==0.141.1",
    "uvicorn==0.54.0",
    "httpx==0.28.1",
]

[project.optional-dependencies]
dev = ["pytest==9.1.1"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Passo 2: `.gitignore`**

```
.venv/
__pycache__/
dados/
*.pyc
```

- [ ] **Passo 3: `CLAUDE.md`**

```markdown
# MultiPerfil

Gerenciador de perfis Camoufox (proxy + fingerprint congelado) com API local para
scripts Playwright. Spec: docs/superpowers/specs/2026-09-25-multiperfil-design.md

## Check (rodar depois de cada mudança)

    .venv\Scripts\python -m pytest -q

## Regras do projeto

- camoufox fica FIXADO em 0.5.6: `lancador.py` usa internos de `camoufox.server`
  (`LAUNCH_SCRIPT`, `get_nodejs`, `to_camel_case_dict`). Subir a versão = reconferir
  a seção "O que foi verificado" do plano.
- Senha de proxy nunca vai para log, exceção ou resposta da API: use `proxy.descrever`.
- `dados/` guarda banco e sessões (cookies de login) — nunca versionar.
```

- [ ] **Passo 4:** `multiperfil/__init__.py` vazio. Instalar em modo editável:

Run: `.venv\Scripts\python -m pip install -e ".[dev]"`
Expected: `Successfully installed multiperfil-0.1.0`

- [ ] **Passo 5: Commit**

```bash
git add pyproject.toml CLAUDE.md .gitignore multiperfil/__init__.py
git commit -m "chore: andaime do sidecar MultiPerfil"
```

---

### Tarefa 1: `fingerprint.py` — congelar e reaplicar o config

**Arquivos:** criar `multiperfil/fingerprint.py`, `tests/test_fingerprint.py`

- [ ] **Passo 1: Testes que falham**

```python
import json

import pytest

from multiperfil.fingerprint import (
    TAMANHO_BLOCO,
    aplicar_congelado,
    dividir_em_env,
    extrair_config,
    gerar_congelado,
    montar_config,
    separar_geo,
)


def _env_de(config: dict, tamanho: int = 10) -> dict:
    texto = json.dumps(config)
    return {
        f"CAMOU_CONFIG_{i // tamanho + 1}": texto[i : i + tamanho]
        for i in range(0, len(texto), tamanho)
    }


def test_extrair_config_junta_blocos_na_ordem_numerica():
    config = {"navigator.userAgent": "x" * 50, "canvas:seed": 7}
    env = _env_de(config)  # 12+ blocos: ordena 10 depois de 9, não depois de 1
    env["OUTRA"] = "ignorada"
    assert extrair_config(env) == config


def test_extrair_config_sem_blocos_falha_alto():
    with pytest.raises(ValueError, match="CAMOU_CONFIG_"):
        extrair_config({"PATH": "x"})


def test_separar_geo():
    config = {
        "timezone": "America/Sao_Paulo",
        "geolocation:latitude": 1.0,
        "locale:region": "BR",
        "webrtc:ipv4": "1.2.3.4",
        "canvas:seed": 7,
    }
    fixo, geo = separar_geo(config)
    assert fixo == {"canvas:seed": 7}
    assert set(geo) == {"timezone", "geolocation:latitude", "locale:region", "webrtc:ipv4"}


def test_montar_config_mantem_congelado_e_pega_geo_do_gerado():
    congelado = {"canvas:seed": 7, "fonts": ["Arial"]}
    gerado = {"canvas:seed": 99, "screen.availTop": 5, "timezone": "Europe/Berlin"}
    assert montar_config(congelado, gerado) == {
        "canvas:seed": 7,
        "fonts": ["Arial"],
        "timezone": "Europe/Berlin",
    }


def test_montar_config_recusa_congelado_com_geo():
    with pytest.raises(ValueError, match="timezone"):
        montar_config({"timezone": "UTC"}, {})


def test_dividir_em_env_ida_e_volta():
    config = {"a": "ç" * 5000, "b": [1, 2]}
    env = dividir_em_env(config, TAMANHO_BLOCO)
    assert all(len(v) <= TAMANHO_BLOCO for v in env.values())
    assert extrair_config(env) == config


def test_aplicar_congelado_troca_so_os_blocos():
    gerado = {"canvas:seed": 99, "navigator.maxTouchPoints": 5, "timezone": "Asia/Tokyo"}
    opcoes = {"env": {**_env_de(gerado), "PATH": "p"}, "headless": False}
    resultado = aplicar_congelado(opcoes, {"canvas:seed": 7})
    assert resultado["headless"] is False
    assert resultado["env"]["PATH"] == "p"
    assert extrair_config(resultado["env"]) == {"canvas:seed": 7, "timezone": "Asia/Tokyo"}


def test_gerar_congelado_tira_geo_e_repassa_sistema():
    chamadas = []

    def gerar_falso(**kw):
        chamadas.append(kw)
        return {"env": _env_de({"canvas:seed": 7, "timezone": "UTC"})}

    assert gerar_congelado("windows", gerar_falso) == {"canvas:seed": 7}
    assert chamadas == [{"os": "windows", "headless": False, "i_know_what_im_doing": True}]
```

- [ ] **Passo 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m pytest tests/test_fingerprint.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'multiperfil.fingerprint'`

- [ ] **Passo 3: Implementação**

```python
"""Congela o fingerprint do Camoufox: o config é gerado uma vez e reaplicado igual.

`launch_options()` sorteia seeds, fontes, vozes e chaves opcionais a cada chamada
(medido em 0.5.6). Um perfil que muda de "computador" a cada abertura é o que faz a
conta pedir verificação. Só a geolocalização acompanha o proxy do momento.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping

Config = dict[str, Any]
GeradorOpcoes = Callable[..., Config]

PREFIXO_ENV = "CAMOU_CONFIG_"
PREFIXOS_GEO: tuple[str, ...] = ("timezone", "geolocation:", "locale:", "webrtc:")
# Mesmo corte que camoufox.utils.get_env_vars usa no Windows.
TAMANHO_BLOCO = 2047


def extrair_config(env: Mapping[str, Any]) -> Config:
    chaves = [k for k in env if k.startswith(PREFIXO_ENV)]
    if not chaves:
        raise ValueError(f"env sem {PREFIXO_ENV}*: o formato de launch_options mudou")
    chaves.sort(key=lambda k: int(k[len(PREFIXO_ENV) :]))
    return json.loads("".join(str(env[k]) for k in chaves))


def eh_geo(chave: str) -> bool:
    return chave.startswith(PREFIXOS_GEO)


def separar_geo(config: Config) -> tuple[Config, Config]:
    fixo = {k: v for k, v in config.items() if not eh_geo(k)}
    geo = {k: v for k, v in config.items() if eh_geo(k)}
    return fixo, geo


def montar_config(congelado: Config, gerado: Config) -> Config:
    intrusas = sorted(k for k in congelado if eh_geo(k))
    if intrusas:
        raise ValueError(f"config congelado contém geolocalização: {intrusas}")
    _, geo = separar_geo(gerado)
    return {**congelado, **geo}


def dividir_em_env(config: Config, tamanho: int) -> dict[str, str]:
    texto = json.dumps(config, separators=(",", ":"), ensure_ascii=False)
    return {
        f"{PREFIXO_ENV}{i // tamanho + 1}": texto[i : i + tamanho]
        for i in range(0, len(texto), tamanho)
    }


def aplicar_congelado(opcoes: Config, congelado: Config) -> Config:
    """Troca o config sorteado por launch_options pelo congelado + geo do proxy atual."""
    env = dict(opcoes["env"])
    gerado = extrair_config(env)
    for chave in [k for k in env if k.startswith(PREFIXO_ENV)]:
        del env[chave]
    env.update(dividir_em_env(montar_config(congelado, gerado), TAMANHO_BLOCO))
    return {**opcoes, "env": env}


def gerar_congelado(sistema: str, gerar: GeradorOpcoes) -> Config:
    """Gera um fingerprint novo para `sistema` e devolve a parte que não depende do IP."""
    opcoes = gerar(os=sistema, headless=False, i_know_what_im_doing=True)
    fixo, _ = separar_geo(extrair_config(opcoes["env"]))
    return fixo
```

- [ ] **Passo 4: Rodar e ver passar**

Run: `.venv\Scripts\python -m pytest tests/test_fingerprint.py -q`
Expected: `8 passed`

- [ ] **Passo 5: Checagem contra o Camoufox real** (sem abrir navegador)

Run:
```bash
.venv\Scripts\python -c "from camoufox.utils import launch_options as g; from multiperfil.fingerprint import *; c=gerar_congelado('windows', g); o=[extrair_config(aplicar_congelado(g(config=dict(c), headless=False, i_know_what_im_doing=True), c)['env']) for _ in range(20)]; print(all(x==o[0]==c for x in o))"
```
Expected: `True` (20 aberturas, config idêntico ao congelado)

- [ ] **Passo 6: Commit**

```bash
git add multiperfil/fingerprint.py tests/test_fingerprint.py
git commit -m "feat: congelamento do fingerprint do Camoufox"
```

---

### Tarefa 2: `proxy.py` — parse, máscara e teste

**Arquivos:** criar `multiperfil/proxy.py`, `tests/test_proxy.py`

- [ ] **Passo 1: Testes que falham**

```python
import pytest

from multiperfil.proxy import (
    ErroProxy,
    Proxy,
    descrever,
    para_playwright,
    para_requests,
    parse_proxy,
    testar,
    url_completa,
)


def test_parse_url_com_credenciais():
    p = parse_proxy("socks5://ana:s%40nha@1.2.3.4:1080")
    assert p == Proxy("socks5", "1.2.3.4", 1080, "ana", "s@nha")


def test_parse_formato_revendedor_host_porta_usuario_senha():
    assert parse_proxy("1.2.3.4:8000:ana:pw") == Proxy("http", "1.2.3.4", 8000, "ana", "pw")


def test_parse_host_porta_sem_credenciais():
    assert parse_proxy(" 1.2.3.4:8000 ") == Proxy("http", "1.2.3.4", 8000)


@pytest.mark.parametrize("texto", ["ftp://h:1", "http://semporta", "a:b:c", ""])
def test_parse_invalido_falha_sem_ecoar_texto(texto):
    with pytest.raises(ValueError) as erro:
        parse_proxy(texto)
    assert "b:c" not in str(erro.value)


def test_descrever_mascara_senha():
    p = Proxy("socks5", "h", 1, "ana", "segredo")
    assert descrever(p) == "socks5://ana:***@h:1"
    assert "segredo" not in descrever(p)


def test_para_playwright_omite_credenciais_ausentes():
    assert para_playwright(Proxy("http", "h", 1)) == {"server": "http://h:1"}
    assert para_playwright(Proxy("http", "h", 1, "u", "p")) == {
        "server": "http://h:1",
        "username": "u",
        "password": "p",
    }


def test_url_completa_ida_e_volta_com_caractere_especial():
    p = Proxy("http", "h", 1, "a b", "s@:/")
    assert parse_proxy(url_completa(p)) == p


def test_para_requests_resolve_dns_no_proxy_socks():
    assert para_requests(Proxy("socks5", "h", 1)).startswith("socks5h://")
    assert para_requests(Proxy("http", "h", 1)).startswith("http://")


def test_testar_devolve_ip_pais_fuso():
    class Geo:
        timezone = "America/Sao_Paulo"

        class locale:
            region = "BR"

    r = testar(Proxy("http", "h", 1), buscar_ip=lambda url: "5.6.7.8", geolocalizar=lambda ip: Geo)
    assert (r.ip, r.pais, r.fuso) == ("5.6.7.8", "BR", "America/Sao_Paulo")
    assert r.latencia_ms >= 0


def test_testar_falha_sem_vazar_senha():
    def quebra(url):
        raise RuntimeError(f"falhou em {url}")

    with pytest.raises(ErroProxy) as erro:
        testar(Proxy("http", "h", 1, "u", "segredo"), buscar_ip=quebra, geolocalizar=None)
    assert "segredo" not in str(erro.value)
    assert "http://u:***@h:1" in str(erro.value)
```

- [ ] **Passo 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m pytest tests/test_proxy.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Passo 3: Implementação**

```python
"""Proxy de um perfil: parse, máscara da senha e teste de saída.

Proxy morto nunca pode virar "abre sem proxy": isso mostraria o IP real para a conta.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote, unquote, urlsplit

ESQUEMAS: tuple[str, ...] = ("http", "https", "socks5")
FORMATO_ESPERADO = "esquema://usuario:senha@host:porta, host:porta ou host:porta:usuario:senha"


@dataclass(frozen=True)
class Proxy:
    esquema: str
    host: str
    porta: int
    usuario: str | None = None
    senha: str | None = None


@dataclass(frozen=True)
class ResultadoProxy:
    ip: str
    pais: str | None
    fuso: str
    latencia_ms: int


class ErroProxy(Exception):
    pass


def _normalizar(texto: str) -> str:
    if "://" in texto:
        return texto
    partes = texto.split(":")
    if len(partes) == 2:
        return f"http://{partes[0]}:{partes[1]}"
    if len(partes) == 4:
        host, porta, usuario, senha = partes
        return f"http://{quote(usuario, safe='')}:{quote(senha, safe='')}@{host}:{porta}"
    raise ValueError(f"proxy em formato desconhecido; esperado {FORMATO_ESPERADO}")


def parse_proxy(texto: str) -> Proxy:
    url = urlsplit(_normalizar(texto.strip()))
    if url.scheme not in ESQUEMAS:
        raise ValueError(f"esquema de proxy não suportado; use um de {ESQUEMAS}")
    if not url.hostname or url.port is None:
        raise ValueError(f"proxy sem host ou porta; esperado {FORMATO_ESPERADO}")
    return Proxy(
        url.scheme,
        url.hostname,
        url.port,
        unquote(url.username) if url.username else None,
        unquote(url.password) if url.password else None,
    )


def _credenciais(p: Proxy, senha: str | None) -> str:
    if not p.usuario:
        return ""
    usuario = quote(p.usuario, safe="")
    return f"{usuario}:{senha}@" if senha is not None else f"{usuario}@"


def url_completa(p: Proxy) -> str:
    senha = quote(p.senha, safe="") if p.senha is not None else None
    return f"{p.esquema}://{_credenciais(p, senha)}{p.host}:{p.porta}"


def descrever(p: Proxy) -> str:
    """Forma segura para log, erro e API: a senha vira ***."""
    senha = "***" if p.senha is not None else None
    return f"{p.esquema}://{_credenciais(p, senha)}{p.host}:{p.porta}"


def para_requests(p: Proxy) -> str:
    """URL para o requests; socks5h resolve o DNS no proxy, sem vazar pelo IP real."""
    url = url_completa(p)
    return "socks5h" + url[len("socks5") :] if p.esquema == "socks5" else url


def para_playwright(p: Proxy) -> dict[str, str]:
    resultado = {"server": f"{p.esquema}://{p.host}:{p.porta}"}
    if p.usuario:
        resultado["username"] = p.usuario
    if p.senha:
        resultado["password"] = p.senha
    return resultado


def testar(
    p: Proxy,
    buscar_ip: Callable[[str], str],
    geolocalizar: Callable[[str], Any] | None,
) -> ResultadoProxy:
    inicio = time.perf_counter()
    try:
        ip = buscar_ip(para_requests(p))
    except Exception as erro:
        texto = str(erro).replace(url_completa(p), descrever(p)).replace(para_requests(p), descrever(p))
        raise ErroProxy(f"proxy {descrever(p)} não respondeu: {texto}") from None
    latencia = int((time.perf_counter() - inicio) * 1000)
    if geolocalizar is None:
        raise ErroProxy("geolocalizar é obrigatório quando o IP foi obtido")
    geo = geolocalizar(ip)
    return ResultadoProxy(ip=ip, pais=geo.locale.region, fuso=geo.timezone, latencia_ms=latencia)
```

Nota: `from None` corta a cadeia da exceção original de propósito — o `requests` põe a
URL com senha na mensagem, e a cadeia iria parar no log.

- [ ] **Passo 4: Rodar e ver passar**

Run: `.venv\Scripts\python -m pytest tests/test_proxy.py -q`
Expected: `13 passed`

- [ ] **Passo 5: Commit**

```bash
git add multiperfil/proxy.py tests/test_proxy.py
git commit -m "feat: parse, mascara e teste de proxy"
```

---

### Tarefa 3: `estado.py` — registro de perfis abertos

**Arquivos:** criar `multiperfil/estado.py`, `tests/test_estado.py`

- [ ] **Passo 1: Testes que falham**

```python
import pytest

from multiperfil.estado import PerfilJaAberto, Registro, Status


def test_perfil_desconhecido_esta_fechado():
    assert Registro().status("a").status is Status.FECHADO


def test_reservar_abrir_e_liberar():
    r = Registro()
    r.reservar("a")
    assert r.status("a").status is Status.ABRINDO
    r.marcar_aberto("a", "ws://x")
    assert (r.status("a").status, r.status("a").ws) == (Status.ABERTO, "ws://x")
    r.liberar("a")
    assert r.status("a").status is Status.FECHADO


@pytest.mark.parametrize("ws", [None, "ws://x"])
def test_segunda_reserva_falha_com_ws_existente(ws):
    r = Registro()
    r.reservar("a")
    if ws:
        r.marcar_aberto("a", ws)
    with pytest.raises(PerfilJaAberto) as erro:
        r.reservar("a")
    assert erro.value.ws == ws


def test_perfil_em_erro_pode_reabrir():
    r = Registro()
    r.reservar("a")
    r.marcar_erro("a", "caiu")
    assert (r.status("a").status, r.status("a").erro) == (Status.ERRO, "caiu")
    r.reservar("a")
    assert r.status("a").status is Status.ABRINDO


def test_ocupado():
    r = Registro()
    assert not r.ocupado("a")
    r.reservar("a")
    assert r.ocupado("a")
```

- [ ] **Passo 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m pytest tests/test_estado.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Passo 3: Implementação**

```python
"""Quem está aberto. Dois navegadores no mesmo perfil corrompem a sessão salva."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    FECHADO = "fechado"
    ABRINDO = "abrindo"
    ABERTO = "aberto"
    ERRO = "erro"


@dataclass(frozen=True)
class Sessao:
    status: Status
    ws: str | None = None
    erro: str | None = None


class PerfilJaAberto(Exception):
    def __init__(self, perfil_id: str, ws: str | None) -> None:
        super().__init__(f"perfil {perfil_id} já está aberto")
        self.ws = ws


class Registro:
    """Seguro entre threads: o FastAPI roda rotas síncronas num pool."""

    def __init__(self) -> None:
        self._sessoes: dict[str, Sessao] = {}
        self._trava = threading.Lock()

    def status(self, perfil_id: str) -> Sessao:
        with self._trava:
            return self._sessoes.get(perfil_id, Sessao(Status.FECHADO))

    def ocupado(self, perfil_id: str) -> bool:
        return self.status(perfil_id).status in (Status.ABRINDO, Status.ABERTO)

    def reservar(self, perfil_id: str) -> None:
        with self._trava:
            atual = self._sessoes.get(perfil_id, Sessao(Status.FECHADO))
            if atual.status in (Status.ABRINDO, Status.ABERTO):
                raise PerfilJaAberto(perfil_id, atual.ws)
            self._sessoes[perfil_id] = Sessao(Status.ABRINDO)

    def marcar_aberto(self, perfil_id: str, ws: str) -> None:
        with self._trava:
            self._sessoes[perfil_id] = Sessao(Status.ABERTO, ws=ws)

    def marcar_erro(self, perfil_id: str, erro: str) -> None:
        with self._trava:
            self._sessoes[perfil_id] = Sessao(Status.ERRO, erro=erro)

    def liberar(self, perfil_id: str) -> None:
        with self._trava:
            self._sessoes.pop(perfil_id, None)
```

- [ ] **Passo 4: Rodar e ver passar**

Run: `.venv\Scripts\python -m pytest tests/test_estado.py -q`
Expected: `6 passed`

- [ ] **Passo 5: Commit**

```bash
git add multiperfil/estado.py tests/test_estado.py
git commit -m "feat: registro de perfis abertos com trava"
```

---

### Tarefa 4: `repositorio.py` — perfis em SQLite

**Arquivos:** criar `multiperfil/repositorio.py`, `tests/test_repositorio.py`

- [ ] **Passo 1: Testes que falham**

```python
import pytest

from multiperfil.proxy import Proxy
from multiperfil.repositorio import Perfil, PerfilExiste, PerfilInexistente, Repositorio, validar_id


def _perfil(pid: str = "canal-a") -> Perfil:
    return Perfil(
        id=pid,
        nome="Canal A",
        sistema="windows",
        proxy=Proxy("socks5", "h", 1080, "u", "p@ss"),
        config={"canvas:seed": 7},
        notas="",
    )


def test_criar_obter_listar(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    obtido = repo.obter("canal-a")
    assert obtido.proxy == Proxy("socks5", "h", 1080, "u", "p@ss")
    assert obtido.config == {"canvas:seed": 7}
    assert [p.id for p in repo.listar()] == ["canal-a"]


def test_persiste_entre_instancias(tmp_path):
    Repositorio(tmp_path / "p.db").criar(_perfil())
    assert Repositorio(tmp_path / "p.db").obter("canal-a").nome == "Canal A"


def test_criar_duplicado_falha(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    with pytest.raises(PerfilExiste):
        repo.criar(_perfil())


def test_obter_inexistente_falha(tmp_path):
    with pytest.raises(PerfilInexistente):
        Repositorio(tmp_path / "p.db").obter("nada")


def test_atualizar_nao_toca_no_config(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    repo.atualizar("canal-a", nome="Novo", proxy=Proxy("http", "x", 1), notas="n")
    p = repo.obter("canal-a")
    assert (p.nome, p.proxy, p.notas, p.config) == ("Novo", Proxy("http", "x", 1), "n", {"canvas:seed": 7})


def test_remover(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    repo.remover("canal-a")
    with pytest.raises(PerfilInexistente):
        repo.remover("canal-a")


@pytest.mark.parametrize("pid", ["", "A", "com espaço", "../x", "a" * 41])
def test_id_invalido(pid):
    with pytest.raises(ValueError):
        validar_id(pid)
```

- [ ] **Passo 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m pytest tests/test_repositorio.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Passo 3: Implementação**

```python
"""Perfis em SQLite. O id vira nome de arquivo e trecho de URL, por isso é restrito."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from multiperfil.fingerprint import Config
from multiperfil.proxy import Proxy, parse_proxy, url_completa

PADRAO_ID = re.compile(r"^[a-z0-9-]{1,40}$")
SISTEMAS: tuple[str, ...] = ("windows", "macos", "linux")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS perfis (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    sistema TEXT NOT NULL,
    proxy TEXT NOT NULL,
    config TEXT NOT NULL,
    notas TEXT NOT NULL,
    criado_em TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class Perfil:
    id: str
    nome: str
    sistema: str
    proxy: Proxy
    config: Config
    notas: str


class PerfilInexistente(KeyError):
    pass


class PerfilExiste(Exception):
    pass


def validar_id(perfil_id: str) -> str:
    if not PADRAO_ID.match(perfil_id):
        raise ValueError("id deve ter 1-40 caracteres: minúsculas, números e hífen")
    return perfil_id


def _de_linha(linha: sqlite3.Row) -> Perfil:
    return Perfil(
        id=linha["id"],
        nome=linha["nome"],
        sistema=linha["sistema"],
        proxy=parse_proxy(linha["proxy"]),
        config=json.loads(linha["config"]),
        notas=linha["notas"],
    )


class Repositorio:
    def __init__(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho = caminho
        with self._conectar() as con:
            con.execute(ESQUEMA)

    def _conectar(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._caminho)
        con.row_factory = sqlite3.Row
        return con

    def criar(self, perfil: Perfil) -> None:
        validar_id(perfil.id)
        if perfil.sistema not in SISTEMAS:
            raise ValueError(f"sistema deve ser um de {SISTEMAS}")
        agora = datetime.now(timezone.utc).isoformat()
        linha = (perfil.id, perfil.nome, perfil.sistema, url_completa(perfil.proxy),
                 json.dumps(perfil.config), perfil.notas, agora)
        try:
            with self._conectar() as con:
                con.execute("INSERT INTO perfis VALUES (?, ?, ?, ?, ?, ?, ?)", linha)
        except sqlite3.IntegrityError:
            raise PerfilExiste(perfil.id) from None

    def obter(self, perfil_id: str) -> Perfil:
        with self._conectar() as con:
            linha = con.execute("SELECT * FROM perfis WHERE id = ?", (perfil_id,)).fetchone()
        if linha is None:
            raise PerfilInexistente(perfil_id)
        return _de_linha(linha)

    def listar(self) -> list[Perfil]:
        with self._conectar() as con:
            linhas = con.execute("SELECT * FROM perfis ORDER BY nome").fetchall()
        return [_de_linha(linha) for linha in linhas]

    def atualizar(self, perfil_id: str, *, nome: str, proxy: Proxy, notas: str) -> None:
        with self._conectar() as con:
            cursor = con.execute(
                "UPDATE perfis SET nome = ?, proxy = ?, notas = ? WHERE id = ?",
                (nome, url_completa(proxy), notas, perfil_id),
            )
        if cursor.rowcount == 0:
            raise PerfilInexistente(perfil_id)

    def remover(self, perfil_id: str) -> None:
        with self._conectar() as con:
            cursor = con.execute("DELETE FROM perfis WHERE id = ?", (perfil_id,))
        if cursor.rowcount == 0:
            raise PerfilInexistente(perfil_id)
```

Nota: `with sqlite3.connect(...)` faz commit mas **não fecha** a conexão; aqui cada
conexão é curta e o coletor fecha. Se aparecer `database is locked` no Windows, trocar
por `contextlib.closing` — não antes de medir.

- [ ] **Passo 4: Rodar e ver passar**

Run: `.venv\Scripts\python -m pytest tests/test_repositorio.py -q`
Expected: `11 passed`

- [ ] **Passo 5: Commit**

```bash
git add multiperfil/repositorio.py tests/test_repositorio.py
git commit -m "feat: repositorio SQLite de perfis"
```

---

### Tarefa 5: `lancador.py` — subir e fechar o navegador

**Arquivos:** criar `multiperfil/lancador.py`, `tests/test_lancador.py`

- [ ] **Passo 1: Teste da parte pura (leitura do endpoint)**

```python
from multiperfil.lancador import achar_endpoint


def test_acha_endpoint_com_ansi():
    linha = "Websocket endpoint:\x1b[93m ws://localhost:51234/abc123 \x1b[0m\n"
    assert achar_endpoint(linha) == "ws://localhost:51234/abc123"


def test_linha_sem_endpoint():
    assert achar_endpoint("Launching server...\n") is None
```

- [ ] **Passo 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m pytest tests/test_lancador.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Passo 3: Implementação**

```python
"""Sobe um Camoufox por perfil como servidor Playwright e devolve o ws://.

Reproduz camoufox.server.launch_server (0.5.6), com uma diferença: o config sorteado
por launch_options é trocado pelo congelado do perfil (ver fingerprint.py).
"""

from __future__ import annotations

import base64
import logging
import queue
import re
import subprocess
import threading
import time
from pathlib import Path

import orjson
from camoufox.server import LAUNCH_SCRIPT, get_nodejs, to_camel_case_dict
from camoufox.utils import launch_options

from multiperfil.fingerprint import aplicar_congelado
from multiperfil.proxy import para_playwright
from multiperfil.repositorio import Perfil

log = logging.getLogger("multiperfil.lancador")

PADRAO_WS = re.compile(r"ws://\S+")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
PRAZO_ABRIR_S = 90
PRAZO_FECHAR_S = 15


class ErroLancamento(Exception):
    pass


def achar_endpoint(linha: str) -> str | None:
    achado = PADRAO_WS.search(ANSI.sub("", linha))
    return achado.group(0) if achado else None


def _opcoes(perfil: Perfil) -> dict:
    opcoes = launch_options(
        config=dict(perfil.config),
        headless=False,
        geoip=True,
        proxy=para_playwright(perfil.proxy),
        firefox_user_prefs={"network.proxy.socks_remote_dns": True},
        i_know_what_im_doing=True,
    )
    return aplicar_congelado(opcoes, perfil.config)


def _drenar(processo: subprocess.Popen, linhas: queue.Queue, perfil_id: str) -> None:
    assert processo.stdout is not None
    for linha in processo.stdout:
        linhas.put(linha)
        log.info("[%s] %s", perfil_id, ANSI.sub("", linha).rstrip())
    linhas.put(None)


def _esperar_endpoint(linhas: queue.Queue, perfil_id: str) -> str:
    limite = time.monotonic() + PRAZO_ABRIR_S
    while (restante := limite - time.monotonic()) > 0:
        try:
            linha = linhas.get(timeout=restante)
        except queue.Empty:
            break
        if linha is None:
            raise ErroLancamento(f"navegador do perfil {perfil_id} saiu antes de abrir")
        if ws := achar_endpoint(linha):
            return ws
    raise ErroLancamento(f"perfil {perfil_id} não abriu em {PRAZO_ABRIR_S}s")


class Lancador:
    def __init__(self) -> None:
        self._processos: dict[str, subprocess.Popen] = {}

    def abrir(self, perfil: Perfil) -> str:
        dados = orjson.dumps(to_camel_case_dict(_opcoes(perfil)))
        node = get_nodejs()
        pacote = Path(node).parent / "package"
        processo = subprocess.Popen(  # nosec - comando fixo, sem shell
            [node, str(LAUNCH_SCRIPT), str(pacote)],
            cwd=pacote, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        )
        assert processo.stdin is not None
        processo.stdin.write(base64.b64encode(dados).decode() + "\n")
        processo.stdin.flush()
        linhas: queue.Queue = queue.Queue()
        threading.Thread(target=_drenar, args=(processo, linhas, perfil.id), daemon=True).start()
        self._processos[perfil.id] = processo
        try:
            return _esperar_endpoint(linhas, perfil.id)
        except ErroLancamento:
            self.fechar(perfil.id)
            raise

    def vivo(self, perfil_id: str) -> bool:
        processo = self._processos.get(perfil_id)
        return processo is not None and processo.poll() is None

    def fechar(self, perfil_id: str) -> None:
        """Fechar o stdin pede ao Node que feche o navegador limpo; depois, força."""
        processo = self._processos.pop(perfil_id, None)
        if processo is None:
            return
        assert processo.stdin is not None
        if not processo.stdin.closed:
            processo.stdin.close()
        try:
            processo.wait(timeout=PRAZO_FECHAR_S)
        except subprocess.TimeoutExpired:
            log.warning("[%s] não fechou em %ss, encerrando à força", perfil_id, PRAZO_FECHAR_S)
            processo.kill()
            processo.wait()
```

- [ ] **Passo 4: Rodar e ver passar**

Run: `.venv\Scripts\python -m pytest -q`
Expected: todos passam (`40 passed`)

- [ ] **Passo 5: Commit**

```bash
git add multiperfil/lancador.py tests/test_lancador.py
git commit -m "feat: lancador do Camoufox com config congelado"
```

---

### Tarefa 6: PORTÃO — spike de login e estabilidade (manual, com Davi)

**Arquivo:** criar `prototipo/spike_login.py`

Este passo decide se o projeto continua como está. Nada da API é construído antes.

- [ ] **Passo 1: Script**

```python
"""Spike: o login Google sobrevive entre aberturas e o fingerprint não muda?

Uso:  set MULTIPERFIL_PROXY=socks5://usuario:senha@host:porta
      .venv\\Scripts\\python prototipo\\spike_login.py
Rodar DUAS vezes. Na primeira, fazer login à mão na janela e apertar Enter.
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path

from camoufox.ip import public_ip
from camoufox.geolocation import get_geolocation
from camoufox.utils import launch_options
from playwright.async_api import async_playwright

from multiperfil.fingerprint import gerar_congelado
from multiperfil.lancador import Lancador
from multiperfil.proxy import parse_proxy, testar
from multiperfil.repositorio import Perfil

PASTA = Path("dados/spike")
SONDA = """() => {
  const c = document.createElement('canvas'); const g = c.getContext('2d');
  g.font = '16px Arial'; g.fillText('MultiPerfil 🦊', 2, 20);
  return {ua: navigator.userAgent, tela: [screen.width, screen.height],
          janela: [innerWidth, innerHeight], fuso: Intl.DateTimeFormat().resolvedOptions().timeZone,
          idioma: navigator.language, canvas: c.toDataURL()};
}"""


def _perfil() -> Perfil:
    PASTA.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA / "config.json"
    if not arquivo.exists():
        arquivo.write_text(json.dumps(gerar_congelado("windows", launch_options)))
    proxy = parse_proxy(os.environ["MULTIPERFIL_PROXY"])
    print("proxy:", testar(proxy, public_ip, get_geolocation))
    return Perfil("spike", "Spike", "windows", proxy, json.loads(arquivo.read_text()), "")


async def main() -> None:
    perfil, lancador = _perfil(), Lancador()
    sessao = PASTA / "sessao.json"
    ws = lancador.abrir(perfil)
    print("ws:", ws)
    try:
        async with async_playwright() as pw:
            browser = await pw.firefox.connect(ws)
            ctx = await browser.new_context(
                no_viewport=True, storage_state=str(sessao) if sessao.exists() else None
            )
            page = await ctx.new_page()
            sonda = await page.evaluate(SONDA)
            sonda["canvas"] = hashlib.sha256(sonda["canvas"].encode()).hexdigest()[:16]
            print("fingerprint:", sonda)
            await page.goto("https://studio.youtube.com")
            input("Se pediu login, faça na janela. Depois aperte Enter aqui...")
            print("url final:", page.url)
            await ctx.storage_state(path=str(sessao))
            await browser.close()
    finally:
        lancador.fechar(perfil.id)


asyncio.run(main())
```

- [ ] **Passo 2: Primeira execução (Davi faz o login)**

Run: `.venv\Scripts\python prototipo\spike_login.py`
Esperado: proxy testado com IP/país; janela do Camoufox abre; `fuso` impresso bate com o
país do proxy; login do Google conclui sem bloqueio "navegador não seguro".

- [ ] **Passo 3: Segunda execução**

Esperado, TUDO precisa valer:
1. `url final` é `https://studio.youtube.com/...` sem passar por `accounts.google.com`.
2. `fingerprint` idêntico ao da primeira execução — incluindo o hash de `canvas`.
3. `janela` coerente com `tela` (janela ≤ tela), sem 1280×720 forçado.

- [ ] **Passo 4: Registrar o resultado** no fim deste plano (seção "Resultado do
  portão"), com os números medidos. Se 1 falhar, parar e voltar ao design: a sessão
  precisa de mais que cookies (ex.: IndexedDB) e o `storage_state` não basta.

- [ ] **Passo 5: Commit**

```bash
git add prototipo/spike_login.py docs/superpowers/plans/2026-09-25-multiperfil-sidecar.md
git commit -m "test: spike de login e estabilidade do fingerprint"
```

---

### Tarefa 7: `api.py` — FastAPI

**Arquivos:** criar `multiperfil/api.py`, `tests/test_api.py`

- [ ] **Passo 1: Testes que falham** (lançador e teste de proxy falsos — sem rede)

```python
import pytest
from fastapi.testclient import TestClient

from multiperfil.api import Dependencias, criar_app
from multiperfil.estado import Registro
from multiperfil.proxy import ErroProxy, ResultadoProxy
from multiperfil.repositorio import Repositorio


class LancadorFalso:
    def __init__(self) -> None:
        self.abertos: set[str] = set()

    def abrir(self, perfil) -> str:
        self.abertos.add(perfil.id)
        return f"ws://localhost:1/{perfil.id}"

    def vivo(self, perfil_id: str) -> bool:
        return perfil_id in self.abertos

    def fechar(self, perfil_id: str) -> None:
        self.abertos.discard(perfil_id)


def _proxy_ok(proxy):
    return ResultadoProxy("5.6.7.8", "BR", "America/Sao_Paulo", 120)


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
            pasta_sessoes=tmp_path / "sessoes",
            gerar_config=lambda sistema: {"canvas:seed": 7},
            testar_proxy=testar,
        )
        return TestClient(criar_app(deps)), lancador, deps
    return _montar


NOVO = {"id": "canal-a", "nome": "Canal A", "sistema": "windows",
        "proxy": "http://u:segredo@h:1", "notas": ""}


def test_criar_e_listar_sem_vazar_senha(montar):
    cliente, _, _ = montar()
    assert cliente.post("/perfis", json=NOVO).status_code == 201
    lista = cliente.get("/perfis").json()
    assert lista[0]["proxy"] == "http://u:***@h:1"
    assert "segredo" not in cliente.get("/perfis").text


def test_criar_duplicado_409_e_proxy_invalido_422(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    assert cliente.post("/perfis", json=NOVO).status_code == 409
    assert cliente.post("/perfis", json={**NOVO, "id": "b", "proxy": "lixo"}).status_code == 422


def test_abrir_devolve_ws_e_caminho_da_sessao(montar):
    cliente, _, deps = montar()
    cliente.post("/perfis", json=NOVO)
    r = cliente.post("/perfis/canal-a/abrir")
    assert r.status_code == 200
    assert r.json() == {
        "ws": "ws://localhost:1/canal-a",
        "storage_state": str(deps.pasta_sessoes / "canal-a.json"),
        "sessao_existe": False,
    }
    assert cliente.get("/perfis/canal-a/status").json()["status"] == "aberto"


def test_abrir_duas_vezes_409_com_ws(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    r = cliente.post("/perfis/canal-a/abrir")
    assert r.status_code == 409
    assert r.json()["detail"]["ws"] == "ws://localhost:1/canal-a"


def test_proxy_morto_nao_abre(montar):
    cliente, lancador, _ = montar(testar=_proxy_morto)
    cliente.post("/perfis", json=NOVO)
    r = cliente.post("/perfis/canal-a/abrir")
    assert r.status_code == 502
    assert lancador.abertos == set()
    assert cliente.get("/perfis/canal-a/status").json()["status"] == "fechado"


def test_processo_que_morreu_vira_erro(montar):
    cliente, lancador, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    lancador.abertos.clear()
    corpo = cliente.get("/perfis/canal-a/status").json()
    assert corpo["status"] == "erro"
    assert "terminou" in corpo["erro"]


def test_fechar_e_editar_bloqueado_enquanto_aberto(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    edicao = {"nome": "X", "proxy": "http://h:2", "notas": ""}
    assert cliente.patch("/perfis/canal-a", json=edicao).status_code == 409
    assert cliente.delete("/perfis/canal-a").status_code == 409
    assert cliente.post("/perfis/canal-a/fechar").json() == {"status": "fechado"}
    assert cliente.patch("/perfis/canal-a", json=edicao).status_code == 200


def test_remover_apaga_sessao(montar):
    cliente, _, deps = montar()
    cliente.post("/perfis", json=NOVO)
    deps.pasta_sessoes.mkdir(parents=True)
    (deps.pasta_sessoes / "canal-a.json").write_text("{}")
    assert cliente.delete("/perfis/canal-a").status_code == 204
    assert not (deps.pasta_sessoes / "canal-a.json").exists()


def test_perfil_inexistente_404(montar):
    cliente, _, _ = montar()
    assert cliente.post("/perfis/nada/abrir").status_code == 404
```

- [ ] **Passo 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m pytest tests/test_api.py -q`
Expected: FAIL com `ModuleNotFoundError`

- [ ] **Passo 3: Implementação**

```python
"""API local. Serve a janela Tauri e os scripts — os dois são só clientes disto."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from multiperfil.estado import PerfilJaAberto, Registro, Status
from multiperfil.fingerprint import Config
from multiperfil.proxy import ErroProxy, Proxy, ResultadoProxy, descrever, parse_proxy
from multiperfil.repositorio import Perfil, PerfilExiste, PerfilInexistente, Repositorio


class LancadorProto(Protocol):
    def abrir(self, perfil: Perfil) -> str: ...
    def vivo(self, perfil_id: str) -> bool: ...
    def fechar(self, perfil_id: str) -> None: ...


@dataclass(frozen=True)
class Dependencias:
    repo: Repositorio
    lancador: LancadorProto
    registro: Registro
    pasta_sessoes: Path
    gerar_config: Callable[[str], Config]
    testar_proxy: Callable[[Proxy], ResultadoProxy]


class NovoPerfil(BaseModel):
    id: str
    nome: str
    sistema: str
    proxy: str
    notas: str = ""


class EdicaoPerfil(BaseModel):
    nome: str
    proxy: str
    notas: str = ""


def _saida(perfil: Perfil, registro: Registro) -> dict:
    return {"id": perfil.id, "nome": perfil.nome, "sistema": perfil.sistema,
            "proxy": descrever(perfil.proxy), "notas": perfil.notas,
            "status": registro.status(perfil.id).status}


def _exigir_fechado(deps: Dependencias, perfil_id: str) -> None:
    if deps.registro.ocupado(perfil_id):
        raise HTTPException(409, "feche o perfil antes de editar ou remover")


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
        return [_saida(p, deps.registro) for p in deps.repo.listar()]

    @app.post("/perfis", status_code=201)
    def criar(novo: NovoPerfil) -> dict:
        proxy = parse_proxy(novo.proxy)
        perfil = Perfil(novo.id, novo.nome, novo.sistema, proxy,
                        deps.gerar_config(novo.sistema), novo.notas)
        try:
            deps.repo.criar(perfil)
        except PerfilExiste:
            raise HTTPException(409, f"perfil {novo.id} já existe") from None
        return _saida(perfil, deps.registro)

    @app.patch("/perfis/{perfil_id}")
    def editar(perfil_id: str, edicao: EdicaoPerfil) -> dict:
        _exigir_fechado(deps, perfil_id)
        deps.repo.atualizar(perfil_id, nome=edicao.nome,
                            proxy=parse_proxy(edicao.proxy), notas=edicao.notas)
        return _saida(deps.repo.obter(perfil_id), deps.registro)

    @app.delete("/perfis/{perfil_id}", status_code=204)
    def remover(perfil_id: str) -> Response:
        _exigir_fechado(deps, perfil_id)
        deps.repo.remover(perfil_id)
        (deps.pasta_sessoes / f"{perfil_id}.json").unlink(missing_ok=True)
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
        try:
            deps.registro.reservar(perfil_id)
        except PerfilJaAberto as erro:
            raise HTTPException(409, {"erro": str(erro), "ws": erro.ws}) from None
        try:
            deps.testar_proxy(perfil.proxy)
            ws = deps.lancador.abrir(perfil)
        except Exception as erro:
            deps.registro.liberar(perfil_id)
            status = 502 if isinstance(erro, ErroProxy) else 500
            raise HTTPException(status, str(erro)) from None
        deps.registro.marcar_aberto(perfil_id, ws)
        sessao = deps.pasta_sessoes / f"{perfil_id}.json"
        deps.pasta_sessoes.mkdir(parents=True, exist_ok=True)
        return {"ws": ws, "storage_state": str(sessao), "sessao_existe": sessao.exists()}

    @app.post("/perfis/{perfil_id}/fechar")
    def fechar(perfil_id: str) -> dict:
        deps.repo.obter(perfil_id)
        deps.lancador.fechar(perfil_id)
        deps.registro.liberar(perfil_id)
        return {"status": Status.FECHADO}

    @app.get("/perfis/{perfil_id}/status")
    def status(perfil_id: str) -> dict:
        deps.repo.obter(perfil_id)
        sessao = deps.registro.status(perfil_id)
        if sessao.status is Status.ABERTO and not deps.lancador.vivo(perfil_id):
            deps.registro.marcar_erro(perfil_id, "o processo do navegador terminou sozinho")
            sessao = deps.registro.status(perfil_id)
        return {"status": sessao.status, "ws": sessao.ws, "erro": sessao.erro}
```

Nota: o `except Exception` em `abrir` não engole nada — libera a trava e relança como
HTTP com a mensagem; sem ele, um erro de lançamento deixaria o perfil preso em `abrindo`.
A mensagem do `ErroLancamento` não contém proxy; a do `ErroProxy` já vem mascarada.

- [ ] **Passo 4: Rodar e ver passar**

Run: `.venv\Scripts\python -m pytest -q`
Expected: todos passam (`49 passed`)

- [ ] **Passo 5: Commit**

```bash
git add multiperfil/api.py tests/test_api.py
git commit -m "feat: API local de perfis"
```

---

### Tarefa 8: `__main__.py` — servidor real

**Arquivo:** criar `multiperfil/__main__.py`

- [ ] **Passo 1: Implementação**

```python
"""`python -m multiperfil` — sobe a API em 127.0.0.1:8800 com as dependências reais."""

import logging
import os
from pathlib import Path

import uvicorn
from camoufox.geolocation import get_geolocation
from camoufox.ip import public_ip
from camoufox.utils import launch_options

from multiperfil.api import Dependencias, criar_app
from multiperfil.estado import Registro
from multiperfil.fingerprint import gerar_congelado
from multiperfil.lancador import Lancador
from multiperfil.proxy import testar
from multiperfil.repositorio import Repositorio

PORTA = 8800


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    dados = Path(os.environ.get("MULTIPERFIL_DADOS", "dados"))
    deps = Dependencias(
        repo=Repositorio(dados / "perfis.db"),
        lancador=Lancador(),
        registro=Registro(),
        pasta_sessoes=dados / "sessoes",
        gerar_config=lambda sistema: gerar_congelado(sistema, launch_options),
        testar_proxy=lambda proxy: testar(proxy, public_ip, get_geolocation),
    )
    uvicorn.run(criar_app(deps), host="127.0.0.1", port=PORTA)


if __name__ == "__main__":
    main()
```

- [ ] **Passo 2: Verificação ao vivo**

Run (terminal 1): `.venv\Scripts\python -m multiperfil`
Run (terminal 2):
```bash
curl -s -X POST localhost:8800/perfis -H "content-type: application/json" -d "{\"id\":\"teste\",\"nome\":\"Teste\",\"sistema\":\"windows\",\"proxy\":\"<proxy do Davi>\"}"
curl -s -X POST localhost:8800/perfis/teste/abrir
curl -s localhost:8800/perfis/teste/status
curl -s -X POST localhost:8800/perfis/teste/fechar
```
Expected: 201 sem senha na resposta; `abrir` devolve `ws://localhost:...`; janela do
Camoufox abre; status `aberto`; `fechar` fecha a janela; senha ausente do log do terminal 1.

- [ ] **Passo 3: Commit**

```bash
git add multiperfil/__main__.py
git commit -m "feat: servidor real do sidecar"
```

---

### Tarefa 9: `cliente.py` — helper para os scripts

**Arquivo:** criar `multiperfil/cliente.py`

- [ ] **Passo 1: Implementação**

```python
"""Uso num script de publicação:

    async with async_playwright() as pw:
        async with abrir_perfil("canal-a", pw) as ctx:
            page = await ctx.new_page()
            ...

A sessão (cookies + localStorage) é salva só quando o bloco termina sem erro.
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
            browser = await pw.firefox.connect(dados["ws"])
            estado = dados["storage_state"] if dados["sessao_existe"] else None
            # no_viewport: sem isso o Playwright força 1280x720 e contradiz a tela spoofada.
            ctx = await browser.new_context(no_viewport=True, storage_state=estado)
            yield ctx
            await ctx.storage_state(path=dados["storage_state"])
            await browser.close()
        finally:
            _checar(await http.post(f"/perfis/{perfil_id}/fechar"))
```

- [ ] **Passo 2: Script de verificação** `prototipo/teste_cliente.py`

```python
"""Com `python -m multiperfil` rodando e o perfil `teste` criado."""

import asyncio

from playwright.async_api import async_playwright

from multiperfil.cliente import abrir_perfil


async def main() -> None:
    async with async_playwright() as pw:
        async with abrir_perfil("teste", pw) as ctx:
            page = await ctx.new_page()
            await page.goto("https://ipinfo.io/json")
            print(await page.inner_text("body"))


asyncio.run(main())
```

Run: `.venv\Scripts\python prototipo\teste_cliente.py`
Expected: JSON do ipinfo com o IP e país **do proxy**; janela fecha no fim;
`dados/sessoes/teste.json` existe.

- [ ] **Passo 3: Commit**

```bash
git add multiperfil/cliente.py prototipo/teste_cliente.py
git commit -m "feat: helper abrir_perfil para scripts Playwright"
```

---

### Tarefa 10: Rodar um script real de publicação (manual, com Davi)

- [ ] **Passo 1:** Davi indica o script de publicação no YouTube que usa hoje.
- [ ] **Passo 2:** trocar só a abertura do navegador por `abrir_perfil(...)`; o resto
  do script fica igual.
- [ ] **Passo 3:** publicar um vídeo **não listado** de teste. Anotar abaixo cada
  seletor/fluxo que quebrou no Firefox e o conserto.
- [ ] **Passo 4: Commit** das anotações neste plano.

---

## Resultado do portão (preencher na Tarefa 6)

Medido em 2026-09-25 com proxy HTTP na Eslováquia (3,6 Mbit/s; direto: 12 Mbit/s).

- Login persistiu na 2ª abertura: **SIM** — com `storage_state`, `studio.youtube.com`
  abriu direto no canal, sem `accounts.google.com`. O Google aceitou o login no Camoufox.
- Fingerprint idêntico entre aberturas: **não medido** — as execuções seguintes travaram.
- Fuso × país do proxy: **FALHOU com só o config** (vazou `America/Sao_Paulo`); passa
  (`Europe/Bratislava`) com `timezone_id` no `new_context`, como
  `camoufox.async_api.AsyncNewContext` faz. Idioma `sk-SK` já saía certo.
- Janela × tela: 1584×795 dentro de 1600×900 — ok.
- **Instabilidade do modo servidor:** `new_context()`/`new_page()` pela conexão `ws`
  travam de forma intermitente (mesma variante passa numa rodada e trava na outra).
  O fechamento às vezes passa de 15 s e deixa `camoufox.exe` órfão, mesmo com
  `taskkill /T`. Tempos típicos quando não trava: subir 9–16 s, sessão 10 s,
  1ª aba 6 s, Studio 11–30 s (cache sempre frio), fechar 6–11 s.
- Decisão pendente: pesquisa de alternativa ao `launch_server` (experimental).
