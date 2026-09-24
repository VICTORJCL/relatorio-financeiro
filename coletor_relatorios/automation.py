"""Login no Zanthus e download dos relatórios em CSV."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from coletor_relatorios.models import CancelamentoCupom, CancelamentoItem, Desconto, Raw

NAVEGADOR_SEM_JANELA = True
TIMEOUT_EM_MILISSEGUNDOS = 10_000
FORMATO_DA_DATA_NO_ZANTHUS = "%d-%m-%Y"

SELETOR_USUARIO = "#USUARIO"
SELETOR_SENHA = "#SENHA"
BOTAO_ENTRAR = "Entrar"
SELETOR_TODAS_AS_LOJAS = ".control__indicator"
SELETOR_EXPORTAR = "#PRINTNEW"
POSICAO_DO_EXPORTAR_CSV = 4  # o Zanthus repete o id #PRINTNEW em todos os botões de exportação


@dataclass(frozen=True)
class RelatorioZanthus:
    link: str
    campo_data_inicial: str
    campo_data_final: str
    modelo: type[Raw]


RELATORIOS_ZANTHUS = (
    RelatorioZanthus("Z000-Detalhamento de descontos concedidos - correção",
                     'input[name="d.m00af_INI"]', 'input[name="d.m00af_END"]', Desconto),
    RelatorioZanthus("Z002-Cancelamentos de cupons",
                     "#dta_movimento_INI", "#dta_movimento_END", CancelamentoCupom),
    RelatorioZanthus("Z003-Cancelamentos de itens",
                     "#dta_movimento_INI", "#dta_movimento_END", CancelamentoItem),
)


@contextmanager
def abrir_navegador() -> Iterator[Page]:
    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(headless=NAVEGADOR_SEM_JANELA)
        try:
            page = navegador.new_page()
            page.set_default_timeout(TIMEOUT_EM_MILISSEGUNDOS)
            yield page
        finally:
            navegador.close()


class Automation:
    def __init__(self, page: Page, url: str, usuario: str, senha: str) -> None:
        self.page = page
        self.url = url
        self.usuario = usuario
        self.senha = senha

    def entrar(self) -> None:
        self.page.goto(self.url)
        self.page.fill(SELETOR_USUARIO, self.usuario)
        self.page.fill(SELETOR_SENHA, self.senha)
        self.page.get_by_role("button", name=BOTAO_ENTRAR).click()
        self.page.wait_for_timeout(5000)
        self.page.goto(self.url)
        self.page.wait_for_timeout(3000)

    def baixar(self, relatorio: RelatorioZanthus, dia: date, destino: Path) -> None:
        self.page.get_by_role("link", name=relatorio.link).click()
        self.page.locator(SELETOR_TODAS_AS_LOJAS).first.click()
        for seletor in (relatorio.campo_data_inicial, relatorio.campo_data_final):
            campo = self.page.locator(seletor)
            campo.fill(dia.strftime(FORMATO_DA_DATA_NO_ZANTHUS))
            campo.press("Tab")  # com Enter, o calendário do campo troca a data digitada pela de hoje
        with self.page.expect_download() as download:
            with self.page.expect_popup():
                self.page.locator(SELETOR_EXPORTAR).nth(POSICAO_DO_EXPORTAR_CSV).click()
        download.value.save_as(destino)
