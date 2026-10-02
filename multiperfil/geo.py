"""IP de saída → país e fuso, lendo direto o banco GeoLite que o camoufox já baixou.

`camoufox.geolocation.get_geolocation` rebaixa o banco quando o acha velho (>30 dias)
ou ausente, e em 2026-10-02 esse download falhou (404 no endereço do GitHub) dentro
do app — todo perfil com proxy deixou de abrir. Banco de algumas semanas erra pouco
em país e fuso; por isso o arquivo local é a fonte, e o download do camoufox só entra
quando não existe arquivo nenhum.
"""

from __future__ import annotations

import logging

import maxminddb
from camoufox import geolocation as camoufox_geo

log = logging.getLogger("multiperfil.geo")


class ErroGeo(Exception):
    pass


def localizar(ip: str) -> tuple[str | None, str]:
    """(país ISO-2 ou None, fuso IANA) do IP."""
    banco = camoufox_geo.get_mmdb_path("ipv6" if ":" in ip else "ipv4")
    if not banco.exists():
        log.warning("banco de geolocalização ausente em %s; baixando", banco)
        camoufox_geo.download_mmdb()
    with maxminddb.open_database(str(banco)) as leitor:
        registro = leitor.get(ip)
    if not registro or not registro.get("timezone"):
        raise ErroGeo(f"o IP {ip} não está no banco de geolocalização")
    return registro.get("country_code") or None, registro["timezone"]
