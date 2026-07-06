# 06 — Build Your Own Redis · PRÁCTICA (Python)

> **Versión de práctica.** Estructura completa, código a 0 bytes. **Tú escribes todo desde cero**, teclándolo tú (no copiar), mirando el modelo `../06_build_your_own_redis/` solo cuando atasques. Patrón modelo+práctica de [[00_README]].

## Por dónde empezar

1. Lee **`PHASES.md`** — el mapa de fases del proyecto.
2. Ponte con la **Fase 0** (walking skeleton): abre **`docs/fase-0-walking-skeleton.md`** y sigue los Issues de **`HULY_fase-0-issues.md`** (mételos en Huly).
3. Teclea el código en `server/myredis/` y los tests en `server/tests/`.

## Setup del entorno (una vez)

```bash
cd 06_build_your_own_redis_practica
python3 -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt
```

## Verificar la Fase 0

```bash
cd server && source ../.venv/bin/activate
pytest tests/unit/test_protocol.py -v          # parser + encoder en verde
python -m myredis                              # arranca en :6380
# en otra terminal:
redis-cli -p 6380 PING                         # -> PONG
pytest tests/integration/ -k ping -v           # ping() True
```

## Filosofía

El valor NO está en el código terminado (ya está en el modelo). Está en **diseñarlo y teclearlo tú**, provocando cada fallo y arreglándolo. Aplica tu [[disenar-funciones-y-programas|guía de diseño]]: contrato + edge cases antes de cada pieza.

## Conexiones
- [[00_README]] · [[MOC_Build_Things]] · [[disenar-funciones-y-programas]]
- Modelo de referencia: `../06_build_your_own_redis/`
