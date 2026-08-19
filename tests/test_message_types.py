"""Tests de ubicación, contactos, stickers, reacciones y respuestas citadas."""

import pytest

from tests.factories import accepted_handler, make_messages_client
from wacloud.messages import builders

# --- Ubicación ---------------------------------------------------------------


def test_location_payload_shape():
    payload = builders.build_location(
        "573001112233",
        latitude=4.7110,
        longitude=-74.0721,
        name="Plaza Bolívar",
        address="Cra 7, Bogotá",
    )
    assert payload["type"] == "location"
    assert payload["location"]["name"] == "Plaza Bolívar"
    assert payload["location"]["address"] == "Cra 7, Bogotá"


def test_location_coordinates_are_sent_as_strings():
    """Meta documenta latitud y longitud como String en el envío."""
    payload = builders.build_location("573001112233", latitude=4.711, longitude=-74.0721)
    assert isinstance(payload["location"]["latitude"], str)
    assert isinstance(payload["location"]["longitude"], str)


def test_location_accepts_strings_verbatim():
    payload = builders.build_location(
        "573001112233", latitude="4.71100", longitude="-74.07210"
    )
    assert payload["location"]["latitude"] == "4.71100"


def test_location_rejects_out_of_range_latitude():
    """Detecta el error clásico de intercambiar latitud y longitud."""
    with pytest.raises(ValueError, match=r"latitude.*fuera del rango"):
        builders.build_location("573001112233", latitude=120.0, longitude=4.0)


def test_location_rejects_out_of_range_longitude():
    with pytest.raises(ValueError, match=r"longitude.*fuera del rango"):
        builders.build_location("573001112233", latitude=4.0, longitude=200.0)


def test_location_rejects_non_numeric_coordinate():
    with pytest.raises(ValueError, match="no es una coordenada"):
        builders.build_location("573001112233", latitude="norte", longitude=4.0)


def test_location_rejects_address_without_name():
    """WhatsApp no muestra la dirección si no hay nombre."""
    with pytest.raises(ValueError, match="necesita 'name'"):
        builders.build_location("573001112233", latitude=4.0, longitude=-74.0, address="Cra 7")


def test_location_omits_empty_optional_fields():
    payload = builders.build_location("573001112233", latitude=4.0, longitude=-74.0)
    assert set(payload["location"]) == {"latitude", "longitude"}


# --- Contactos ---------------------------------------------------------------


def test_contact_name_requires_formatted_name():
    with pytest.raises(ValueError, match="formatted_name es obligatorio"):
        builders.contact_name("")


def test_contact_name_drops_empty_optionals():
    assert builders.contact_name("Ana Ruiz", first_name="Ana") == {
        "formatted_name": "Ana Ruiz",
        "first_name": "Ana",
    }


def test_full_contact_payload_shape():
    card = builders.contact(
        builders.contact_name("Ana Ruiz", first_name="Ana", last_name="Ruiz"),
        phones=[builders.contact_phone("+573001112233", type="Mobile", wa_id="573001112233")],
        emails=[builders.contact_email("ana@ejemplo.com", type="Work")],
        urls=[builders.contact_url("https://ejemplo.com")],
        addresses=[builders.contact_address(city="Bogotá", country="Colombia")],
        org=builders.contact_org(company="Lucky Shrub", title="Directora"),
        birthday="1990-05-14",
    )
    payload = builders.build_contacts("573001112233", [card])

    assert payload["type"] == "contacts"
    contact = payload["contacts"][0]
    assert contact["name"]["formatted_name"] == "Ana Ruiz"
    assert contact["phones"][0]["wa_id"] == "573001112233"
    assert contact["org"]["company"] == "Lucky Shrub"
    assert contact["birthday"] == "1990-05-14"


def test_minimal_contact_only_needs_a_name():
    """Meta solo exige ``name.formatted_name``."""
    card = builders.contact(builders.contact_name("Ana Ruiz"))
    assert card == {"name": {"formatted_name": "Ana Ruiz"}}


@pytest.mark.parametrize("bad", ["14-05-1990", "1990/05/14", "ayer"])
def test_contact_rejects_bad_birthday_format(bad):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        builders.contact(builders.contact_name("Ana"), birthday=bad)


def test_contact_requires_a_built_name():
    with pytest.raises(ValueError, match="contact_name"):
        builders.contact({"first_name": "Ana"})


def test_contact_phone_requires_a_number():
    with pytest.raises(ValueError, match="teléfono es obligatorio"):
        builders.contact_phone("")


def test_contact_address_requires_some_content():
    with pytest.raises(ValueError, match="al menos un campo"):
        builders.contact_address()


def test_contact_org_requires_some_content():
    with pytest.raises(ValueError, match="al menos un campo"):
        builders.contact_org()


def test_build_contacts_requires_at_least_one():
    with pytest.raises(ValueError, match="al menos un contacto"):
        builders.build_contacts("573001112233", [])


def test_build_contacts_rejects_raw_dicts():
    with pytest.raises(ValueError, match="contact\\(\\)"):
        builders.build_contacts("573001112233", [{"nombre": "Ana"}])


# --- Sticker -----------------------------------------------------------------


def test_sticker_payload_shape():
    payload = builders.build_sticker("573001112233", media_id="MID")
    assert payload["type"] == "sticker"
    assert payload["sticker"] == {"id": "MID"}


def test_sticker_requires_a_source():
    with pytest.raises(ValueError, match="'link' o 'media_id'"):
        builders.build_sticker("573001112233")


# --- Reacciones --------------------------------------------------------------


def test_reaction_payload_shape():
    payload = builders.build_reaction("573001112233", "wamid.ABC", "👍")
    assert payload["type"] == "reaction"
    assert payload["reaction"] == {"message_id": "wamid.ABC", "emoji": "👍"}


def test_reaction_requires_an_emoji():
    with pytest.raises(ValueError, match="build_remove_reaction"):
        builders.build_reaction("573001112233", "wamid.ABC", "")


def test_remove_reaction_sends_an_empty_emoji():
    payload = builders.build_remove_reaction("573001112233", "wamid.ABC")
    assert payload["reaction"] == {"message_id": "wamid.ABC", "emoji": ""}


def test_reaction_requires_a_message_id():
    with pytest.raises(ValueError, match="message_id es obligatorio"):
        builders.build_reaction("573001112233", "", "👍")


# --- Respuesta citada --------------------------------------------------------


def test_as_reply_adds_context_to_any_payload():
    original = builders.build_text("573001112233", "Claro")
    reply = builders.as_reply(original, "wamid.ABC")
    assert reply["context"] == {"message_id": "wamid.ABC"}
    assert reply["text"] == original["text"]


def test_as_reply_works_with_media_too():
    reply = builders.as_reply(
        builders.build_image("573001112233", media_id="MID"), "wamid.ABC"
    )
    assert reply["type"] == "image" and "context" in reply


def test_as_reply_does_not_mutate_the_original():
    """El payload debe poder reutilizarse para otro destinatario sin la cita."""
    original = builders.build_text("573001112233", "Hola")
    builders.as_reply(original, "wamid.ABC")
    assert "context" not in original


def test_as_reply_requires_a_message_id():
    with pytest.raises(ValueError, match="message_id es obligatorio"):
        builders.as_reply(builders.build_text("573001112233", "Hola"), "")


# --- Integración con el cliente ----------------------------------------------


async def test_send_location_posts_expected_payload():
    captured, handler = accepted_handler()
    client = make_messages_client(handler)
    await client.send_location(
        "573001112233",
        phone_number_id="PNID",
        latitude=4.711,
        longitude=-74.0721,
        name="Plaza",
    )
    assert captured["body"]["type"] == "location"
    assert captured["body"]["location"]["name"] == "Plaza"


async def test_send_contacts_posts_expected_payload():
    captured, handler = accepted_handler()
    client = make_messages_client(handler)
    await client.send_contacts(
        "573001112233",
        [builders.contact(builders.contact_name("Ana Ruiz"))],
        phone_number_id="PNID",
    )
    assert captured["body"]["contacts"][0]["name"]["formatted_name"] == "Ana Ruiz"


async def test_send_reaction_posts_expected_payload():
    captured, handler = accepted_handler()
    client = make_messages_client(handler)
    await client.send_reaction(
        "573001112233", phone_number_id="PNID", message_id="wamid.ABC", emoji="❤️"
    )
    assert captured["body"]["reaction"]["emoji"] == "❤️"


async def test_remove_reaction_posts_empty_emoji():
    captured, handler = accepted_handler()
    client = make_messages_client(handler)
    await client.remove_reaction(
        "573001112233", phone_number_id="PNID", message_id="wamid.ABC"
    )
    assert captured["body"]["reaction"]["emoji"] == ""


async def test_send_sticker_posts_expected_payload():
    captured, handler = accepted_handler()
    client = make_messages_client(handler)
    await client.send_sticker("573001112233", phone_number_id="PNID", media_id="MID")
    assert captured["body"]["type"] == "sticker"


async def test_reply_to_adds_context_on_any_send():
    captured, handler = accepted_handler()
    client = make_messages_client(handler)
    await client.send_text(
        "573001112233", "Claro", phone_number_id="PNID", reply_to="wamid.ABC"
    )
    assert captured["body"]["context"] == {"message_id": "wamid.ABC"}


async def test_send_payload_without_reply_to_has_no_context():
    captured, handler = accepted_handler()
    client = make_messages_client(handler)
    await client.send_text("573001112233", "Hola", phone_number_id="PNID")
    assert "context" not in captured["body"]
