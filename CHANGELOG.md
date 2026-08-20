# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto sigue [versionado semántico](https://semver.org/lang/es/).

`MIGRATION.md` documenta con detalle los cambios que rompen la API y cómo adaptarse;
aquí queda el resumen por versión.

## [Sin publicar]

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
