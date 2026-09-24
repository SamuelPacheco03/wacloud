"""Pedir la ubicación y recibirla.

El gemelo de ``test_contact_info.py`` para el otro dato que el usuario tiene que poner
de su parte. La diferencia está en la vuelta: una tarjeta de contacto puede ser la de un
tercero y por eso Meta manda ``origin``, mientras que un pin es el sitio al que apunta y
llega igual se haya pedido o no.

Referencia:
https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/location-request-messages
"""

from __future__ import annotations

import pytest

from tests.factories import accepted_handler, make_messages_client
from wacloud import parse_webhook
from wacloud.messages import builders

PNID = "941351305730281"
BSUID = "CO.2452497711827233"


# -- Pedirla ----------------------------------------------------------------------


def test_interactive_payload_matches_meta():
    """El tipo y la acción **no se llaman igual**, al revés que en el resto.

    ``cta_url`` y ``request_contact_info`` repiten el mismo valor en ``type`` y en
    ``action.name``; copiar ese patrón aquí produce un payload que Meta rechaza.
    """
    payload = builders.build_request_location(BSUID, "¿Dónde te lo llevamos? 📍")

    assert payload["interactive"] == {
        "type": "location_request_message",
        "body": {"text": "¿Dónde te lo llevamos? 📍"},
        "action": {"name": "send_location"},
    }


def test_there_is_no_header_or_footer_to_pass():
    """Meta documenta este interactivo **sin** cabecera ni pie, el único de los seis.

    No se aceptan para descartarlos después: el destinatario recibiría algo distinto de
    lo que el host pidió y no quedaría rastro en ningún log. Si alguien los añade a la
    firma "por simetría", este test es el que lo para.
    """
    with pytest.raises(TypeError):
        builders.build_request_location(BSUID, "Hola", header={"type": "text", "text": "x"})

    with pytest.raises(TypeError):
        builders.build_request_location(BSUID, "Hola", footer="Gracias")


def test_it_can_be_sent_to_someone_we_only_know_by_bsuid():
    assert builders.build_request_location(BSUID, "¿Dónde estás?")["recipient"] == BSUID


def test_a_body_over_the_limit_is_rejected_before_calling_meta():
    with pytest.raises(ValueError, match=r"interactive\.body"):
        builders.build_request_location(BSUID, "x" * 1025)


async def test_the_client_posts_it_to_the_messages_endpoint():
    captured, handler = accepted_handler()

    await make_messages_client(handler).send_request_location(
        BSUID, "¿Dónde te lo llevamos?", phone_number_id=PNID
    )

    assert captured["path"].endswith(f"/{PNID}/messages")
    assert captured["body"]["interactive"]["type"] == "location_request_message"
    assert captured["body"]["interactive"]["action"] == {"name": "send_location"}


# -- Recibirla --------------------------------------------------------------------


def _shared(location: dict) -> dict:
    return {
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": PNID},
                            "contacts": [{"wa_id": "573001112233"}],
                            "messages": [
                                {
                                    "id": "wamid.X",
                                    "timestamp": "1788793900",
                                    "type": "location",
                                    "from": "573001112233",
                                    "location": location,
                                }
                            ],
                        },
                    }
                ],
            }
        ]
    }


#: Lo que manda Meta cuando el usuario elige un sitio del buscador de WhatsApp.
_PLACE = {
    "latitude": 3.4205678,
    "longitude": -76.5412345,
    "name": "Casa",
    "address": "Calle 10 # 20-30, Cali",
}


def test_the_coordinates_arrive_as_numbers():
    """Al enviar, Meta documenta las coordenadas como cadena; al recibir, como número.

    La asimetría no es un capricho de la librería: es de Meta, y aquí se respeta porque
    el punto acaba en una columna numérica y en una consulta geoespacial.
    """
    location = parse_webhook(_shared(_PLACE)).messages[0].location

    assert location is not None
    assert location.latitude == 3.4205678
    assert location.longitude == -76.5412345
    assert isinstance(location.latitude, float)


def test_the_place_name_and_address_come_through():
    location = parse_webhook(_shared(_PLACE)).messages[0].location

    assert location is not None
    assert location.name == "Casa"
    assert location.address == "Calle 10 # 20-30, Cali"


def test_a_bare_pin_is_a_location_too():
    """``name`` y ``address`` solo aparecen si el usuario eligió un sitio del buscador.

    Un pin sin ellos es el caso normal de "comparto dónde estoy", y tiene que llegar
    igual: son ``None``, no una ubicación que falte.
    """
    location = (
        parse_webhook(_shared({"latitude": 3.42, "longitude": -76.54})).messages[0].location
    )

    assert location is not None
    assert (location.latitude, location.longitude) == (3.42, -76.54)
    assert location.name is None
    assert location.address is None


def test_coordinates_sent_as_strings_are_still_numbers():
    """Permisivo al parsear: Meta documenta números, pero un intermediario puede mandar
    cadenas y perder el mensaje entero por eso sería peor que convertirlo."""
    location = (
        parse_webhook(_shared({"latitude": "3.42", "longitude": "-76.54"}))
        .messages[0]
        .location
    )

    assert location is not None
    assert location.latitude == 3.42


def test_a_location_message_is_never_discarded():
    """El descarte era la sospecha del consumidor: no ocurre, y este test lo fija."""
    events = parse_webhook(_shared(_PLACE))

    assert events.discarded == []
    assert events.messages[0].type == "location"


def test_the_text_is_for_showing_it_not_for_the_turn():
    """``text`` es la etiqueta legible del mensaje; el dato vive en ``location``.

    Cuando no hay nombre cae en las coordenadas, así que un host que meta ``text`` en el
    turno del modelo le estaría dando un punto por el mismo canal por el que entra lo que
    teclea el usuario. El punto se lee de ``location``, siempre.
    """
    assert parse_webhook(_shared(_PLACE)).messages[0].text == "Casa"

    bare = parse_webhook(_shared({"latitude": 3.42, "longitude": -76.54})).messages[0]
    assert bare.text == "3.42, -76.54"
    assert bare.location is not None


def test_a_pin_from_someone_we_only_know_by_bsuid_arrives_too():
    """Quien tiene nombre de usuario llega sin teléfono, y comparte ubicación igual."""
    payload = _shared(_PLACE)
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    del message["from"]
    message["from_user_id"] = BSUID

    parsed = parse_webhook(payload).messages[0]

    assert parsed.from_user == BSUID
    assert parsed.location is not None
