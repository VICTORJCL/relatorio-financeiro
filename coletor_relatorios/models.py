import os
from datetime import datetime, timedelta, timezone
from functools import partial

import peewee as pw
from dotenv import load_dotenv

FUSO_BRASILIA = timezone(timedelta(hours=-3))

inteiro = partial(pw.IntegerField, null=True)
texto = partial(pw.TextField, null=True)
dinheiro = partial(pw.DecimalField, max_digits=12, decimal_places=2, null=True)
percentual = partial(pw.DecimalField, max_digits=6, decimal_places=2, null=True)

def conectar_robtom() -> pw.PostgresqlDatabase:
    load_dotenv()
    return pw.PostgresqlDatabase(
        os.environ["ROBTOM_DB"], host=os.environ["ROBTOM_HOST"],
        port=int(os.environ["ROBTOM_PORT"]), user=os.environ["ROBTOM_USER"],
        password=os.environ["ROBTOM_PASSWORD"], connect_timeout=15)


class DataHoraComFuso(pw.DateTimeField):
    field_type = "TIMESTAMPTZ"


class Raw(pw.Model):
    data = pw.DateField(index=True)
    carregado_em = DataHoraComFuso(default=lambda: datetime.now(FUSO_BRASILIA))

    class Meta:
        schema = "public"


class Desconto(Raw):
    """Z000 — Detalhamento de descontos concedidos."""

    loja = inteiro()
    pdv = inteiro()
    documento = inteiro()
    operador = inteiro()
    supervisor = inteiro()
    nome_supervisor = texto()
    produto = texto()
    descricao = texto()
    venda = dinheiro()
    desconto = dinheiro()
    perc_desc = percentual()
    cod_motivo = inteiro()
    descr_motivo = texto()
    promocao = texto()
    descr_promocao = texto()

    class Meta:
        table_name = "raw_descontos"


class CancelamentoCupom(Raw):
    """Z002 — Cancelamentos de cupons."""

    loja = inteiro()
    pdv = inteiro()
    cupom_cancelado = inteiro()
    venda = dinheiro()
    cancelamento = dinheiro()
    motivo = inteiro()
    descr_motivo = texto()
    operador = inteiro()
    nome_operador = texto()
    supervisor = inteiro()
    nome_supervisor = texto()

    class Meta:
        table_name = "raw_cancelamentos_cupons"


class CancelamentoItem(Raw):
    """Z003 — Cancelamentos de itens."""

    loja = inteiro()
    pdv = inteiro()
    cupom = inteiro()
    mercadoria = texto()
    descricao = texto()
    valor = dinheiro()
    motivo = inteiro()
    descr_motivo = texto()
    operador = inteiro()
    nome_operador = texto()
    supervisor = inteiro()
    nome_supervisor = texto()

    class Meta:
        table_name = "raw_cancelamento_itens"


MODELOS: tuple[type[Raw], ...] = (Desconto, CancelamentoCupom, CancelamentoItem)
