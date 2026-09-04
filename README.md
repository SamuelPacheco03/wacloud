# wacloud

Cliente **stateless** e infra-agnóstico para la [WhatsApp Cloud API](https://developers.facebook.com/documentation/business-messaging/whatsapp) de Meta.

La librería no conoce bases de datos, variables de entorno ni frameworks web. Recibe las
credenciales por número mediante un `CredentialResolver` inyectado y el almacenamiento de
medios mediante un `StorageBackend` inyectado. El host (p. ej. `siriusbot`) aporta esas
implementaciones: tokens cifrados en base de datos, Cloudflare R2, etc.

Async sobre `httpx`, multi-tenant por número. Solo dos dependencias: `httpx` y `pydantic`.

## Instalación

No está en PyPI, pero el repo es público: se instala desde el tarball que GitHub sirve por
HTTPS, fijando un tag para que la instalación sea reproducible.

```bash
pip install "wacloud @ https://github.com/SamuelPacheco03/wacloud/archive/v0.10.0.tar.gz"
```

Sobre una copia de trabajo, con los extras de desarrollo (pytest, ruff, mypy):

```bash
pip install -e ".[dev]"
```

## Uso

```python
from wacloud import (
    MessagesClient,
    StaticCredentialResolver,
    Transport,
    WaCredentials,
)

resolver = StaticCredentialResolver(
    WaCredentials(phone_number_id="123456", access_token="EAA...")
)

async with Transport() as transport:
    messages = MessagesClient(transport, resolver)
    result = await messages.send_text(
        "+57 322 543 2100", "Hola", phone_number_id="123456"
    )
    print(result.message_id)
```

En producción, el host implementa su propio `CredentialResolver`:

```python
class DbCredentialResolver:
    async def for_phone_number_id(self, phone_number_id: str) -> WaCredentials:
        row = await db.fetch_number(phone_number_id)
        return WaCredentials(
            phone_number_id=phone_number_id,
            access_token=fernet.decrypt(row.token).decode(),
            waba_id=row.waba_id,
            app_secret=fernet.decrypt(row.app_secret).decode(),
        )

    async def for_waba_id(self, waba_id: str) -> WaCredentials:
        ...
```

### Lo que devuelve cada llamada

Tres formas y no hay una cuarta:

| Qué pides | Qué recibes | Ejemplo |
| --- | --- | --- |
| Un recurso | Un modelo tipado | `send_text` → `SendResult`; `numbers.get` → `PhoneNumberInfo` |
| Una colección | Una `list[X]`, ya paginada entera | `templates.list_all` → `list[TemplateInfo]` |
| Una operación | Un `bool` | `waba.subscribe`, `numbers.register`, `templates.delete` |

```python
result = await messages.send_text(to, "Hola", phone_number_id=pnid)
result.message_id                                  # modelo

for number in await numbers.list_all(waba_id):     # lista, sin envoltorio
    print(number.display_phone_number, number.quality_rating)

if await templates.delete(waba_id, name="recibo"): # booleano
    ...
```

**Ninguna llamada devuelve el `dict` crudo de Meta.** Es la línea que separa esta librería
de un `httpx` con azúcar: si tienes que leer el esquema de Meta para saber si algo salió
bien, no te hemos ahorrado nada, y tu código queda atado a una forma que Meta cambia entre
versiones. Para lo que el modelo no cubre está `raw` dentro de él:

```python
info = await numbers.get(pnid)
info.quality_rating      # campo modelado
info.raw["campo_nuevo"]  # lo que Meta añada entre versiones, sin esperar a una release
```

Un listado viene **completo**: la librería sigue los cursores de Meta hasta el final.
Quedarse con la primera página devuelve listas incompletas en silencio, y ese fallo no se
ve: parece simplemente que la plantilla no existe.

### Webhook

Son dos pasos y ambos son obligatorios. El alta (`GET`) y la firma de cada notificación
(`POST`):

```python
from fastapi import Request, Response
from wacloud import first_phone_number_id, parse_webhook, verify_signature
from wacloud.webhook import verify_subscription


@app.get("/webhook")
async def subscribe(request: Request) -> Response:
    challenge = verify_subscription(
        expected_token=MY_VERIFY_TOKEN,
        mode=request.query_params.get("hub.mode"),
        token=request.query_params.get("hub.verify_token"),
        challenge=request.query_params.get("hub.challenge"),
    )
    if challenge is None:
        return Response(status_code=403)
    return Response(content=challenge, media_type="text/plain")


@app.post("/webhook")
async def receive(request: Request) -> Response:
    raw = await request.body()          # ¡el cuerpo crudo, no un JSON reserializado!
    payload = json.loads(raw)

    pnid = first_phone_number_id(payload)
    credentials = await resolver.for_phone_number_id(pnid)
    if not verify_signature(
        app_secret=credentials.app_secret,
        raw_body=raw,
        signature_header=request.headers.get("X-Hub-Signature-256"),
    ):
        return Response(status_code=403)

    events = parse_webhook(payload)
    for message in events.messages:
        ...
    return Response(status_code=200)
```

La firma se calcula sobre el **cuerpo crudo en bytes**: reserializar un JSON ya parseado
cambia el orden de claves y el escapado, y el HMAC deja de cuadrar.

### Crear una plantilla

La parte que más rechazos provoca es el campo `example`, cuya forma **no es la misma** en
cada componente: la cabecera lleva un array plano y el cuerpo un array de arrays. Los
builders lo generan solos a partir de los valores que pases.

```python
from wacloud import TemplateCategory, buttons, components

await templates.create(
    waba_id,
    name="order_confirmation",          # minúsculas, dígitos y guiones bajos
    language="es_ES",
    category=TemplateCategory.UTILITY,
    components=[
        components.text_header("Pedido {{order_id}}", examples={"order_id": "A-123"}),
        components.body(
            "Hola {{name}}, tu pedido {{order_id}} llega el {{date}}.",
            examples={"name": "Ana", "order_id": "A-123", "date": "12 sep"},
        ),
        components.footer("Lucky Shrub"),
        components.buttons([
            buttons.url("Ver pedido", "https://luckyshrub.com/o/{{1}}", example="A-123"),
            buttons.phone_number("Llamar", "+34911234567"),
            buttons.quick_reply("Cancelar"),
        ]),
    ],
)
```

El formato de las variables (`POSITIONAL` o `NAMED`) se deduce del texto: usa `{{1}}` y
pasa una lista, o usa `{{nombre}}` y pasa un diccionario. Mezclarlos, saltarse un número,
olvidar un ejemplo o poner un nombre con mayúsculas falla en local, antes de gastar cupo
de la API.

Con cabecera de imagen hacen falta dos pasos, porque Meta usa un identificador distinto
para crear que para enviar:

```python
from wacloud import components, upload_resumable

handle = await upload_resumable(
    transport,
    app_id=META_APP_ID,        # el ID de la app, no el WABA ni el número
    access_token=token,
    data=imagen_bytes,
    content_type="image/jpeg",
    file_name="muestra.jpg",
)
components.media_header("IMAGE", handle=handle)
```

### Enviar una plantilla aprobada

```python
from wacloud import parameters

await messages.send_template(
    "+57 322 543 2100",
    "order_confirmation",
    "es_ES",
    [
        parameters.header([parameters.text("A-123", name="order_id")]),
        parameters.body([
            parameters.text("Ana", name="name"),
            parameters.text("A-123", name="order_id"),
            parameters.text("12 sep", name="date"),
        ]),
        parameters.button_url(0, "A-123"),
    ],
    phone_number_id="123456",
)
```

### Otros tipos de mensaje

```python
from wacloud import builders

await messages.send_location(
    "+57 300 111 2233", phone_number_id=pnid,
    latitude=4.7110, longitude=-74.0721,
    name="Plaza Bolívar", address="Cra 7, Bogotá",
)

await messages.send_contacts(
    "+57 300 111 2233",
    [builders.contact(
        builders.contact_name("Ana Ruiz", first_name="Ana"),
        phones=[builders.contact_phone("+573001112233", wa_id="573001112233")],
        org=builders.contact_org(company="Lucky Shrub"),
    )],
    phone_number_id=pnid,
)

await messages.send_sticker("+57 300 111 2233", phone_number_id=pnid, media_id=mid)
await messages.send_reaction(
    "+57 300 111 2233", phone_number_id=pnid, message_id="wamid.ABC", emoji="👍"
)
```

Cualquier envío puede citar un mensaje anterior con `reply_to`:

```python
await messages.send_text(
    "+57 300 111 2233", "Claro", phone_number_id=pnid, reply_to="wamid.ABC"
)
```

En sentido entrante, el parser normaliza estos tipos:

```python
for message in parse_webhook(payload).messages:
    if message.location:
        print(message.location.latitude, message.location.longitude)
    if message.reaction:
        print("retirada" if message.reaction.removed else message.reaction.emoji)
    for card in message.shared_contacts:      # tarjetas que envió el usuario
        print(card["name"]["formatted_name"])
    print(message.contacts)                   # perfil de quien escribe: no es lo mismo
```

### Listas y Flows

Una lista muestra un menú de opciones. El límite que más se malinterpreta: **10 filas en
total entre todas las secciones**, no 10 por sección.

```python
await messages.send_list(
    "+57 300 111 2233",
    "¿Qué envío prefieres?",
    "Opciones",                      # etiqueta que abre el menú, máx. 20
    [
        builders.list_section(
            [
                builders.list_row("exp", "Express", description="1-2 días"),
                builders.list_row("std", "Estándar"),
            ],
            title="Rápido",          # obligatorio en cuanto hay más de una sección
        ),
    ],
    phone_number_id=pnid,
    header="Envío",                  # solo texto: la lista no admite cabecera de medio
)
```

Un Flow abre un formulario multipantalla dentro de WhatsApp:

```python
await messages.send_flow(
    "+57 300 111 2233",
    "Reserva tu cita",
    "Reservar",
    phone_number_id=pnid,
    flow_id="123456",
    flow_token="reserva-42",         # única forma de correlacionar la respuesta
    screen="APPOINTMENT",
    data={"servicio": "corte"},
)
```

`flow_token` es obligatorio en esta librería aunque Meta lo dé por opcional: la respuesta
de un Flow **no incluye el `flow_id`**, así que sin token no hay manera de saber a qué
envío corresponde.

Las respuestas llegan normalizadas, con el `id` que hace falta para decidir:

```python
for message in parse_webhook(payload).messages:
    reply = message.interactive
    if not reply:
        continue
    if reply.type in ("list_reply", "button_reply"):
        despachar(reply.id)                  # 'exp', 'cancelar'…
    elif reply.type == "nfm_reply":
        print(reply.flow_token, reply.flow_response)   # ya parseado
```

`response_json` viene de Meta como cadena JSON dentro del JSON; el parser hace ese segundo
parseo por ti.

### Gestión del número

Administración de la línea: estado, alta, verificación y perfil público.

```python
from wacloud import BusinessVertical, NumbersClient

numbers = NumbersClient(transport, resolver)

info = await numbers.get(pnid)
print(info.quality_rating, info.status, info.messaging_limit)   # GREEN, CONNECTED, TIER_2K

for number in await numbers.list_all(waba_id):
    print(number.display_phone_number, number.quality_rating)

await numbers.update_profile(
    pnid,
    about="Vivero de suculentas desde 1998",
    email="hola@luckyshrub.com",
    vertical=BusinessVertical.RETAIL,
    websites=["https://luckyshrub.com"],
)
```

Alta de un número nuevo:

```python
await numbers.set_two_step_pin(pnid, "150954")          # seis dígitos
await numbers.request_verification_code(pnid)           # SMS por defecto
await numbers.verify_code(pnid, "000000")
await numbers.register(pnid, pin="150954", data_localization_region="DE")
```

Dos avisos que la librería no puede evitar por ti: el registro y la baja comparten un
límite de **10 operaciones por número cada 72 horas**, y pedir el código a un número ya
verificado devuelve un error. Comprueba `info.is_verified` antes.

Los campos enumerados (`quality_rating`, `status`…) se exponen como cadena, no como enum:
la documentación de Meta se contradice en la ortografía de varios valores y forzar la
conversión haría fallar el parseo ante algo que Meta considera válido. Para comparar están
`QualityRating`, `NumberStatus` y compañía.

### Alta de una empresa: WABA y Embedded Signup

Conectar la cuenta de un cliente sin entrar al panel de Meta son dos pasos, y el segundo es
el que se olvida: **sin suscribir la app a la WABA, Meta no entrega ni un solo webhook de
esa cuenta** —ni mensajes, ni estados, ni el veredicto de las plantillas—. Y no devuelve
ningún error: simplemente no llega nada.

```python
from wacloud import OAuthClient, WabaClient

# 1. El popup de Embedded Signup devuelve un `code` de un solo uso.
oauth = OAuthClient(transport, app_id=APP_ID, app_secret=APP_SECRET)
token = await oauth.exchange_code(code)          # token de negocio, de larga duración

# 2. Suscribir la app, o esta cuenta no entregará ningún webhook.
waba = WabaClient(transport, resolver)
await waba.subscribe(waba_id)

info = await waba.get(waba_id)
print(info.name, info.account_review_status)     # sin aprobar no entrega en producción
```

`subscribe` es idempotente. Admite `override_callback_uri` para que cada cuenta entregue a
una URL propia sin montar una app de Meta por cliente; si se usa, Meta exige también
`verify_token` y verifica esa URL con el mismo `GET` de `hub.challenge` que un webhook
normal.

Cuando alguien reporta que no le llegan mensajes, la primera comprobación es si la
suscripción quedó hecha y a qué URL apunta:

```python
for app in await waba.list_subscriptions(waba_id):
    print(app.name, app.override_callback_uri)
```

Un aviso que la librería no puede evitar por ti: el `app_secret` viaja en la **query
string** del canje porque así lo define Meta. No expongas `exchange_code` detrás de nada
que registre URLs completas, y no lo reenvíes desde un frontend. El `code`, además, es de
un solo uso: si el canje falla por red hay que rehacer el popup, no reintentar.

### Lista de bloqueo

```python
from wacloud import BlockedUsersClient

blocked = BlockedUsersClient(transport, resolver)

result = await blocked.block(pnid, ["573001112233"])
print(result.succeeded, result.failed)

await blocked.unblock(pnid, ["573001112233"])
print(await blocked.list_all(pnid))
```

Mira siempre `failed`: Meta responde **por usuario y no por lote**, así que puede aceptar
parte y rechazar el resto. Dar por bloqueado a alguien que fue rechazado deja un agujero
silencioso en la moderación.

### Manejo de errores

Los errores llevan el código de Meta, que es lo que Meta manda usar para decidir:

```python
from wacloud import WaCloudError

try:
    await messages.send_text(...)
except WaCloudError as exc:
    if not exc.retryable:
        logger.error("fallo definitivo %s: %s", exc.code, exc.details)
    elif exc.retry_after_seconds and exc.retry_after_seconds > 60:
        # p. ej. el código 131049 exige esperar 24 h: reprogramar, no reintentar aquí.
        await schedule_retry(after=exc.retry_after_seconds)
```

## Módulos

| Módulo | Responsabilidad |
|---|---|
| `config` | `GraphConfig`: URL base y versión de la Graph API. Sin secretos. |
| `retry` | `RetryPolicy`: reintentos y backoff, sustituible por el host. |
| `errors` · `error_codes` | Jerarquía tipada y clasificación de los códigos de Meta. |
| `credentials` | `WaCredentials` y el protocolo `CredentialResolver`. |
| `transport` | `httpx.AsyncClient` compartido, reintentos y mapeo de errores. |
| `recipient` · `limits` | Normalización del destinatario y límites documentados de Meta. |
| `messages.builders` | Payloads por familia: texto, medios, interactivos (botones, CTA, lista, Flow), contactos, ubicación, reacciones. |
| `flows` | Enums de WhatsApp Flows, compartidos por plantillas y mensajes. |
| `messages` | `MessagesClient`. |
| `templates.components` · `.buttons` | Estructura de una plantilla al **crearla**. |
| `templates.parameters` | Valores concretos al **enviarla**. |
| `templates.definition` · `.placeholders` | Ensamblado y validación de variables. |
| `templates` | `TemplatesClient` y builders de autenticación/marketing. |
| `media` | `StorageBackend`, subida, descarga e ingesta de medios. |
| `numbers` | Estado, registro, verificación y perfil del número; `numbers.blocking`, la lista de bloqueo. |
| `waba` | `WabaClient`: suscripción de la app a la WABA y metadatos de la cuenta. |
| `oauth` | `OAuthClient`: canje del código de Embedded Signup por el token de negocio. |
| `webhook` | Alta de suscripción, firma, y parser (`events` · `extract` · `parser`). |

## Desarrollo

```bash
pip install -e ".[dev]"
python scripts/check.py          # formato, lint, tipos y tests
python scripts/check.py --fix    # además arregla formato y lint
```

Opcionalmente, engancha los mismos gates al commit:

```bash
pre-commit install
```

Los tests nunca salen a la red: usan `httpx.MockTransport`. `mypy` corre en modo `strict`
y la cobertura tiene un mínimo del 90 %. La CI repite todo sobre Python 3.10–3.13.

Ver `CLAUDE.md` para las convenciones de arquitectura y las reglas de la API de Meta que el
código respeta, y `CHANGELOG.md` para el historial de versiones.

## Estado

Cubierto: envío de texto, medios, interactivos (botones y CTA) y plantillas; ciclo de vida
completo de plantillas (crear con validación local, editar, listar con paginación, borrar);
los 11 tipos de botón; subida de medios y Resumable Upload API; webhook completo.

Cubre además ubicación, contactos, stickers, reacciones, respuestas citadas y los cuatro
tipos de interactivo (botones, CTA, lista y Flow), tanto al enviar como al recibir.

Del lado de la administración: gestión del número, lista de bloqueo, suscripción de la app
a una WABA y canje de Embedded Signup — lo que hace falta para dar de alta a un cliente sin
entrar al panel de Meta.

Pendiente: mensajes de catálogo y producto (requieren un catálogo de Commerce Manager), y
los webhooks de gestión `account_update` y `phone_number_quality_update`, que hoy hay que
leer de `raw`. `message_template_status_update` sí llega parseado desde la 0.7.0.

Ver `MIGRATION.md` para los cambios que rompen la API: hoy cubre 0.1 → 0.2, 0.6 → 0.7 y
0.9 → 0.10.

## Licencia

MIT. Ver [LICENSE](LICENSE).
