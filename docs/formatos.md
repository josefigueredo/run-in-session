# Formatos

Hay dos mensajes, la **tarea** y la **respuesta**, y dos archivos de estado, el **registro** y los **reclamos**. Los
mensajes los arma `ris` y los manda el agente con su herramienta `SendMessage`. `ris` no manda nada.

## Reglas comunes a los dos mensajes

- **La primera línea se entiende sola.** Quien recibe ve solo esa línea, cortada, hasta que despliega el mensaje
  (ctrl+o). Medido el 2026-10-17: la tab mostró
  `Message from @bugs: ris task 20261017-133004-f64f from bugs: Prueba de ida y vuelta de run-in-session: leer este mensaje con ris parse y co… (ctrl+o to expand)`.
  Ese formato viejo gastaba 20 caracteres en el id completo. Desde entonces la línea es
  `ris task from <quien pide>: <goal> [xxxx]` o `ris reply from <quien contesta> (<status>): <summary> [xxxx]`: primero
  quién y qué, y al final solo la cola del id (los 4 hexadecimales), que alcanza para que una persona empareje la
  respuesta con su tarea. El id completo va en el bloque, y es el que lee `ris`. Igual conviene que `goal` y `summary`
  digan lo importante al principio. Dónde se corta depende, probablemente, del ancho de la terminal (no medido).
- **Los campos van en un bloque con marca de versión.** La tarea va entre `--- ris-task v1 ---` y
  `--- end ris-task ---`, y la respuesta entre `--- ris-reply v1 ---` y `--- end ris-reply ---`. `ris parse` busca el
  bloque en cualquier parte del texto, porque el canal envuelve el mensaje con sus propias líneas (ver
  [El canal](#el-canal)).
- **Un campo, una línea:** `nombre: valor`. Si un valor trae un salto de línea, `ris` lo rechaza al armar el mensaje
  (código 2).
- **Los campos son datos, no permisos.** Que una tarea diga que se puede tocar algo no habilita a nadie: cada sesión
  decide con sus propios permisos y hooks.

## Tarea

```text
ris task from bugs: Rebasear feat/mcp-integration sobre fix/20-migracion-0018 [46d7]
--- ris-task v1 ---
id: 20261017-114927-46d7
from: bugs
to: main-session
goal: Rebasear feat/mcp-integration sobre fix/20-migracion-0018
done-when: la rama mergea sin conflictos y npm run test:db pasa
touches: feat/mcp-integration
forbidden: push; abrir PRs
--- context ---
fix/20 corrige la 0018 (le faltaba un END;) y ya tiene push.
Si aparece un conflicto en chat.service.ts, quedate con la versión de fix/20.
--- end ris-task ---
```

| Campo | Obligatorio | Qué es |
|---|---|---|
| `id` | sí | `AAAAMMDD-HHMMSS-xxxx` (fecha y hora local, más 4 hexadecimales al azar). Lo genera `ris task new` |
| `from` | sí | El nombre de la sesión que pide, como lo muestra `ListAgents`. Es para que lo lea una persona: **no se usa para contestar** |
| `to` | sí | El nombre de la sesión que recibe |
| `goal` | sí | Qué hay que hacer, en una línea. Es lo que se ve en la primera línea |
| `done-when` | sí | Cuándo la tarea cuenta como terminada. Sirve para que la respuesta diga `done` o `partial` sin discutir |
| `touches` | no | Ramas o archivos que la tarea puede cambiar, separados por `; ` (por eso un ítem no puede tener `;`) |
| `forbidden` | no | Lo que no tiene que hacer, separado por `; ` |
| `--- context ---` | sí, puede quedar vacío | Texto libre, varias líneas, hasta `--- end ris-task ---`. No puede tener una línea que parezca una marca (`--- ris-task v1 ---`, `--- end ris-reply ---`…), porque cortaría el mensaje: `ris task new` sale con 2 |

## Respuesta

```text
ris reply from main-session (done): Rebaseada sobre fix/20, sin conflictos [46d7]
--- ris-reply v1 ---
id: 20261017-114927-46d7
from: main-session
status: done
summary: Rebaseada sobre fix/20, sin conflictos
evidence:
- git log --oneline -1: 7c21917d feat(mcp): ...
- npm run test:db: 77 passed
pending:
- el push es del usuario
--- end ris-reply ---
```

| Campo | Obligatorio | Qué es |
|---|---|---|
| `id` | sí | El de la tarea que contesta. Si quien la recibe no mandó esa tarea, `ris parse` sale con 6 |
| `from` | sí | Quién contesta. Igual que en la tarea, es para leer, no para enrutar |
| `status` | sí | `done` (cumple `done-when`), `partial` (avanzó, ver `pending`), `declined` (no le corresponde o sus permisos no lo dejan) o `failed` (lo intentó y falló) |
| `summary` | sí | Una línea. Va también en la primera línea del mensaje |
| `evidence:` | no | Una lista con `- `: commits, comandos y su resultado. Quien la recibe la verifica antes de contársela al usuario. Un ítem sí puede tener `;` |
| `pending:` | no | Una lista con `- `: lo que falta y para quién |

## El canal

Lo que sigue se midió el 2026-10-17 entre dos sesiones de Claude Code en la misma máquina, salvo donde dice otra cosa.

- **Así llega un mensaje:** una sesión idle lo recibe como un turno nuevo, envuelto en
  `<cross-session-message from="uds:/tmp/cc-socks/82719.sock" from-name="acme-agent-c6" from-mode="prompting">`.
  Por eso `ris parse` busca el bloque en cualquier parte del texto.
- **Se contesta a quien lo mandó:** el valor de `from=` del mensaje que trajo la tarea. Funcionó contestando a
  `uds:/tmp/cc-socks/82719.sock`.
- **Los nombres cambian, la referencia no:** con `/rename`, `acme-agent-c6` pasó a llamarse `main-session` y su
  `[ref]` siguió siendo `[248292]`. Por eso `ris task new` guarda `--to-ref`, y los campos `from` y `to` del mensaje
  son solo para leer.
- **Una sesión ocupada lo recibe en el medio de su trabajo:** el mensaje entra en su próxima ronda de herramientas. Por
  eso la skill primero se suscribe a `notify_when_idle` sin mensaje, y manda la tarea cuando llega el aviso de que la
  sesión quedó libre.
- **Ida y vuelta completa (medida el 2026-10-17 con una sesión nueva, `prueba-ris`):** la tarea salió a las 13:30:04,
  la sesión que la recibió la leyó con `ris parse` (13:30:22) y contestó (13:30:29). Cargó la skill sola, al ver el
  bloque `ris-task`, sin que su persona se lo pidiera. Le pasó a `ris parse` el mensaje sin el envoltorio; del lado que
  pidió, `ris parse` leyó la respuesta con el envoltorio incluido y salió 0. Cada sesión dejó su registro aparte. El aviso de `notify_when_idle` llegó después de la respuesta, como un
  turno nuevo, con una línea de resumen de lo que hizo la otra sesión. La sesión que recibe también ve la suscripción:
  su tab mostró que la dirección de `bugs` pidió que le avisaran cuando quedara libre. Su `SendMessage` de respuesta lo
  aprobó el clasificador del modo auto, sin preguntarle a nadie.
- **Según la descripción de la herramienta `SendMessage`, no medido:** una sesión en otro modo de permisos retiene el
  mensaje hasta que su persona lo aprueba; las sesiones en la nube reciben pero no pueden contestar; las de Remote
  Control offline lo reciben cuando se reconectan. Que el envío salga bien no quiere decir que alguien lo leyó.

## Registro

`$RIS_HOME/sessions/<ref>/log.jsonl` (por defecto `~/.run-in-session/sessions/<ref>/log.jsonl`): una línea JSON por
evento, solo con lo que vio esa sesión. `<ref>` es la referencia de la sesión en el encabezado de `ListAgents` (por
ejemplo `bugs [48ff1d]`), y se pasa con `--as` a todo comando que lee o escribe el registro.

¿Por qué uno por sesión? Porque dos sesiones del mismo usuario en la misma máquina comparten `~/.run-in-session`. Con
un solo archivo, la respuesta que escribe una cerraría la tarea en la lista de la otra, y una respuesta mal dirigida
entre sesiones locales nunca daría el código 6. Se usa la referencia y no el nombre porque el nombre cambia con
`/rename`.

```json
{"ts": "2026-10-17T11:49:32-0300", "event": "sent", "id": "20261017-114932-8e16", "peer": "main-session", "peer_ref": "248292", "goal": "x"}
{"ts": "2026-10-17T11:49:32-0300", "event": "replied", "id": "20261017-114927-46d7", "peer": "", "status": "done"}
```

| `event` | Lo escribe | Campos además de `ts`, `id` y `peer` |
|---|---|---|
| `sent` | `ris task new` | `peer_ref`, `goal` |
| `received` | `ris parse` de una tarea | `goal` |
| `replied` | `ris task reply` | `status`; `peer` sale de la tarea recibida, vacío si no está en el registro |
| `reply-received` | `ris parse` de una respuesta a una tarea propia | `status` |

`ris task list --as <ref>` arma una fila por tarea de esa sesión: está `open` hasta que hay una respuesta, y después
muestra su `status`.

## Reclamos

`$RIS_HOME/claims.json`: quién tiene cada rama o archivo, separado por repo. A diferencia del registro, se comparte
entre las sesiones a propósito: dice cuál tiene qué. La clave del repo es su directorio git común
(`git rev-parse --git-common-dir`), así todos los worktrees de un clon ven lo mismo. El repo es el de `-C <dir>`, o el
directorio actual si no se pasa; fuera de un repo, la clave es `(no repo)`. `claim` y `release` toman un lock
(`claims.lock`) mientras leen y escriben, así dos sesiones a la vez no pierden un reclamo.

```json
{
 "/Users/ana/code/acme-agent/.git": {
  "fix/20": {"note": "rebasing", "session": "bugs", "since": "2026-10-17T11:49:32-0300"}
 }
}
```

Los reclamos son de este usuario en esta máquina. Una sesión en otra máquina no los ve: para eso está el mensaje.

## Códigos de salida

| Código | Cuándo |
|---|---|
| 0 | Salió bien |
| 2 | Uso: falta un argumento, `--as` no es una referencia válida, un valor tiene un salto de línea, un ítem de `touches` o `forbidden` tiene `;`, el contexto tiene una línea de marca, un `status` desconocido |
| 3 | Rechazado: el mensaje coincide con un `--deny`, o la rama o el archivo los tiene otra sesión |
| 4 | El texto no trae un mensaje válido: no tiene marca, le falta un campo o el bloque está cortado |
| 5 | La marca es de una versión que este `ris` no lee |
| 6 | Un `id` que no está en el registro de esa sesión: una respuesta a una tarea que no mandó, o `ris task show` de un id desconocido |

## Versiones

La versión va en la marca (`ris-task v1`). Un cambio que el parser de la v1 no pueda leer (un campo obligatorio nuevo,
otro separador) sube la versión. Sumar un campo opcional no la sube: el parser de la v1 ignora los campos `nombre: valor`
que no conoce, así que una sesión con un `ris` viejo sigue leyendo el mensaje y solo pierde el campo nuevo. Una línea
que no tiene la forma `nombre: valor` sí es un error (código 4). Si llega una versión que `ris` no lee, sale con 5 y la
sesión contesta en texto plano diciendo qué versión lee.
