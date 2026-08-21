# wacloud es una **librería**, no un servicio: esta imagen no se despliega.
#
# Existe para dos cosas concretas, y por eso son dos etapas con nombre:
#
#   docker build --target dist  -t wacloud:dist  .   # produce el wheel en /dist
#   docker build --target check -t wacloud:check .   # corre formato, lint, tipos y tests
#
# La primera sirve cuando hay que instalar la librería donde no llega PyPI ni git —
# un runner sin red, una imagen base propia—. La segunda reproduce la CI sin depender
# de qué Python tenga la máquina, que es justo lo que se quiere al depurar un fallo
# que solo pasa en el runner.
#
# Se fija 3.10 a propósito: `pyproject.toml` declara >=3.10 y es la versión más baja
# que hay que soportar. Un fallo de compatibilidad tiene que salir aquí y no en el
# host que menos suerte tenga.
FROM python:3.10-slim AS base

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /src

COPY pyproject.toml README.md LICENSE ./
COPY wacloud ./wacloud


# --- El wheel, para quien no puede instalar desde git ---------------------------
FROM base AS builder

RUN pip install build && python -m build --wheel --outdir /dist

FROM scratch AS dist
COPY --from=builder /dist /dist


# --- Los gates, tal como los corre la CI ----------------------------------------
FROM base AS check

COPY scripts ./scripts
COPY tests ./tests

# Se instala el paquete y no solo sus dependencias: los tests importan `wacloud`, y
# ejecutarlos contra el árbol de fuentes en vez de contra lo instalado es cómo se cuela
# un módulo que funciona en local y falta en el wheel — que es exactamente el fallo que
# la CI ya vigila con `py.typed`.
RUN pip install ".[dev]"

CMD ["python", "scripts/check.py"]
