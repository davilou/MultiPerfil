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
