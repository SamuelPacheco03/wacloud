# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto sigue [versionado semántico](https://semver.org/lang/es/).

`MIGRATION.md` documenta con detalle los cambios que rompen la API y cómo adaptarse;
aquí queda el resumen por versión.

## [0.12.0] — 2026-09-07

El botón `REQUEST_CONTACT_INFO`. La 0.11.0 hizo que dejaran de perderse los mensajes de
quien escribe sin teléfono; esta añade la forma **explícita** de pedírselo, que es lo
único que permite unir el BSUID con un número real.

### Añadido

- **`builders.build_request_contact_info` y `MessagesClient.send_request_contact_info`**:
  el interactivo `request_contact_info`, que enseña el botón nativo de WhatsApp para
  compartir el contacto. El botón no se puede personalizar, así que el único texto que se
  controla es el cuerpo.
- **`buttons.request_contact_info()` y `ButtonType.REQUEST_CONTACT_INFO`**: el mismo botón
  dentro de una plantilla. Es el único botón sin `text` de toda la librería, porque Meta
  no deja ponerle etiqueta. Solo se admite en categorías utility y marketing. No se valida
  ningún cupo: Meta no publica ninguno.
- **`WebhookInboundMessage.contact_cards`**: las tarjetas de `shared_contacts` ya
  desanidadas, en `InboundContactCard` (`phone`, `wa_id`, `origin`, `name`, `vcard`).
  Antes el teléfono había que sacarlo de `contacts[0]["phones"][0]["wa_id"]`, o sea
  conociendo la forma de Meta, que es justo lo que esta librería evita.
- **`WebhookInboundMessage.requested_phone`**: el número que el usuario compartió **porque
  se lo pedimos**. Es la pieza que une las dos identidades en una línea. Devuelve `None`
  si la tarjeta la compartió por su cuenta (`origin: "other"`): ese número puede ser el de
  un tercero, y darlo por suyo asociaría a un cliente el teléfono de otra persona.
- `CONTACT_ORIGIN_REQUEST` y `CONTACT_ORIGIN_OTHER`, para comparar sin literales sueltos.

### Cambiado

- **El texto de un mensaje `contacts` sin nombre ya no es `[contacto recibido]`**: ahora es
  el número. Una respuesta al botón no trae nombre —solo teléfono—, así que el marcador
  genérico escondía precisamente el dato por el que se había preguntado. Cuando la tarjeta
  sí trae nombre no cambia nada.

## [0.11.0] — 2026-09-07

Nombres de usuario de WhatsApp. Un usuario con username puede llegar **sin teléfono**, y
el parser lo descartaba entero y en silencio: se perdieron conversaciones durante días sin
dejar una línea de log.

### Corregido

- **El parser ya no exige `from`.** Un mensaje identificado solo por `from_user_id` —el
  BSUID, `CO.2452497711827233`— se parsea igual. Meta omite `wa_id` y `from` cuando el
  usuario tiene nombre de usuario y además no ha escrito a ese número en 30 días, no está
  en la agenda, o el negocio le escribió al BSUID. `from_user_id`, en cambio, viene
  siempre.
- **Un mensaje sin `metadata.phone_number_id` ya no se salta el bucle sin dejar rastro**:
  se anota como descarte, con el motivo.

### Añadido

- **`WebhookEvents.discarded`.** Lo que el parser no supo normalizar deja de desaparecer:
  cada `WebhookDiscarded` lleva `kind`, `reason` —un código estable, no prosa— y el `raw`
  para poder reprocesarlo. Un lote vacío y un lote perdido se veían exactamente igual
  desde fuera, y ese es el motivo de que el fallo tardara días en detectarse.
- **Identidad en el evento entrante**: `from_user_id` (el BSUID), `from_phone` (el
  teléfono, o `None` si Meta no lo mandó), `username` y la propiedad `has_phone_number`.
- **`WebhookStatus.recipient_user_id`**: el BSUID del destinatario, que Meta pone siempre,
  se hubiera enviado el mensaje al teléfono o al BSUID.
- **Envío a un BSUID.** `recipient_block` reconoce la forma `CO.…` y la manda por
  `recipient` en vez de por `to`, que es donde la espera Meta. Al vivir en `recipient.py`
  lo heredan los catorce builders sin tocar ninguna firma. Antes, un BSUID en `to` moría
  con un «tiene 16 dígitos, E.164 permite 15».
- **Bloqueo por BSUID**: `BlockedUsersClient.block` y `unblock` mandan `user_id` en vez de
  `user` cuando toca. `succeeded` y `list_all` devuelven el `wa_id` si lo hay y el BSUID si
  no, en vez de perder la fila.
- **`is_user_id`**, exportado, para el host que necesite ramificar.
- Un BSUID pasado en el `to` de `build_marketing_template` se reencamina a `recipient` en
  vez de quedarse en sus cifras.

### Notas

`from_user` **sigue siendo `str` y sigue viniendo relleno**: es el teléfono cuando lo hay y
el BSUID cuando no. `send_text(msg.from_user, …)` funciona en los dos casos, así que el
host puede desplegar sin coordinar el cambio. Ver `MIGRATION.md`.

## [0.10.1] — 2026-09-03

Solo documentación: **el código es idéntico al de la 0.10.0**. Se publica porque lo que
cambia es el `README`, y el `README` no viaja en un tag que se cortó antes de escribirlo.

### Añadido

- **La convención de retorno, en el `README`.** Estaba solo en `CLAUDE.md`, que lee quien
  toca el código, y no donde lee quien usa la librería. Va dentro de «Uso», con las tres
  formas —modelo, `list[X]` y `bool`— corriendo en un ejemplo ejecutado, no escrito de
  memoria.

### Corregido

- El `pip install` del arranque fijaba `v0.8.0`: llevaba dos versiones sin tocarse, así que
  copiar y pegar esa línea instalaba una librería más vieja que su propia documentación.
- «`MIGRATION.md` hoy cubre 0.1 → 0.2 y 0.6 → 0.7» no mencionaba el 0.9 → 0.10.

## [0.10.0] — 2026-09-03

### Cambiado (rompe)

- **`TemplatesClient.edit`, `TemplatesClient.delete` y `MessagesClient.mark_read` devuelven
  `bool`** en vez del `dict` crudo de Meta. Los tres respondían un acuse `{"success": true}`,
  así que lo único que aportaba el diccionario era obligar al host a leer la forma de Meta.
  Ver `MIGRATION.md`.

  Eran las tres únicas excepciones de los 40 métodos públicos: el resto ya devolvía un
  modelo, una `list[X]` o un `bool`.

### Añadido

- **La convención de retorno, escrita** en `CLAUDE.md`: un recurso es un modelo tipado, una
  colección es una `list[X]` ya paginada entera, y una operación es un `bool`. Un cliente
  nunca devuelve el `dict` crudo de Meta. En el `README` llega en la 0.10.1.

- **`tests/test_contrato.py`**, que la comprueba recorriendo las clases de verdad, así que
  un método nuevo entra solo. Es la diferencia entre una costumbre y un contrato: la regla
  se cumplía en 37 de 40 métodos y las tres excepciones sobrevivieron varias versiones sin
  que nada se quejara.

## [0.9.0] — 2026-09-02

### Añadido

- `InboundMedia.animated`: si el WebP de un sticker entrante está animado. Meta lo manda
  solo para stickers, así que en el resto de medios es `None` —que significa "no aplica",
  no "estático"—. Importa al pintarlo: un sticker animado y uno estático no se muestran
  igual, y hasta ahora había que sacarlo de `raw`.

  Solo se acepta un booleano de verdad. Un `bool(valor)` convertiría la cadena `"false"`
  en `True`, que es justo el error que pintaría mal el sticker.

### Corregido

- El docstring de `build_sticker` decía que el límite de tamaño del sticker «se comprueba
  al subir». **No se comprueba en ninguna parte**, y `ensure_within_size_limit` ya lo
  explicaba en sentido contrario: un sticker comparte el MIME `image/webp` con una imagen
  y desde los bytes no se sabe si está animado, así que se aplica el límite permisivo de
  imagen (5 MB) y Meta rechaza el caso concreto.

  El código siempre hizo lo segundo; el docstring prometía una garantía inexistente. Un
  WebP de 3 MB pasa la validación local y lo rechaza Meta: quien quiera fallar antes tiene
  que medirlo en el host.

## [0.8.0] — 2026-08-26

Lo que faltaba para dar de alta la WABA de un cliente sin tocar el panel de Meta.

### Añadido

- `WabaClient`: `subscribe`, `list_subscriptions`, `unsubscribe` y `get`. **Sin suscribir
  la app a una WABA, Meta no entrega ni un solo webhook de esa cuenta**, y no avisa de
  ello. `subscribe` admite `override_callback_uri` + `verify_token` para que cada cuenta
  entregue a su propia URL.
- `OAuthClient.exchange_code`: canje del código de Embedded Signup por el token de
  negocio. El código es de un solo uso, así que la petición no se reintenta ante un fallo
  de red.
- `BlockedUsersClient`: `block`, `unblock` y `list_all`. `BlockResult` separa aceptados de
  rechazados porque Meta responde por usuario, no por lote.

### Cambiado

- `Transport.request` acepta `access_token=None` para omitir la cabecera `Authorization`.
  Lo necesita un solo endpoint —`/oauth/access_token`, donde las credenciales son el
  propio `client_secret`—; para todo lo demás el token sigue siendo obligatorio.

## [0.7.0] — 2026-08-21

El veredicto de las plantillas llega solo, un envío se puede reconocer al volver, y ya no
se duplica ante un fallo ambiguo. Hay un cambio de comportamiento; está en `MIGRATION.md`.

### Añadido

- `message_template_status_update` en el webhook: `WebhookEvents.template_statuses`
  con `WebhookTemplateStatus`. Es el único aviso de que Meta aprobó o rechazó una
  plantilla — el nodo de la Graph API dice el estado actual pero no avisa del cambio,
  y la revisión tarda de minutos a días. Antes había que leerlo de `raw` o sondear.
- `builders.with_callback_data`: adjunta `biz_opaque_callback_data` a cualquier
  payload. Meta lo devuelve intacto en el webhook de estado, así que correlacionar un
  estado con la fila que lo originó deja de depender del `wamid` — que solo se conoce
  **después** de que Meta acepte el envío.
- `Transport.request(idempotent=...)` para declarar qué no se puede repetir.
- Integración continua en GitHub Actions: tests sobre Python 3.10–3.13, formato, lint,
  tipos y comprobación de que `py.typed` viaja en el wheel.
- Configuración de `pre-commit` con los mismos gates.
- `scripts/check.py`: ejecuta formato, lint, tipos y tests en un comando.
- Umbral mínimo de cobertura (90 %); antes podía bajar sin que nadie se enterara.
- `ruff format` como formateador. Hasta ahora solo había linter y el estilo dependía
  de quien escribiera.
- `CHANGELOG.md` y `LICENSE`.

### Cambiado

- **Un envío ya no se reintenta ante un fallo ambiguo.** `MessagesClient` marca
  `POST /{phone_number_id}/messages` como no idempotente, así que un timeout, una
  conexión caída o un 5xx sin código reconocible de Meta se propagan en vez de
  reintentarse: ninguno de los tres demuestra que Meta rechazara la petición, y
  repetirla cuando sí la procesó le manda al destinatario el mismo mensaje dos veces.
  Lo que Meta rechaza explícitamente (429, `130429`, `131056`…) se sigue reintentando
  igual, y las lecturas y la gestión de plantillas no cambian.
  Un host que dependa del reintento en esos casos verá ahora el error: es lo que le
  permite decidir con su propio estado, que la librería no tiene.
- La versión tiene una sola fuente de verdad (`wacloud/__init__.py`); `pyproject.toml`
  la lee de ahí. Antes estaba duplicada y se sincronizaba a mano.
- `tests/` es un paquete: `from tests.factories import ...` ya no depende de que el
  directorio actual esté en `sys.path`.
- Helpers de captura de peticiones unificados en `tests/factories.py`; estaban
  duplicados en tres archivos.

## [0.6.0]

### Añadido

- `NumbersClient`: estado del número, listado de la WABA con paginación, alta y baja,
  PIN de dos pasos, verificación por SMS o llamada, y perfil de negocio.

## [0.5.0]

### Añadido

- Mensajes interactivos de lista (`send_list`) y de Flow (`send_flow`), con validación
  del tope de 10 filas **en total** entre todas las secciones.
- `message.interactive` en el webhook, con el `id` elegido y el segundo parseo de
  `response_json` para las respuestas de Flow.

### Cambiado

- `FlowAction` y `FlowIcon` se mueven de `templates.enums` a `wacloud.flows`: los usan
  tanto las plantillas como los mensajes, y dejarlos en `templates` invertía las capas.
  Se siguen reexportando desde el sitio antiguo.

## [0.4.0]

### Añadido

- Ubicación, contactos, stickers y reacciones, al enviar y al recibir.
- `reply_to` en todos los envíos, vía el modificador `builders.as_reply`.

### Cambiado

- `messages/builders.py` y `webhook/parser.py` pasan a ser paquetes partidos por
  responsabilidad. Las rutas de import no cambian.

## [0.3.0]

### Añadido

- Creación de plantillas completa: builders de componentes y los 11 tipos de botón, con
  las formas asimétricas de `example` generadas automáticamente.
- Validación local de las reglas de Meta antes de gastar cupo de API.
- Subida de medios (Media API) y Resumable Upload API para las cabeceras de plantilla.
- `templates.parameters` para el envío de plantillas aprobadas.

## [0.2.0]

### Corregido

- La versión de la Graph API sube de `v19.0` (expirada el 21-05-2026) a `v25.0`. Meta no
  devuelve error al expirar una versión: redirige en silencio, así que el comportamiento
  era indeterminado.
- El caché de plantillas no expiraba: la comparación de TTL usaba `>` en vez de `>=`.
- `assert` como control de flujo en el transporte, que `python -O` elimina.
- El listado de plantillas se quedaba en la primera página.

### Cambiado

- Los errores se clasifican por `error.code` de Meta y no por el status HTTP. Los códigos
  `130403` y `131050` ya no se reintentan nunca, y `131049` se propaga con sus 24 h de
  espera en vez de reintentarse tres veces en diez segundos.
- `RetryPolicy` se separa de `GraphConfig`. Backoff `4^X`, que es lo que recomienda Meta.
- Los builders fallan en vez de recortar en silencio.

### Añadido

- `verify_subscription` para el alta del webhook, que faltaba por completo.
- `py.typed`, `wacloud.limits`, `wacloud.recipient`.

## [0.1.0]

Extracción inicial de `wacloud` desde `siriusbot` como paquete independiente.
