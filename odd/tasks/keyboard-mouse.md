## Specs
S1: El usuario pidió "los indicativos de las teclas reactivos al ratón, como en el resto del agente". Cita literal: "Le podías añadir que los indicativos de las teclas fueran reactivos al ratón, como es en el resto del agente."
S2: Confirmación del usuario: los de parte inferior (ej. "esc") también. Confirmación final: "los de la parte inferior tambien por ejemplo el que dice esc" + "si hace click en ESC se cierra".
S3: Los paneles (`files`/`preview`) ya responden al mouse (`handleMouse`); se mantienen y se confirma que directorios colapsan/expandan con click. Confirmación: "es correcto, creo que es suficiente con los paneles y carpetas".
S4: Alcance: no inventar estilos hover inexistentes en `theme`; usar `accent`/`bold` del runtime existente.

## Tasks
T1: Especificación y plan (S1-S4) — commit: `feat: spec mouse-reactive badges and dirs`
T2: Implementar click en badges top/bottom y colapso/expansión de directorios en `browser.js` — commit: `feat: mouse-reactive keyboard badges and dirs`
T3: Verificar con `npm test` — commit: `test: verify mouse badges and dirs`

## Log
L1: Petición original: "Le podías añadir que los indicativos de las teclas fueran reactivos al ratón, como es en el resto del agente."
L2: Confirmación puntos 1 y 2 (badges + paneles) y fila inferior (`esc`). Confirmación final: suficiente con paneles y carpetas; click en `esc` cierra; directorios colapsan/expanden.
