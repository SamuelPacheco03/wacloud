# Migración entre versiones

Los cambios que rompen, versión a versión. La más reciente arriba.

## 0.6 → 0.7

Ningún cambio de firma: nada deja de compilar. Lo que cambia es **cuándo se reintenta un
envío**, y eso puede cambiar lo que ve un host que dependía del comportamiento anterior.

### Un envío ya no se reintenta ante un fallo ambiguo

Hasta ahora el transporte reintentaba cualquier `httpx.HTTPError` y cualquier 5xx, también
en `POST /{phone_number_id}/messages`. Un timeout de lectura o un 502 pelado **no dicen si
Meta llegó a procesar el envío**, así que el reintento le mandaba al destinatario el mismo
mensaje dos veces. La librería no guarda estado con el que darse cuenta, y deduplicar no es
su trabajo.

Ahora un envío solo reintenta lo que Meta rechazó de forma reconocible: un código del
catálogo demuestra que lo evaluó y dijo que no, así que repetirlo no puede duplicar nada.
429, `130429` y `131056` se siguen reintentando igual. **Las lecturas y la gestión de
plantillas no cambian.**

**Qué hacer.** Si tu host confiaba en ese reintento, ahora verá el error en vez de un envío
que se resuelve solo:

```python
try:
    await messages.send_text(to, body, phone_number_id=pnid)
except WaCloudError as exc:
    if exc.retryable:
        # Meta lo rechazó: se puede reprogramar sin riesgo.
        schedule_retry(after=exc.retry_after_seconds)
    else:
        # Ambiguo o definitivo. Reintentar aquí es lo que duplica el mensaje.
        mark_failed(exc)
```

Es más trabajo, y es el correcto: **tú** sabes si ese mensaje ya salió y la librería no. Si
además adjuntas `biz_opaque_callback_data` al enviar (nuevo en esta versión), el webhook de
estado te devuelve tu propia referencia y puedes reconciliar sin adivinar.

Para volver al comportamiento anterior en una llamada concreta, `Transport.request` acepta
`idempotent=True`. No se recomienda en envíos.

## 0.1 → 0.2

Versión de saneamiento: arregla bugs, separa responsabilidades y hace accionables los
errores de Meta. Hay cambios que rompen la API pública; están todos aquí.

### Lo urgente

**La versión de la Graph API pasa de `v19.0` a `v25.0`.** `v19.0` expiró el 21 de mayo de
2026. Meta **no devuelve error** cuando una versión expira: redirige la llamada en
silencio a la última versión funcional, así que hasta ahora el comportamiento real era
indeterminado. Si necesitas fijar otra versión:

```python
from wacloud import GraphConfig
config = GraphConfig(api_version="v26.0")
```

### Cambios que rompen

#### `GraphConfig` ya no lleva la política de reintentos

Los campos `max_retries`, `backoff_base_seconds` y `backoff_max_seconds` se movieron a
`RetryPolicy`, que se inyecta en el `Transport`. Eran tres ejes de cambio distintos en la
misma clase, y la política no se podía sustituir sin tocar el transporte.

```python
# Antes
config = GraphConfig(max_retries=5, backoff_base_seconds=0.5, backoff_max_seconds=8.0)
transport = Transport(config)

# Ahora
from wacloud import GraphConfig, RetryPolicy, Transport

transport = Transport(
    GraphConfig(),
    retry_policy=RetryPolicy(max_retries=5, base_seconds=1.0, max_seconds=32.0),
)
```

El backoff por defecto pasa a la progresión que Meta recomienda (`4^X`: 1 s, 4 s, 16 s)
en vez de `0.5 · 2^X`. Meta **no documenta el header `Retry-After`** para la Cloud API; el
mecanismo real es `estimated_time_to_regain_access`, que el transporte ahora lee.

#### Los clientes ya no aceptan `config`

`MessagesClient` y `TemplatesClient` recibían un `config` que guardaban y nunca leían. Se
elimina: la configuración vive en el `Transport`, que es quien hace las peticiones.

```python
# Antes
MessagesClient(transport, resolver, config=config)
TemplatesClient(transport, resolver, config=config, cache_ttl_seconds=60)

# Ahora
MessagesClient(transport, resolver)
TemplatesClient(transport, resolver, cache_ttl_seconds=60)
```

#### `TemplatesClient.list` pasa a llamarse `list_all`

El nombre `list` sombreaba al builtin dentro del cuerpo de la clase, lo que rompía las
anotaciones `list[...]` de los métodos siguientes (mypy lo detecta como error real).

```python
templates = await client.list_all(waba_id)          # antes: client.list(...)
```

Además ahora **sigue la paginación por cursores**: antes se quedaba con la primera página
y en cuentas con más de 100 plantillas devolvía una lista incompleta en silencio.

#### Los builders fallan en vez de recortar

`build_interactive_buttons` truncaba a 3 botones y cortaba los títulos a 20 caracteres sin
avisar; ahora lanza `ValueError`. Recortar en silencio hace que el destinatario reciba algo
distinto de lo que el host pidió, sin rastro en ningún log.

También validan ahora: cuerpo de texto vacío o de más de 4096 caracteres, captions de más
de 1024, pies de más de 60, títulos de botón duplicados y destinatarios sin dígitos o
fuera del rango de E.164.

Si tu código dependía del truncado, recorta explícitamente antes de llamar.

#### `build_auth_autofill` desaparece

Devolvía exactamente lo mismo que `build_auth_copy_code`: en el envío, las tres variantes
de OTP (copy_code, one-tap, zero-tap) comparten payload; lo que las diferencia es cómo se
aprobó la plantilla en Meta. Usa `build_auth_copy_code`, o el nuevo `build_auth_code` con
`with_button=`.

#### `WebhookInboundMessage`: los campos de medio se agrupan

`media_id`, `mime_type` y `filename` pasan a un objeto `media` (`InboundMedia`), que además
trae `sha256`. **Los tres siguen accesibles como propiedades**, así que el código existente
sigue funcionando:

```python
message.media_id          # sigue funcionando
message.media.sha256      # nuevo
```

#### `error_from_response` y la jerarquía de errores

`WaCloudError.retryable` era un atributo de clase y ahora es de instancia: se calcula a
partir del código de error de Meta. Comprobarlo sobre la instancia (`exc.retryable`) sigue
funcionando; comprobarlo sobre la clase (`WaRateLimited.retryable`) ya no.

### Novedades

#### Gestión del número

`NumbersClient` cubre la administración de la línea:

```python
numbers.get(pnid)                      # calidad, estado, límite de mensajería
numbers.list_all(waba_id)              # con paginación por cursores
numbers.register(...) / deregister(...)
numbers.set_two_step_pin(...)
numbers.request_verification_code(...) / verify_code(...)
numbers.get_profile(...) / update_profile(...)
```

Lee `whatsapp_business_manager_messaging_limit` y cae a `messaging_limit_tier`, que Meta
deprecó. Valida el PIN (seis dígitos), la región de localización y el sector del negocio;
**no** valida los límites de caracteres del perfil, porque Meta ya no los publica.


#### Interactivos de lista y Flow

```python
messages.send_list(...)   # menú de opciones agrupadas en secciones
messages.send_flow(...)   # formulario multipantalla dentro de WhatsApp
```

Se validan los límites reales: 10 filas **en total** entre todas las secciones (no 10 por
sección), títulos obligatorios con más de una sección, ids de fila únicos, y la cabecera de
lista restringida a texto.

En Flow, `flow_token` es obligatorio aquí aunque Meta lo dé por opcional: su respuesta no
incluye el `flow_id`, así que sin token no se puede correlacionar.

Al recibir, `message.interactive` normaliza los tres tipos de respuesta (`button_reply`,
`list_reply`, `nfm_reply`) y expone el `id` elegido, que antes solo estaba en `raw`. Para
los Flows hace además el segundo parseo de `response_json`, que Meta manda como cadena JSON
dentro del JSON.

#### `FlowAction` y `FlowIcon` se mueven a `wacloud.flows`

Estaban en `wacloud.templates.enums`, pero los Flows los usan tanto el botón `FLOW` de una
plantilla como el mensaje interactivo de tipo `flow`. Dejarlos en `templates` obligaba a
`messages` a importar de `templates`, que invierte el sentido de las capas (y provocaba un
import circular). **Se siguen reexportando desde `wacloud.templates.enums`**, así que el
código existente no se rompe.


#### Ubicación, contactos, stickers y reacciones

```python
messages.send_location(...)    # valida el rango de las coordenadas
messages.send_contacts(...)    # tarjetas compuestas con builders.contact(...)
messages.send_sticker(...)
messages.send_reaction(...) / messages.remove_reaction(...)
```

Cualquier envío admite `reply_to="wamid..."` para citar un mensaje. Se implementa como el
modificador `builders.as_reply`, que funciona con cualquier payload en vez de repetir el
argumento en cada builder.

El parser normaliza los mismos tipos al recibir: `message.location`, `message.reaction`
(con `.removed` cuando el usuario la retira) y `message.shared_contacts`. Cuidado con este
último: `message.contacts` es el perfil de **quien escribe**, no las tarjetas compartidas.

#### Reorganización interna

`messages/builders.py` y `webhook/parser.py` pasan a ser paquetes partidos por
responsabilidad. **Las rutas de import no cambian**: `from wacloud.messages import
builders` y `from wacloud.webhook.parser import parse_webhook` siguen funcionando igual, y
la suite de tests pasó sin tocarse tras el split.


#### Creación de plantillas completa

Antes `create()` era un pasamanos: el host escribía a mano el JSON de `components`, que es
justo la parte que Meta rechaza. Ahora hay builders para toda la estructura
(`templates.components` y `templates.buttons`), los 11 tipos de botón, y validación local
de todas las reglas documentadas.

El formato de las variables se deduce del texto en vez de declararse: `{{1}}` con una lista
de ejemplos, o `{{nombre}}` con un diccionario. Las formas asimétricas de `example` que
espera Meta —array plano en la cabecera, array de arrays en el cuerpo, cadena suelta en el
botón `COPY_CODE`— se generan solas.

`create()` valida antes de llamar, así que un nombre con mayúsculas o un ejemplo que falta
ya no consumen cupo de API.

#### Subida de medios

- `upload_media()` — `POST /{phone_number_id}/media`, devuelve el `media_id` para enviar.
- `upload_resumable()` — Resumable Upload API, devuelve el `handle` para crear plantillas
  con cabecera de medio. Usa `Authorization: OAuth` y cuerpo binario crudo, que es la
  excepción al resto de la Graph API.
- `get_media_metadata()` y `delete_media()`.

Los tamaños se validan antes de subir con los límites reales: **16 MB para vídeo**, no los
100 MB que se citan a menudo (esos son solo para documentos).

#### Parámetros de envío

`templates.parameters` cubre texto (posicional y con nombre), `currency`, `date_time`,
medios, ubicación y los botones (`url`, `quick_reply`, `copy_code`, `flow`, `catalog`,
`mpm`). Resuelve además dos contradicciones de la documentación de Meta: `index` va como
cadena y `sub_type` en minúscula.


#### Los errores traen el código de Meta

Meta dice explícitamente que hay que ramificar por `error.code`, nunca por el status HTTP
ni por `error_subcode` (deprecado desde v16.0). Ahora se expone:

```python
exc.code                 # 131049
exc.details              # error_data.details
exc.fbtrace_id           # para abrir soporte con Meta
exc.retryable            # decidido por el código, con el status como respaldo
exc.retry_after_seconds  # espera mínima que impone Meta
```

Esto arregla un comportamiento peligroso: antes, todo 429 y 5xx se reintentaba. Ahora
**no se reintentan nunca** `130403` (el negocio bloqueó al usuario) ni `131050` (opt-out de
marketing), y `131049` se propaga al host con sus 24 horas de espera en vez de reintentarse
tres veces en diez segundos, que añadía 4 días de penalización.

#### `verify_subscription`

Faltaba por completo el alta del webhook (`GET` con `hub.challenge`). Ver el README.

#### Otras

- `Transport` es context manager: `async with Transport() as t:`.
- `TemplatesClient.edit()` y `TemplatesClient.get()`.
- `SendResult.message_status`: `accepted`, `held_for_quality_assessment` o `paused`. Un
  envío `paused` **no se entrega**, aunque devuelva `message_id`.
- `BatchSendResult.code` con el código de Meta del fallo.
- `WebhookStatus` añade `error_code`, `pricing_category` y `callback_data`.
- `WebhookInboundMessage.replied_to` con el `wamid` citado.
- `wacloud.limits` con los límites documentados de Meta.
- `wacloud.recipient` público, con validación de E.164.
- `py.typed`: mypy en el host ya ve los tipos de la librería.
- Logging bajo el logger `wacloud.transport` en cada reintento.

### Bugs corregidos

- **Cache de plantillas que no expiraba.** La comparación de TTL era `>` en vez de `>=`, así
  que con un TTL bajo la entrada se servía siempre desde el cache.
- **`assert` como control de flujo** en el transporte. Con `python -O` los asserts
  desaparecen y la función devolvía `None` en vez de lanzar el error tras agotar reintentos.
- **Listado de plantillas incompleto** por no seguir la paginación.
- **`v19.0` expirada.**
