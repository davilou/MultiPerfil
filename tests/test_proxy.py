import pytest

from multiperfil.proxy import (
    ErroProxy,
    Proxy,
    descrever,
    para_playwright,
    para_requests,
    parse_proxy,
    url_completa,
)
from multiperfil.proxy import testar as verificar_proxy


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


def test_repr_e_str_nao_vazam_senha():
    p = Proxy("socks5", "h", 1, "ana", "segredo")
    assert "segredo" not in repr(p)
    assert "segredo" not in str(p)
    assert repr(p) == "Proxy(socks5://ana:***@h:1)"


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

    r = verificar_proxy(Proxy("http", "h", 1), buscar_ip=lambda url: "5.6.7.8", geolocalizar=lambda ip: Geo)
    assert (r.ip, r.pais, r.fuso) == ("5.6.7.8", "BR", "America/Sao_Paulo")
    assert r.latencia_ms >= 0


def test_testar_falha_sem_vazar_senha():
    def quebra(url):
        raise RuntimeError(f"falhou em {url}")

    with pytest.raises(ErroProxy) as erro:
        verificar_proxy(Proxy("http", "h", 1, "u", "segredo"), buscar_ip=quebra, geolocalizar=None)
    assert "segredo" not in str(erro.value)
    assert "http://u:***@h:1" in str(erro.value)


def test_testar_falha_sem_vazar_senha_crua_na_mensagem():
    def quebra(url):
        raise RuntimeError("auth falhou, pass segredo")

    with pytest.raises(ErroProxy) as erro:
        verificar_proxy(Proxy("http", "h", 1, "u", "segredo"), buscar_ip=quebra, geolocalizar=None)
    assert "segredo" not in str(erro.value)
