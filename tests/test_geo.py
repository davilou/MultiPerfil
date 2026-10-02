import pytest

from multiperfil import geo


class _Leitor:
    def __init__(self, registros):
        self.registros = registros

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, ip):
        return self.registros.get(ip)


@pytest.fixture
def banco(tmp_path, monkeypatch):
    arquivo = tmp_path / "geolite2-ipv4.mmdb"
    arquivo.write_bytes(b"x")
    monkeypatch.setattr(geo.camoufox_geo, "get_mmdb_path", lambda versao: arquivo)
    registros = {"196.44.125.10": {"country_code": "SK", "timezone": "Europe/Bratislava"}}
    monkeypatch.setattr(geo.maxminddb, "open_database", lambda caminho: _Leitor(registros))
    monkeypatch.setattr(geo.camoufox_geo, "download_mmdb",
                        lambda: pytest.fail("com o banco no disco não pode baixar"))
    return arquivo


def test_le_o_banco_local_sem_baixar(banco):
    assert geo.localizar("196.44.125.10") == ("SK", "Europe/Bratislava")


def test_ip_fora_do_banco_falha_claro(banco):
    with pytest.raises(geo.ErroGeo, match="1.2.3.4"):
        geo.localizar("1.2.3.4")


def test_sem_banco_pede_download(tmp_path, monkeypatch):
    baixou = []
    arquivo = tmp_path / "nao-existe.mmdb"
    monkeypatch.setattr(geo.camoufox_geo, "get_mmdb_path", lambda versao: arquivo)
    monkeypatch.setattr(geo.camoufox_geo, "download_mmdb", lambda: baixou.append(1))
    monkeypatch.setattr(geo.maxminddb, "open_database",
                        lambda caminho: _Leitor({"8.8.8.8": {"country_code": "US", "timezone": "America/Chicago"}}))
    assert geo.localizar("8.8.8.8") == ("US", "America/Chicago")
    assert baixou == [1]
