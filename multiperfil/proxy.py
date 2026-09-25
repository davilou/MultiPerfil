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
