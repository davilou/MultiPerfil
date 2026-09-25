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
