"""Pings de entrada e saída no monitor Palantir.

A falha não é avisada: o Palantir a detecta pela falta do ping de saída.
"""

import logging

import requests

TIMEOUT_EM_SEGUNDOS = 3

logger = logging.getLogger("automation")


class Palantir:
    """Nunca levanta exceção: monitor fora do ar não pode derrubar a execução que ele monitora."""

    def __init__(self, job: str, url_base: str) -> None:
        self.url_do_job = f"{url_base}/ping/{job}"

    def pingar_entrada(self) -> None:
        self._pingar(f"{self.url_do_job}/start")

    def pingar_saida(self) -> None:
        self._pingar(self.url_do_job)

    def _pingar(self, url: str) -> None:
        try:
            resposta = requests.post(url, timeout=TIMEOUT_EM_SEGUNDOS)
            resposta.raise_for_status()
            logger.info("Palantir [%s] %s", resposta.status_code, url)
        except requests.ConnectionError:
            logger.warning("Palantir fora do ar, ping não entregue: %s", url)
        except requests.RequestException as erro:
            logger.warning("Palantir recusou o ping %s: %s", url, erro)
