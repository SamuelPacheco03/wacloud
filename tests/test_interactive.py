"""Tests de mensajes interactivos de lista y de Flow, en ambos sentidos."""

import pytest

from tests.factories import accepted_handler, make_messages_client
from wacloud import parse_webhook
from wacloud.flows import FlowAction, FlowMode
from wacloud.messages import builders

# --- Listas ------------------------------------------------------------------


def _sections(count: int = 1, rows_each: int = 1):
    return [
        builders.list_section(
            [builders.list_row(f"s{s}r{r}", f"Fila {s}-{r}") for r in range(rows_each)],
            title=f"Sección {s}",
        )
        for s in range(count)
    ]


def test_list_payload_shape():
    payload = builders.build_interactive_list(
        "573001112233",
        "¿Qué envío prefieres?",
        "Opciones",
        [
            builders.list_section(
                [
                    builders.list_row("exp", "Express", description="1-2 días"),
                    builders.list_row("std", "Estándar"),
                ],
                title="Rápido",
            )
        ],
        header="Envío",
        footer="Lucky Shrub",
    )
    interactive = payload["interactive"]
    assert interactive["type"] == "list"
    assert interactive["action"]["button"] == "Opciones"
    assert interactive["action"]["sections"][0]["rows"][0] == {
        "id": "exp",
        "title": "Express",
        "description": "1-2 días",
    }
    assert interactive["footer"] == {"text": "Lucky Shrub"}


def test_list_header_is_text_only():
    """La lista es el único interactivo cuya cabecera no admite medios."""
    payload = builders.build_interactive_list(
        "573001112233", "cuerpo", "Ver", _sections(), header="Título"
    )
    assert payload["interactive"]["header"] == {"type": "text", "text": "Título"}


def test_row_limit_is_ten_across_all_sections_not_per_section():
    """El error más común: 10 filas en total, no 10 por sección."""
    # 3 secciones de 4 filas = 12 filas en total.
    with pytest.raises(ValueError, match="10 filas en total"):
        builders.build_interactive_list(
            "573001112233", "cuerpo", "Ver", _sections(count=3, rows_each=4)
        )


def test_ten_rows_spread_across_sections_is_valid():
    payload = builders.build_interactive_list(
        "573001112233", "cuerpo", "Ver", _sections(count=5, rows_each=2)
    )
    total = sum(len(s["rows"]) for s in payload["interactive"]["action"]["sections"])
    assert total == 10


def test_list_rejects_more_than_ten_sections():
    with pytest.raises(ValueError, match="máximo 10"):
        builders.build_interactive_list("573001112233", "cuerpo", "Ver", _sections(count=11))


def test_multiple_sections_require_titles():
    sections = [
        builders.list_section([builders.list_row("a", "A")], title="Con título"),
        builders.list_section([builders.list_row("b", "B")]),
    ]
    with pytest.raises(ValueError, match="todas necesitan 'title'"):
        builders.build_interactive_list("573001112233", "cuerpo", "Ver", sections)


def test_single_section_needs_no_title():
    sections = [builders.list_section([builders.list_row("a", "A")])]
    payload = builders.build_interactive_list("573001112233", "cuerpo", "Ver", sections)
    assert "title" not in payload["interactive"]["action"]["sections"][0]


def test_duplicate_row_ids_are_rejected():
    """Dos filas con el mismo id harían indistinguible la respuesta."""
    sections = [
        builders.list_section(
            [builders.list_row("mismo", "A"), builders.list_row("mismo", "B")]
        )
    ]
    with pytest.raises(ValueError, match="repetido"):
        builders.build_interactive_list("573001112233", "cuerpo", "Ver", sections)


def test_list_requires_sections():
    with pytest.raises(ValueError, match="al menos una sección"):
        builders.build_interactive_list("573001112233", "cuerpo", "Ver", [])


def test_section_requires_rows():
    with pytest.raises(ValueError, match="al menos una fila"):
        builders.list_section([])


def test_list_button_label_limit():
    with pytest.raises(ValueError, match="máximo 20"):
        builders.build_interactive_list("573001112233", "cuerpo", "x" * 21, _sections())


def test_list_button_is_required():
    with pytest.raises(ValueError, match="etiqueta del botón es obligatoria"):
        builders.build_interactive_list("573001112233", "cuerpo", "  ", _sections())


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"row_id": "x" * 201, "title": "A"}, "máximo 200"),
        ({"row_id": "a", "title": "x" * 25}, "máximo 24"),
        ({"row_id": "a", "title": "A", "description": "x" * 73}, "máximo 72"),
    ],
)
def test_row_field_limits(kwargs, expected):
    with pytest.raises(ValueError, match=expected):
        builders.list_row(**kwargs)


def test_section_title_limit():
    with pytest.raises(ValueError, match="máximo 24"):
        builders.list_section([builders.list_row("a", "A")], title="x" * 25)


def test_row_requires_id_and_title():
    with pytest.raises(ValueError, match="id de la fila"):
        builders.list_row("", "A")
    with pytest.raises(ValueError, match="título de la fila"):
        builders.list_row("a", "")


# --- Flow --------------------------------------------------------------------


def test_flow_payload_shape():
    payload = builders.build_interactive_flow(
        "573001112233",
        "Reserva tu cita",
        "Reservar",
        flow_token="T-42",
        flow_id="123456",
        screen="APPOINTMENT",
        data={"producto": "corte"},
    )
    parameters = payload["interactive"]["action"]["parameters"]
    assert payload["interactive"]["type"] == "flow"
    assert payload["interactive"]["action"]["name"] == "flow"
    assert parameters["flow_message_version"] == "3"
    assert parameters["flow_id"] == "123456"
    assert parameters["flow_token"] == "T-42"
    assert parameters["flow_action"] == "navigate"
    assert parameters["mode"] == "published"
    assert parameters["flow_action_payload"] == {
        "screen": "APPOINTMENT",
        "data": {"producto": "corte"},
    }


def test_flow_message_version_is_always_three():
    payload = builders.build_interactive_flow(
        "573001112233", "cuerpo", "Ir", flow_token="T", flow_id="1"
    )
    version = payload["interactive"]["action"]["parameters"]["flow_message_version"]
    assert version == "3"


def test_flow_requires_exactly_one_reference():
    with pytest.raises(ValueError, match="exactamente uno"):
        builders.build_interactive_flow("573001112233", "cuerpo", "Ir", flow_token="T")
    with pytest.raises(ValueError, match="exactamente uno"):
        builders.build_interactive_flow(
            "573001112233", "cuerpo", "Ir", flow_token="T", flow_id="1", flow_name="x"
        )


def test_flow_requires_a_token():
    """Sin token no hay forma de correlacionar la respuesta: Meta no manda el flow_id."""
    with pytest.raises(ValueError, match="flow_token es obligatorio"):
        builders.build_interactive_flow(
            "573001112233", "cuerpo", "Ir", flow_token="", flow_id="1"
        )


def test_flow_accepts_flow_name():
    payload = builders.build_interactive_flow(
        "573001112233", "cuerpo", "Ir", flow_token="T", flow_name="reservas"
    )
    parameters = payload["interactive"]["action"]["parameters"]
    assert parameters["flow_name"] == "reservas"
    assert "flow_id" not in parameters


def test_screen_is_rejected_with_data_exchange():
    with pytest.raises(ValueError, match="solo aplica con flow_action=navigate"):
        builders.build_interactive_flow(
            "573001112233",
            "cuerpo",
            "Ir",
            flow_token="T",
            flow_id="1",
            flow_action=FlowAction.DATA_EXCHANGE,
            screen="PANTALLA",
        )


def test_data_exchange_without_screen_is_valid():
    payload = builders.build_interactive_flow(
        "573001112233",
        "cuerpo",
        "Ir",
        flow_token="T",
        flow_id="1",
        flow_action="data_exchange",
    )
    parameters = payload["interactive"]["action"]["parameters"]
    assert parameters["flow_action"] == "data_exchange"
    assert "flow_action_payload" not in parameters


def test_empty_data_is_omitted():
    """Meta rechaza un ``data`` vacío."""
    payload = builders.build_interactive_flow(
        "573001112233", "cuerpo", "Ir", flow_token="T", flow_id="1", data={}
    )
    assert "flow_action_payload" not in payload["interactive"]["action"]["parameters"]


def test_flow_draft_mode():
    payload = builders.build_interactive_flow(
        "573001112233", "cuerpo", "Ir", flow_token="T", flow_id="1", mode=FlowMode.DRAFT
    )
    assert payload["interactive"]["action"]["parameters"]["mode"] == "draft"


def test_flow_rejects_unknown_mode():
    with pytest.raises(ValueError, match="mode debe ser uno de"):
        builders.build_interactive_flow(
            "573001112233", "cuerpo", "Ir", flow_token="T", flow_id="1", mode="borrador"
        )


def test_flow_cta_limit():
    with pytest.raises(ValueError, match="máximo 30"):
        builders.build_interactive_flow(
            "573001112233", "cuerpo", "x" * 31, flow_token="T", flow_id="1"
        )


def test_flow_cta_is_required():
    with pytest.raises(ValueError, match="cta\\) es obligatoria"):
        builders.build_interactive_flow(
            "573001112233", "cuerpo", "", flow_token="T", flow_id="1"
        )


# --- Respuestas entrantes ----------------------------------------------------


def _inbound(message):
    return {
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "PNID"},
                            "messages": [message],
                        }
                    }
                ],
            }
        ]
    }


def _interactive(kind, inner):
    return _inbound(
        {
            "from": "573001112233",
            "id": "wamid.I",
            "type": "interactive",
            "interactive": {"type": kind, kind: inner},
        }
    )


def test_parse_list_reply_exposes_the_id():
    """El ``id`` es lo que necesita el host para decidir; ``title`` es solo visible."""
    events = parse_webhook(
        _interactive(
            "list_reply",
            {"id": "exp", "title": "Express", "description": "1-2 días"},
        )
    )
    reply = events.messages[0].interactive
    assert reply.type == "list_reply"
    assert reply.id == "exp"
    assert reply.title == "Express"
    assert reply.description == "1-2 días"


def test_parse_button_reply():
    events = parse_webhook(
        _interactive("button_reply", {"id": "cancelar", "title": "Cancelar"})
    )
    reply = events.messages[0].interactive
    assert reply.type == "button_reply"
    assert reply.id == "cancelar"
    assert reply.description is None


def test_parse_flow_response_needs_a_second_json_parse():
    """``response_json`` llega como cadena JSON, no como objeto."""
    events = parse_webhook(
        _interactive(
            "nfm_reply",
            {
                "name": "flow",
                "body": "Sent",
                "response_json": '{"flow_token": "T-42", "email": "ana@ejemplo.com"}',
            },
        )
    )
    reply = events.messages[0].interactive
    assert reply.type == "nfm_reply"
    assert reply.flow_token == "T-42"
    assert reply.flow_response == {"flow_token": "T-42", "email": "ana@ejemplo.com"}


def test_malformed_flow_response_does_not_break_parsing():
    events = parse_webhook(
        _interactive("nfm_reply", {"body": "Sent", "response_json": "no-es-json"})
    )
    reply = events.messages[0].interactive
    assert reply.flow_response is None
    assert reply.title == "Sent"


def test_non_interactive_message_has_no_interactive():
    events = parse_webhook(
        _inbound({"from": "573001112233", "type": "text", "text": {"body": "hola"}})
    )
    assert events.messages[0].interactive is None


# --- Integración con el cliente ----------------------------------------------


async def test_send_list_posts_expected_payload():
    captured, handler = accepted_handler()
    client = make_messages_client(handler)
    await client.send_list(
        "573001112233",
        "Elige",
        "Opciones",
        [builders.list_section([builders.list_row("a", "A")])],
        phone_number_id="PNID",
    )
    assert captured["body"]["interactive"]["type"] == "list"


async def test_send_flow_posts_expected_payload():
    captured, handler = accepted_handler()
    client = make_messages_client(handler)
    await client.send_flow(
        "573001112233",
        "Reserva",
        "Reservar",
        phone_number_id="PNID",
        flow_token="T-42",
        flow_id="123",
    )
    parameters = captured["body"]["interactive"]["action"]["parameters"]
    assert parameters["flow_token"] == "T-42"


async def test_list_can_be_a_reply():
    captured, handler = accepted_handler()
    client = make_messages_client(handler)
    await client.send_list(
        "573001112233",
        "Elige",
        "Opciones",
        [builders.list_section([builders.list_row("a", "A")])],
        phone_number_id="PNID",
        reply_to="wamid.ABC",
    )
    assert captured["body"]["context"] == {"message_id": "wamid.ABC"}


# --- Botón CTA con URL -------------------------------------------------------


def test_cta_url_payload_shape():
    payload = builders.build_interactive_cta_url(
        "573001112233",
        "Consulta las fechas disponibles",
        "Ver fechas",
        "https://luckyshrub.com/agenda",
        footer="Sujeto a cambios",
    )
    interactive = payload["interactive"]
    assert interactive["type"] == "cta_url"
    assert interactive["action"] == {
        "name": "cta_url",
        "parameters": {
            "display_text": "Ver fechas",
            "url": "https://luckyshrub.com/agenda",
        },
    }
    assert interactive["footer"] == {"text": "Sujeto a cambios"}


def test_cta_url_requires_a_url():
    with pytest.raises(ValueError, match="se requiere 'button_url'"):
        builders.build_interactive_cta_url("573001112233", "cuerpo", "Ver", "  ")


def test_cta_url_label_limit():
    with pytest.raises(ValueError, match="máximo 20"):
        builders.build_interactive_cta_url("573001112233", "cuerpo", "x" * 21, "https://x.com")


def test_cta_url_body_limit():
    with pytest.raises(ValueError, match="máximo 1024"):
        builders.build_interactive_cta_url("573001112233", "x" * 1025, "Ver", "https://x.com")


def test_cta_url_accepts_a_media_header():
    """A diferencia de la lista, el CTA sí admite cabecera de medio."""
    payload = builders.build_interactive_cta_url(
        "573001112233",
        "cuerpo",
        "Ver",
        "https://x.com",
        header={"type": "image", "image": {"id": "MID"}},
    )
    assert payload["interactive"]["header"]["type"] == "image"


def test_interactive_footer_limit():
    with pytest.raises(ValueError, match="máximo 60"):
        builders.build_interactive_cta_url(
            "573001112233", "cuerpo", "Ver", "https://x.com", footer="x" * 61
        )
