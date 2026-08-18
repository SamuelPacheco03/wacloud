# wacloud

Cliente **stateless** e infra-agnóstico para la [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api) de Meta.

La librería no conoce bases de datos, variables de entorno globales ni frameworks web.
Recibe las credenciales por número mediante un `CredentialResolver` inyectado y el
almacenamiento de medios mediante un `StorageBackend` inyectado. El host (p. ej. sirius_bot)
aporta esas implementaciones (DB con tokens cifrados, Cloudflare R2, etc.).

## Módulos

- `config` — `GraphConfig` (base URL, versión de la Graph API). Sin secretos.
- `transport` — un único `httpx.AsyncClient` con keep-alive, reintentos con backoff
  (429/5xx + `Retry-After`) y errores tipados.
- `credentials` — `WaCredentials` + protocolo `CredentialResolver`.
- `errors` — jerarquía de errores (`WaCloudError` y derivados).
- `media` — protocolo `StorageBackend` + descarga de medios de Meta (fases siguientes).
- `messages`, `templates`, `webhook` — fases siguientes.

## Estado

Fase 0: andamiaje (transport + contratos). Ver
`docs/whatsapp_meta_integration_spec.md` en el repo host para el plan completo.

## Instalación (modo editable)

```bash
pip install -e ./packages/wacloud
# con extras de desarrollo:
pip install -e "./packages/wacloud[dev]"
```
