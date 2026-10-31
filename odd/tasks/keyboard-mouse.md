## Specs
S1: El usuario pidió "los indicativos de las teclas reactivos al ratón, como en el resto del agente". Cita literal: "Le podías añadir que los indicativos de las teclas fueran reactivos al ratón, como es en el resto del agente."
S2: Los indicativos de la fila inferior también, incluido `Esc close`. Cita literal: "los de la parte inferior tambien por ejemplo el que dice esc".
S3: Click en `[Esc Close]` o en `Esc close` cierra la ventana exactamente una vez. Cita literal: "si hace click en ESC se cierra".
S4: Click en una carpeta del árbol la colapsa o expande. Cita literal: "o si hace click en una carpeta en el panel de los archivos los colpasa o expande".
S5: Alcance confirmado: badges superiores (`[Tab Switch]`, `[Esc Close]`), fila de ayuda inferior, paneles y carpetas. Cita literal: "los badges (Tab Switch, Esc Close) y fila inferior (Tab, ↑↓, Esc) tiene que ser clickeable tambien como los del top".
S6: No se inventan estilos de tema: el realce de hover usa `underline` (o `bold` como fallback) y los tokens existentes `accent`, `muted`, `selectedBg`, `border`.

## Tasks
T1: Especificación, tests RED y plan (S1-S6) — commit: `a4f97d8`
T2: Regiones de click/hover, acción por indicativo y colapso de carpetas en `src/browser.js` (S1-S5) — commit: `cea0d43`
T3: Controles del README, tests MR1-MR5 y verificación `npm test` + `npm run check` (S2-S6) — commit: `cea0d43`

## Log
L1: Petición original: "Le podías añadir que los indicativos de las teclas fueran reactivos al ratón, como es en el resto del agente."
L2: Confirmó que los indicativos de la fila inferior también, "por ejemplo el que dice esc".
L3: Confirmó que click en ESC cierra y que click en una carpeta la colapsa o expande.
L4: Corrección de alcance: "los badges (Tab Switch, Esc Close) y fila inferior (Tab, ↑↓, Esc) tiene que ser clickeable tambien como los del top".

## Follow-up: v0.2.0 field reports

S7: Cita literal: "En el panel de artefactos, quizás se podría mejorar el subrayado del enlazado (elemento seleccionado), tal como está subraya toda la línea, quedaría más limpio si se limitara solo al texto."
S8: Cita literal: "PROBLEMA: Al salir de la extensión y retornar a la página principal del agente el teclado no reacciona, no deja hacer nada, parece que la extensión secuestra el manejador ("handle") de teclado o lo deja en el limbo".

T4: Reproducir y corregir el foco de teclado perdido al cerrar (`MR6`, `MR7`) — commit: pending
T5: Limitar el resaltado de selección al texto (`MR8`) — commit: pending

Cause of S8: the close path returned `focus: true` from `handleMouse` after the overlay was already
disposed, so the host restored keyboard focus to a dead component. Mouse kept working because it is
dispatched by overlay layout, not by focus.
