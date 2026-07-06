# Issues de Huly — Fase 9 (Replicación, opcional)

> Título → Título de Huly; debajo → Descripción. Labels: `byox-redis`, `fase-9`, `sistemas-distribuidos`. Doc (diseño): `docs/fase-9-replicacion.md`.
>
> ⚠️ Estas son **épicas de diseño** — el código lo diseñamos juntos al llegar (contratos + edge cases + tests). Aquí solo el mapa.

---

### F9-1 · REPLICAOF + full resync (snapshot)

**Título:** F9-1 · Replicación: REPLICAOF + sincronización inicial

**Contexto:** una réplica se conecta con `REPLICAOF host port` y recibe un snapshot completo del máster (reusa el RDB de F6).

**A diseñar:**
- comando `REPLICAOF host port` / `REPLICAOF NO ONE`
- máster: enviar snapshot a la réplica que se conecta
- réplica: conexión saliente + recibir y cargar el snapshot

**Hecho cuando:** una réplica arranca con el estado del máster.

---

### F9-2 · propagación de escrituras (stream)

**Título:** F9-2 · Replicación: propagar comandos de escritura

**A diseñar:**
- máster: lista de réplicas; tras cada escritura, reenviar el comando a todas, en orden
- réplica: consumir el stream y aplicar los comandos al storage local

**Edge cases:** orden estricto; no perder ni duplicar comandos.

**Hecho cuando:** un SET en el máster aparece en la réplica en < 1s.

---

### F9-3 · réplica solo-lectura + INFO replication

**Título:** F9-3 · Replicación: réplica read-only + estado

**A diseñar:**
- role master/replica; la réplica rechaza escrituras de clientes normales
- `INFO replication` (role, offset, réplicas conectadas)

---

### F9-4 · reconexión y resync tras caída

**Título:** F9-4 · Replicación: reconexión de la réplica

**A diseñar:**
- la réplica reintenta conectar si el máster cae
- resync (completo, para empezar) al reconectar

**Edge cases (los duros):** máster caído, réplica huérfana, lag de replicación (read-your-writes roto).

---

### F9-5 · (avanzado) split-brain → por qué hace falta consenso

**Título:** F9-5 · Spike: split-brain y el límite de master-slave

**Contexto:** entender por qué la replicación simple **no** resuelve una partición de red (dos másters divergen), y por qué eso lleva a **Raft/consenso**.

**Salida:** una nota en la bitácora + puente al Raft del [[catalogo-byox-infra]]. (No código — es un spike de comprensión.)
