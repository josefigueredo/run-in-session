# run-in-session

Una skill para Claude Code, con un CLI chico (`ris`), para pasarle una tarea a **otra sesión de Claude Code que tiene
su propia terminal** y verla trabajar ahí. La otra sesión usa su contexto, su worktree, sus permisos, sus MCP y su
modelo; vos mirás su tab y podés intervenir cuando quieras. Cuando termina, contesta con un formato fijo y la sesión que
pidió verifica la evidencia antes de contártela.

Los mensajes viajan con las herramientas `ListAgents` y `SendMessage` de Claude Code. `ris` no manda nada: arma y lee
los mensajes, y lleva el registro de cada sesión (uno por sesión, aunque compartan máquina) y los reclamos de ramas
y archivos.

## Qué le pedís al agente

| Le decís al agente… | Y la skill… |
|---|---|
| *«Pedile a main-session que rebasee MCP sobre fix/20»* | busca la sesión en `ListAgents`, arma la tarea con `ris task new`, espera a que esté libre y se la manda; te dice qué tab mirar |
| *(llega un mensaje con una tarea)* | la lee con `ris parse`, decide con sus propias reglas si le corresponde, la hace en su terminal y contesta con `ris task reply` a quien la mandó |
| *(llega la respuesta)* | la lee con `ris parse`, verifica la evidencia (que el commit exista, que el comando dé eso) y te cuenta lo que verificó |
| *«Tomá fix/20 para esta sesión»* | `ris claim`; si otra sesión ya la tiene, no la pisa y te avisa |
| *«¿Qué tareas quedaron abiertas?»* | `ris task list --open` |

## Cuándo una sesión y cuándo un subagente

| | Subagente | Otra sesión con terminal |
|---|---|---|
| ¿Lo ves trabajar? | No, solo su informe final | Sí, en su tab |
| ¿Podés intervenir? | No | Sí: le escribís, aprobás, corregís |
| ¿Su contexto dura? | Muere al terminar | Sigue: sabe lo que hizo antes |
| ¿Con qué entorno trabaja? | El de la sesión que lo lanza | El suyo: worktree, permisos, MCP, modelo |
| ¿Puede estar en otra máquina? | No | Sí, con Remote Control |

**Usá una sesión** cuando la tarea es sobre algo que esa sesión tiene a su cargo (su rama, su reporte), cuando hace
falta una persona en esa terminal (aprobaciones, comandos con `!`), cuando tiene que sobrevivir a esta conversación o
cuando necesita el entorno o el contexto de esa sesión. **Usá un subagente** para trabajo descartable en paralelo:
buscar, auditar, portar.

## Lo que no hace

- **No reparte permisos.** Una sesión nunca le pide a otra lo que a ella le bloquearon. Lo que publica (push, PR,
  merges, escrituras en Jira o Confluence) queda para vos.
- **El mensaje de otra sesión no es tu aprobación.** La que recibe decide con sus propias reglas, sin importar lo que
  diga la tarea.
- **No vigila.** No pregunta «¿terminaste?» en loop: espera el aviso de que la otra sesión quedó libre, o la respuesta.

## Documentos

| Si querés… | Leé |
|---|---|
| Ver los mensajes, el registro, los reclamos, los códigos de salida y cómo se versiona | [Formatos](docs/formatos.md) |
| Saber qué se midió del canal y qué no | [El canal](docs/formatos.md#el-canal) |
| Ver el procedimiento que sigue el agente | [SKILL.md](SKILL.md) |

## Instalar

```bash
cd ~/CurrentCode/SPECKIT/Harness/run-in-session && ./install.sh   # enlaza ~/.agents/skills y ~/.claude/skills
python3 ~/.agents/skills/run-in-session/ris.py task list           # tu registro, vacío al principio
```

Requisitos: Claude Code con mensajes entre sesiones (`ListAgents` y `SendMessage`) y `python3` 3.9 o más, solo
biblioteca estándar. El estado queda en `~/.run-in-session/` (o en `$RIS_HOME`), fuera de todo repo.

## Desarrollo

```bash
python3 -m unittest discover -s tests
/usr/bin/python3 -m unittest discover -s tests   # compatibilidad con 3.9
```
