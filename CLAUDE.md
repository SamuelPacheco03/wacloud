# CLAUDE.md

Guía para trabajar en `wacloud`. Léela antes de tocar código.

Dos mitades: la primera son las convenciones del proyecto; la segunda, las reglas de la
API de Meta que el código respeta y **por qué**. La segunda mitad no es documentación de
Meta reescrita: son las trampas concretas que ya nos han costado tiempo, con la fuente.

| | |
|---|---|
| **Empezar** | [Arranque rápido](#arranque-rápido) · [Glosario](#glosario-de-identificadores) |
| **Diseñar** | [Regla de oro](#regla-de-oro-la-librería-no-sabe-de-infraestructura) · [Arquitectura](#arquitectura-por-capas) · [Estado](#estado-qué-hay-y-qué-falta) |
| **Escribir** | [Convenciones](#convenciones-de-código) · [Anti-patrones](#anti-patrones) · [Errores](#errores) · [Tests](#tests) |
| **Entregar** | [Flujo de trabajo](#flujo-de-trabajo) · [Git](#git-y-commits) · [Checklist](#checklist-antes-de-dar-algo-por-terminado) |
| **Meta** | [Reglas de la API](#reglas-de-la-api-de-meta-que-el-código-debe-respetar) · [Sin verificar](#pendiente-de-verificar-contra-una-waba-real) |

## Qué es este proyecto

Librería Python **stateless** e **infra-agnóstica** para la [WhatsApp Cloud API](https://developers.facebook.com/documentation/business-messaging/whatsapp) de Meta.
Es un *paquete de librería*, no una aplicación: no tiene servidor, ni base de datos, ni
lectura de variables de entorno. Se instala en un host (p. ej. `siriusbot`) que aporta
las piezas de infraestructura por inyección.

Async-first (`httpx.AsyncClient`), multi-tenant por número de teléfono. Solo dos
dependencias de runtime: `httpx` y `pydantic`.

## Arranque rápido

```bash
pip install -e ".[dev]"
pre-commit install          # engancha los gates al commit
python scripts/check.py     # formato, lint, tipos y tests
```

Si `scripts/check.py` pasa, la CI pasa: ejecutan exactamente lo mismo.

## Glosario de identificadores

Meta usa media docena de identificadores parecidos y **no son intercambiables**.
Confundirlos produce errores que no dicen cuál es el problema.

| Identificador | Qué es | Dónde se usa |
|---|---|---|
| `phone_number_id` | El número emisor, dentro de la WABA | Enviar mensajes, medios, perfil |
| `waba_id` | La WhatsApp Business Account que agrupa números | Plantillas, listar números |
| `app_id` | La app de Meta (ni WABA ni número) | Resumable Upload |
| `wamid` | Un mensaje concreto (`wamid.HBg...`) | Responder, reaccionar, marcar leído |
| `media_id` | Un medio subido a la Media API | **Enviar** medios y plantillas |
| `handle` | Un medio subido a la Resumable Upload API (`4::aW1h...`) | **Crear** plantillas con cabecera |
| `flow_token` | Referencia propia que viaja al Flow y vuelve | Correlacionar la respuesta de un Flow |

Los dos últimos son la fuente de error más frecuente: un `media_id` no vale como
`header_handle` ni al revés. Ver [Crear y enviar](#crear-y-enviar-son-dos-mundos-distintos).

## Regla de oro: la librería no sabe de infraestructura

Estas tres cosas **nunca** deben aparecer en `wacloud/`:

1. `os.environ` / lectura de config global — la config entra por `GraphConfig`.
2. Acceso a base de datos o secretos — los tokens entran por `CredentialResolver`.
3. Dependencia de un framework web (FastAPI, Flask…) o de un SDK de nube (boto3, aioboto3)
   — el almacenamiento entra por `StorageBackend`.

Si una función necesita algo del mundo exterior, se define un `Protocol` y lo implementa
el host. Añadir una dependencia a `pyproject.toml` es una decisión de peso: hoy solo hay
`httpx` y `pydantic`, y así debe seguir salvo justificación fuerte.

**Tampoco es responsabilidad de la librería**, aunque la Cloud API lo requiera: deduplicar
webhooks (Meta reintenta 7 días), programar reintentos diferidos (los de 24 h), persistir
conversaciones, ni limitar el ritmo por destinatario. La librería expone lo necesario para
que el host lo haga —`retry_after_seconds`, `rate_limit_hook`, `wamid`— pero no guarda
estado.

## Arquitectura por capas

El flujo de dependencias es estrictamente hacia abajo. Una capa nunca importa de una
capa superior.

```
config · retry · errors · error_codes                ← núcleo sin dependencias internas
credentials · models · recipient · limits · flows
            ↓
     responses · transport                           ← única capa que hace I/O HTTP
            ↓
     builders (funciones puras)                      ← datos simples → dict de payload
            ↓
   clients (messages · templates · media · numbers)
            ↓
        webhook                                      ← parseo/verificación, sin red
```

| Módulo | Responsabilidad única |
|---|---|
| `config` | A dónde apunta la librería y timeouts de red. Sin secretos. |
| `retry` | Cuántas veces reintentar y cuánto esperar. Sustituible por el host. |
| `errors` | Jerarquía tipada. Cada error sabe si es reintentable y por qué. |
| `error_codes` | Tabla de códigos de Meta. Datos, sin lógica. |
| `recipient` | Normalización y validación del número de destino. |
| `limits` | Límites documentados de Meta, en un solo sitio. |
| `flows` | Enums de Flows. En la raíz porque los usan plantillas **y** mensajes. |
| `credentials` | Contrato `CredentialResolver`. La librería no resuelve tokens, los pide. |
| `models` | Resultados **normalizados** de Meta hacia el host. No payloads crudos. |
| `responses` | Interpretación de la respuesta HTTP: qué dice, no qué se hace con ella. |
| `transport` | HTTP + reintentos + backoff + mapeo de errores. Nada de negocio. |
| `messages/builders/` | **Funciones puras** por familia de mensaje. Cero I/O. |
| `messages/client.py` | Orquestación: resolver credenciales + delegar. Cero armado de payloads. |
| `templates/components.py` · `buttons.py` | Estructura de la plantilla al **crearla**. |
| `templates/parameters.py` | Valores concretos al **enviarla**. |
| `templates/placeholders.py` | Análisis y validación de las variables `{{...}}`. |
| `templates/definition.py` | Ensamblado y reglas que cruzan componentes. |
| `media/storage.py` | Contrato `StorageBackend`. |
| `media/upload.py` | Media API (media_id) y Resumable Upload (handle). Sistemas distintos. |
| `numbers/` | Administración del número: estado, registro, verificación, perfil. |
| `webhook/events.py` | Estructuras de los eventos normalizados. Sin lógica. |
| `webhook/extract.py` | Traducción del payload crudo a esos eventos. |
| `webhook/parser.py` | Recorrido de `entry[].changes[].value`. |
| `webhook/verify.py` | Alta de la suscripción y verificación HMAC. Sin red. |

**La separación builders/clients es la más importante y no se negocia.** Un builder que
haga red, o un client que arme un `dict` de Meta inline, es un error de diseño. Los builders
son testables sin mocks; los clients se testean con `httpx.MockTransport`.

## Estado: qué hay y qué falta

**Cubierto.** Envío de texto, los cinco tipos de medio, los cuatro interactivos (botones,
CTA, lista, Flow), ubicación, contactos, stickers, reacciones y respuestas citadas. Ciclo
de vida completo de plantillas (crear con validación local, editar, listar con paginación,
borrar) y los 11 tipos de botón. Subida de medios por los dos sistemas. Webhook entrante
normalizado. Gestión del número.

**Falta.** Mensajes de catálogo y producto (necesitan un catálogo de Commerce Manager) y
los webhooks de gestión más allá de `messages` —`message_template_status_update`,
`account_update`, `phone_number_quality_update`—, que hoy hay que leer de `raw`. El primero
es el que avisa de si Meta aprobó una plantilla, así que es el candidato natural.

## Convenciones de código

- `from __future__ import annotations` en todos los módulos. Sintaxis `X | None` (target 3.10+).
- Type hints completos en toda API pública. La librería exporta tipos vía `py.typed`.
- Argumentos keyword-only (`*`) para todo lo que no sea el sujeto de la operación:
  `send_text(to, body, *, phone_number_id=...)`.
- Docstrings que explican el **porqué** y las reglas de Meta, no el qué.
  Un docstring útil dice "Meta prioriza `media_id` sobre `link`", no "envía una imagen".
- Nombres de dominio en inglés (los de la API de Meta: `phone_number_id`, `waba_id`,
  `wamid`); prosa y comentarios en español.
- Sin `print`. Sin estado global mutable. Sin singletons.
- Pydantic: campos por defecto con `Field(default_factory=...)`, nunca `= []` ni `= {}`.

### Estricto al construir, permisivo al parsear

Es el principio que gobierna toda la validación:

- **Al construir un payload**: si un valor incumple un límite documentado de Meta, se lanza
  `ValueError`. Nunca se recorta en silencio — el destinatario recibiría algo distinto de lo
  que el host pidió y no quedaría rastro en ningún log.
- **Al parsear una respuesta o un webhook**: un campo con forma inesperada se descarta, no
  tumba el lote. Meta manda hasta 1000 actualizaciones por POST y añade campos entre
  versiones.

Corolario: los campos enumerados de una respuesta se guardan como `str`, no como `Enum`.
Meta se contradice consigo misma (`NOT_VERIFIED` frente a `UNVERIFIED`, `UNCONNECTED`
frente a `DISCONNECTED`), y un enum estricto convertiría una discrepancia de documentación
en una excepción en producción. **Los enums existen para comparar, no para convertir.**

### Límites de tamaño

Ningún archivo de funciones debe pasar de ~250 líneas, ni ninguna función de ~40. Al
crecer se parte por familia exponiendo un paquete con el mismo API público: así están ya
`messages/builders/` (media, interactive, contacts, location, reactions…) y `webhook/`
(events, extract, parser).

La señal para partir es que un archivo mezcle responsabilidades, no el número de líneas
en sí. Una clase cohesionada puede pasar de 250 —`TemplatesClient` y `MessagesClient` lo
hacen— porque trocear una clase entre archivos perjudica más de lo que ayuda. Un módulo de
funciones que roza el límite, en cambio, casi siempre esconde dos familias mezcladas.

Al partir, `__init__.py` reexporta todo y el API pública no cambia: **si hay que tocar los
tests para acomodar un split, el split está mal hecho.**

### Nada de acoplamiento a símbolos privados

Un módulo **no importa un `_nombre` de otro módulo**. Si dos módulos necesitan el mismo
helper, ese helper es público y vive en un sitio compartido: por eso `recipient.py`,
`limits.py` y `flows.py` están en la raíz del paquete, y por eso `media_object()` e
`interactive_message()` no llevan guion bajo.

Un import circular casi nunca se arregla moviendo el import: señala que algo está en la
capa equivocada. `FlowAction` vivía en `templates/enums.py` y lo necesitaba `messages/`;
la solución no fue un import diferido sino sacarlo a `wacloud/flows.py`, porque los Flows
no son un concepto de plantillas.

### Anti-patrones

Todos estos estuvieron en el código y costaron un bug real. Si aparece uno, es regresión.

| No hagas | Por qué | En su lugar |
|---|---|---|
| Recortar un valor que excede un límite | El receptor recibe algo distinto de lo que el host pidió, sin rastro en logs | `raise ValueError` con el límite y el valor |
| `assert` como control de flujo | `python -O` los elimina; la función devolvía `None` en vez de lanzar | `if ...: raise` |
| Convertir a `Enum` un campo de respuesta | Meta se contradice en la ortografía; revienta en producción | Guardar `str`, comparar con el enum |
| Ramificar por status HTTP | El mismo 400 puede ser permanente o reintentable en 24 h | Ramificar por `error.code` |
| Duplicar la versión en dos ficheros | Se sincronizó a mano seis veces; se desincroniza seguro | `[tool.hatch.version]` lee `__init__.py` |
| Llamar `list` a un método | Sombrea el builtin y rompe las anotaciones `list[...]` posteriores | `list_all` |
| Inventar un límite que Meta no publica | Rechaza en local valores que Meta acepta | No validar, y dejarlo escrito |
| Paginar solo la primera página | Devuelve listas incompletas en silencio | Seguir `paging.cursors.after` mientras haya `next` |

## Errores

El host debe poder decidir qué hacer **sin parsear strings**:

- `WaTransportError` — fallo de red antes de respuesta. Reintentable.
- `WaRateLimited` — límite de ritmo de Meta, con `retry_after_seconds`. Reintentable.
- `WaServerError` — 5xx de Meta. Reintentable.
- `WaInvalidRequest` — rechazo definitivo. **No** reintentable.

Todo error lleva `status_code`, `body`, `code` (el de Meta), `details` y `fbtrace_id`. Al
añadir información de error, se expone como atributo tipado, nunca embebida en el mensaje.

La clase se elige por el **código de Meta** antes que por el status: `131050` (opt-out)
llega con HTTP 429, y clasificarlo como `WaRateLimited` daría un error "reintentable" que
no debe reintentarse nunca.

## Tests

- `pytest` + `pytest-asyncio` en modo `auto` (no hace falta decorar con `@pytest.mark.asyncio`).
- **Nunca red real.** Los clients se testean con `httpx.MockTransport`; los builders,
  llamándolos directamente y comprobando el `dict`.
- El cableado común vive en `tests/factories.py`. Si un test monta un cliente a mano, es
  señal de que falta un factory:

| Factory | Para qué |
|---|---|
| `make_transport(handler)` | Transport sobre `MockTransport` |
| `make_messages_client` · `make_templates_client` | Cliente listo con resolver estático |
| `capturing_handler(respuesta)` | `(capturado, handler)`: registra `path`, `method`, `params`, `body` |
| `accepted_handler()` | Simula un envío aceptado (`wamid.OK`) |
| `ok_handler()` | Responde 200 sin inspeccionar nada |
| `fast_policy(n)` | Política de reintentos sin esperas |

- Todo builder nuevo necesita un test que verifique la forma exacta del payload contra la
  doc de Meta. **Un builder sin test es un payload que Meta rechazará en producción.**
- Los tests que fijan una decisión deliberada (no validar algo, aceptar dos formas) llevan
  un docstring explicando por qué, para que nadie los "arregle" después.

Los dos patrones a copiar:

```python
# Builder: comprobar la forma exacta contra la doc de Meta.
def test_positional_body_example_is_a_list_of_lists():
    """Meta espera [["a", "b"]] en el cuerpo: doble corchete."""
    component = components.body("Hola {{1}}, tu pedido {{2}}.", examples=["Ana", "A-1"])
    assert component["example"] == {"body_text": [["Ana", "A-1"]]}


# Cliente: comprobar el endpoint y el cuerpo que sale por la red.
async def test_send_location_posts_expected_payload():
    captured, handler = accepted_handler()
    await make_messages_client(handler).send_location(
        "573001112233", phone_number_id="PNID", latitude=4.711, longitude=-74.07
    )
    assert captured["body"]["type"] == "location"
```

Y el patrón para verificar que **no** se hace una llamada:

```python
async def test_create_rejects_invalid_template_before_calling_meta():
    """Meta limita a 100 creaciones/hora: no se gasta cupo en algo inválido."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={})

    with pytest.raises(ValueError):
        await client.create(...)
    assert calls["n"] == 0
```

## Flujo de trabajo

Un solo comando ejecuta todo lo que ejecuta la CI:

```bash
python scripts/check.py          # formato, lint, tipos y tests
python scripts/check.py --fix    # además arregla formato y lint
```

Por separado, si hace falta:

```bash
python -m ruff format .
python -m ruff check --fix .
python -m mypy wacloud/
python -m pytest -q --cov=wacloud
```

`mypy` corre en modo `strict` y la cobertura tiene un mínimo del 90 %. Los cuatro deben
pasar antes de dar por terminado un cambio.

La CI (`.github/workflows/ci.yml`) repite lo mismo sobre Python 3.10, 3.11, 3.12 y 3.13, y
además comprueba que `py.typed` viaja dentro del wheel — sin ese fichero el host pierde
todos los tipos y el fallo es silencioso.

### Git y commits

- **Nunca commitear directo a `main`.** Rama por trabajo, y merge con `--no-ff` para que el
  punto de integración quede en el historial y se pueda revertir de una pieza.
- Prefijos: `feat`, `fix`, `refactor`, `test`, `docs`, `build`, `chore`.
- El asunto va en imperativo y en minúscula, sin punto final.
- **El cuerpo explica el porqué, no el qué** — el diff ya dice qué cambió. Si el commit
  arregla un bug, describe el modo de fallo: "Meta no devuelve error al expirar una
  versión, redirige en silencio" vale más que "actualiza la versión de la API".
- Cada commit debe pasar los gates **por sí solo**: un punto de `git bisect` roto es peor
  que un commit grande. Si el trabajo no se puede partir sin romper commits intermedios,
  va en uno solo y se explica en el cuerpo.
- Antes de `push`, `python scripts/check.py` sobre la rama ya mergeada. No se publica un
  `main` roto.

### Versionado

La versión vive **solo** en `wacloud/__init__.py`; `pyproject.toml` la lee de ahí con
`[tool.hatch.version]`. No la dupliques.

Al publicar: subir `__version__`, añadir la entrada en `CHANGELOG.md` y, si hay cambios que
rompen, documentarlos en `MIGRATION.md` con el antes/después.

## Añadir soporte para un tipo de mensaje o endpoint nuevo

1. Confirmar la forma exacta del payload en la doc oficial de Meta (enlazarla en el docstring).
2. Escribir el **builder puro** y su test.
3. Añadir el método al client correspondiente — debe ser un delegado fino al builder.
4. Exportarlo en el `__init__.py` del módulo y en el `__all__` raíz.
5. Actualizar `CHANGELOG.md`.

## Checklist antes de dar algo por terminado

- [ ] `python scripts/check.py` en verde (formato, lint, mypy strict, tests ≥90 %).
- [ ] El builder nuevo tiene un test que fija la forma del payload contra la doc de Meta.
- [ ] Los docstrings explican reglas de Meta, no lo que hace el código.
- [ ] Ningún archivo de funciones supera ~250 líneas, ninguna función ~40.
- [ ] Nada nuevo en `__all__` sin exportar también en el `__init__.py` del módulo.
- [ ] Si rompe el API pública: nota en `MIGRATION.md` con el antes/después.
- [ ] `CHANGELOG.md` actualizado.
- [ ] Si algo quedó sin verificar contra Meta, añadido a [la tabla del final](#pendiente-de-verificar-contra-una-waba-real).

## Compatibilidad

`wacloud` es consumida por un host externo. Renombrar o quitar algo de `__all__` rompe al
consumidor: si hay que hacerlo, es un cambio de versión menor con nota en `MIGRATION.md`,
no un retoque silencioso.

---

# Reglas de la API de Meta que el código debe respetar

Verificado contra la documentación oficial en agosto de 2026. La doc canónica se movió a
`developers.facebook.com/documentation/business-messaging/whatsapp/...`; añadir `.md` a
cualquier URL devuelve el markdown crudo (útil para detectar cambios de esquema).

## Versionado — trampa crítica

Al expirar una versión de la Graph API **las llamadas no fallan**: Meta las redirige en
silencio a la última versión funcional. El comportamiento cambia sin error. Por eso la
versión se fija explícitamente y se revisa cada release.

`v19.0` expiró el 21 may 2026. `v20.0` expira el 24 sep 2026. Usar **`v25.0` o superior**.

## Crear y enviar son dos mundos distintos

Meta llama `components` a dos cosas que no se parecen, y confundirlas es el error más
fácil de cometer en esta parte del código:

- **Crear** (`POST /{waba_id}/message_templates`): los componentes describen la estructura
  y llevan `example`. Los construye `templates/components.py`.
- **Enviar** (`POST /{pnid}/messages`): los componentes llevan `parameters` con los valores
  concretos. Los construye `templates/parameters.py`.

La misma dualidad afecta a los medios: crear una plantilla con cabecera de imagen exige un
**handle** de la Resumable Upload API; enviarla exige un **media ID** de la Media API. Son
sistemas separados y sus identificadores no son intercambiables.

## Asimetrías de payload que causan la mayoría de los bugs

Al crear plantillas, los campos `example` **no tienen la misma forma**:

```jsonc
"header_text": ["Pablo"]                    // array plano
"body_text": [["Pablo", "860198-230332"]]   // array de arrays (doble corchete)
"header_handle": ["4::aW1hZ2UvanBlZw==..."] // array plano
{ "type": "URL", "example": ["summer2023"] }  // array plano, sin envolver en "example":{}
{ "type": "COPY_CODE", "example": "250FF" }   // string desnudo
```

Otras trampas confirmadas:

- Resumable Upload usa `Authorization: OAuth`, **no `Bearer`**, y el cuerpo es binario crudo
  sin multipart. El paso 1 exige `file_name`, que casi todas las guías omiten.
- La `url` que devuelve `GET /{media_id}` **caduca a los 5 minutos**. Un 404 al descargar
  significa URL caducada: hay que volver a resolver el ID, no reintentar la misma URL.
- Vídeo: **16 MB**, no 100 MB. Los 100 MB son solo para documentos.
- `index` de botón va como **string** (`"0"`) y `sub_type` en **minúscula**.
- Al editar una plantilla se reemplaza el array `components` **entero**; no hay edición parcial.
- El nombre de una plantilla solo admite `^[a-z0-9_]+$`. Con mayúsculas o espacios, Meta
  responde un error 100 sin explicar la causa.
- Una lista interactiva admite 10 filas **en total** entre todas las secciones, no 10 por
  sección. Y su cabecera solo acepta texto, a diferencia del resto de interactivos.

## Validar en local antes de llamar

Meta limita la creación a 100 plantillas por hora y WABA, y el rechazo llega por webhook
minutos u horas después. Todo lo que se pueda comprobar sin red se comprueba: longitudes,
secuencia de variables, coherencia del formato, cupos de botones, tamaño de los medios.

**No se valida lo que Meta no documenta.** Los límites de caracteres del perfil de negocio
son el caso claro: la página que los publicaba devuelve un error del lado de Meta y los
números que circulan vienen de terceros, así que aquí no se comprueban. Inventar un límite
rechazaría en local valores que Meta acepta.

Ante una regla ambigua, se valida solo donde el rechazo está documentado. Dos ejemplos ya
resueltos así: la regla de "no empezar ni acabar en variable" se aplica al cuerpo pero no a
la cabecera (Meta aprueba `"Pedido {{1}}"`), y la creencia de que dos variables no pueden
ser adyacentes no se valida porque no aparece en ninguna página de Meta. Ser más estricto
que Meta bloquea plantillas legítimas.

## Errores: ramificar por `error.code`

Meta lo dice explícitamente: construir el manejo de errores sobre **`error.code`**, nunca
sobre `error_subcode` (deprecado desde v16.0) ni sobre el status HTTP. El mismo HTTP 400
puede ser un fallo permanente o algo que se reintenta tras 24 horas.

Reintentables: `2`, `4`, `80007`, `80008`, `130429`, `131000`, `131016`, `131056`, `131057`,
`133004`, `133015`, `133016`, `2494100`.
**No reintentar nunca:** `130403` (el negocio bloqueó al usuario), `131050` (opt-out de marketing).
Caso especial: `131049` exige esperar **≥24 h** — reintentar antes añade otras 24 h de castigo.

**`Retry-After` no está documentado por Meta en ninguna parte.** El mecanismo real es
`estimated_time_to_regain_access` (minutos) dentro del header `X-Business-Use-Case-Usage`,
más el backoff que Meta sí recomienda: **4^X segundos** (1, 4, 16, 64, 256). Leer `Retry-After`
si viene está bien como oportunismo, pero no puede ser la única estrategia.

## Rate limits que importan

- **Pair rate limit:** 1 mensaje cada 6 s al *mismo* usuario (~600/hora) → error `131056`.
  Ráfagas de hasta 45 permitidas, pero se "toman prestadas" del cupo futuro.
- **Throughput:** 80 mps por número (1.000 con upgrade automático), **incluye entrantes y
  salientes** → error `130429`.
- **Gestión (plantillas y números):** 200 peticiones/hora por WABA, o 5.000 si tiene un
  número registrado. Además, 100 creaciones de plantilla/hora (`80008`).
- **Registro/baja de número:** 10 operaciones por número cada 72 h (`133016`).

## Webhooks

- La firma se calcula sobre el **body crudo en bytes**. Reserializar el JSON parseado cambia
  orden y escapes, y el HMAC no cuadra. Comparación en tiempo constante siempre.
- **`delivered` puede no llegar nunca.** Si el usuario está en la pantalla del chat, Meta manda
  `read` sin `delivered`. Una máquina de estados que exija el orden se atasca.
- Los estados son exactamente cinco: `sent`, `delivered`, `read`, `failed`, `played`.
- Meta reintenta durante 7 días y reparte a todas las apps suscritas: **hay que deduplicar**
  (en el host, no aquí).
- Una reacción entrante **sin** campo `emoji` significa que el usuario la retiró; Meta
  omite el campo en vez de mandarlo vacío.
- `value.contacts` es el perfil de **quien escribe**; `message.contacts` son las tarjetas
  que ha compartido. Mismo nombre, cosas distintas: en el parser son `contacts` y
  `shared_contacts`.
- `nfm_reply.response_json` es una cadena JSON **dentro** del JSON: necesita un segundo
  `json.loads`. La respuesta de un Flow no trae el `flow_id`, así que correlacionar exige
  haber enviado un `flow_token` propio.
- `conversation` desaparece en v24.0+ salvo free entry point: para correlacionar, usar
  `biz_opaque_callback_data`.

## Al implementar algo nuevo

La doc de Meta se contradice a sí misma en varios sitios (mayúsculas de `sub_type`, `index`
como int o string, enums incompletos). Ante una discrepancia, seguir el ejemplo de la página
más reciente y **dejar constancia en el docstring** de cuál se eligió y por qué.

## Pendiente de verificar contra una WABA real

Estos puntos están implementados según la mejor lectura de la documentación, pero Meta no
los publica con claridad. Al validarlos empíricamente, actualizar el docstring
correspondiente y borrar la fila de esta tabla:

| Punto | Dónde | Duda |
|---|---|---|
| Retirar reacción con `emoji: ""` | `builders/reactions.py` | Ya no aparece en la doc actual; funcionaba antes. |
| `flow_action_payload.data` | `builders/interactive_flow.py` | Meta lo muestra como objeto y como cadena JSON en páginas distintas. Se manda objeto. |
| Forma de `throughput` | `numbers/models.py` | La referencia vigente ya no la publica. Se aceptan entero y `{"level": ...}`. |
| Default de `product_policy` | `templates/builders.py` | No documentado. Conviene fijarlo explícito. |
| Límites del perfil de negocio | `numbers/client.py` | La página de Meta devuelve error. No se validan. |
| Regex de parámetros con nombre | `templates/placeholders.py` | Meta lo describe en prosa; no está claro si admite dígitos. |
