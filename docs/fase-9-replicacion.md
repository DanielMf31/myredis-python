# Fase 9 (opcional) — Replicación master-slave

> **Meta:** convertir tu Redis de un nodo en un **sistema distribuido** — una réplica sigue al máster. Es tu **primer contacto real con sistemas distribuidos**, el campo que te fascina.
> **Esto es un DOC DE DISEÑO**, no código guiado: replicación tiene edge cases de red y fallo que merecen que diseñemos el código juntos cuando llegues (contratos + tests + decisiones). Aquí montamos el **mapa mental**.

## 1. Concepto: por qué esto es "distribuido de verdad"
Hasta F8, todo era un nodo. Con replicación aparecen los problemas que **no existen en un solo proceso**:
- **Fallo parcial:** el máster puede caer mientras la réplica sigue viva (y viceversa).
- **Consistencia:** la réplica va **por detrás** del máster (replicación asíncrona → *consistencia eventual*). ¿Qué ve un cliente que lee de la réplica?
- **Orden:** los cambios deben aplicarse en la réplica **en el mismo orden** que en el máster.

Esos tres —fallo parcial, consistencia, orden— son la esencia de sistemas distribuidos.

## 2. Arquitectura (cómo lo haría Redis, simplificado)
```
   Cliente escribe
        │
        ▼
   [ MÁSTER ] ──(1) snapshot inicial──> [ RÉPLICA ]
        │                                    ▲
        └──(2) stream de comandos de escritura┘   (replication log)
```
1. **Sincronización inicial (full resync):** cuando una réplica se conecta con `REPLICAOF host port`, el máster le manda un **snapshot** de todo el estado (reusa tu RDB de F6).
2. **Propagación incremental:** a partir de ahí, el máster **reenvía cada comando de escritura** (SET, LPUSH...) a la réplica por un stream. La réplica los **aplica en orden** → se mantiene al día.
3. La réplica es **solo-lectura**: rechaza escrituras de clientes (solo acepta las que vienen del máster).

## 3. Piezas nuevas (para diseñar juntos)
- `REPLICAOF host port` (y `REPLICAOF NO ONE` para volver a máster).
- En el **máster**: una lista de réplicas conectadas; tras cada escritura, propagar el comando a todas.
- En la **réplica**: una conexión saliente al máster, recibir el snapshot, luego consumir el stream de comandos y aplicarlos al `storage` local.
- Marcar el server como `role: master | replica`; la réplica rechaza escrituras de clientes normales.

## 4. Los edge cases (la parte difícil — tu taxonomía, en distribuido)
- **El máster cae** a mitad → la réplica se queda huérfana. ¿Reintenta reconectar? ¿Se promociona a máster?
- **La réplica cae y vuelve** → ¿resync completo o parcial (desde dónde se quedó)?
- **Partición de red** (los dos vivos pero sin verse) → *split-brain*: dos másters aceptando escrituras → divergencia.
- **Lag de replicación:** un cliente escribe en el máster y lee de la réplica al instante → **no ve su propia escritura** (read-your-writes roto). Es el precio de la consistencia eventual.
- **Orden bajo reconexión:** garantizar que no se pierden ni se duplican comandos del stream.

> Estos son los mismos "modos de fallo" de tu design guide, pero **sobre la red**. Aquí es donde LoC ≠ dificultad: poco código, muchísima materia gris.

## 5. Cómo lo abordaremos (plan de sub-fases, cuando llegues)
- **F9.1** — `REPLICAOF` + full resync (snapshot). La réplica arranca con el estado del máster.
- **F9.2** — propagación de escrituras (el stream). La réplica sigue al máster en vivo.
- **F9.3** — réplica solo-lectura + `INFO replication` (role, offset).
- **F9.4** — reconexión y resync tras caída.
- **F9.5** (avanzado) — pensar el *split-brain* y por qué hace falta consenso (Raft) para resolverlo de verdad → puente al **catálogo BYOX** (Raft).

## 6. Lecturas para cuando llegues
- **Designing Data-Intensive Applications** (Kleppmann), cap. 5 (Replication) — el mejor tratamiento.
- La doc de replicación de Redis (cómo hace el resync parcial con el *replication backlog*).
- Tu propio [[catalogo-byox-infra]]: Raft es el siguiente escalón natural (consenso para resolver el split-brain).

## Conexiones
- `PHASES.md` · `issues/fase-9.md` · [[disenar-funciones-y-programas]] (edge cases) · [[catalogo-byox-infra]] (Raft) · [[MOC_CS_Fundamentos]] (sistemas distribuidos)
