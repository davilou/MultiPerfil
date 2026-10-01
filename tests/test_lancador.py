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


def test_argumentos_sem_proxy_nem_fuso_usam_os_do_sistema():
    perfil = Perfil("a", "A", "windows", None, 7, "pt-BR", "")
    args = argumentos_chrome(Path("c.exe"), Path("p"), perfil, None, None, 9222)
    assert not any(a.startswith(("--proxy-server", "--timezone")) for a in args)
    assert "--fingerprint=7" in args and "--remote-debugging-port=9222" in args


def test_lancador_sem_proxy_nao_sobe_repassador(tmp_path):
    from multiperfil.lancador import Lancador

    class RepassadorQueNaoPodeSerUsado:
        def abrir(self, perfil_id, proxy):
            raise AssertionError("perfil sem proxy não usa repassador")

        def fechar(self, perfil_id):
            pass

    falso = tmp_path / "falso.exe"
    falso.write_bytes(b"nao e um executavel")  # passa do "existe?" e falha no Popen
    lancador = Lancador(falso, tmp_path, RepassadorQueNaoPodeSerUsado())
    perfil = Perfil("a", "A", "windows", None, 7, "pt-BR", "")
    import pytest
    with pytest.raises(OSError):  # AssertionError aqui = repassador foi chamado
        lancador.abrir(perfil, None)
