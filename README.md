# odd-view — explorá los artefactos de ODD desde Gentle Shell

Si no quieres salir de la terminal para explorar los archivos que crea ODD, tenemos la solución.

`odd-view` agrega el comando `/odd-review` a Gentle Shell. Abre un navegador fullscreen, de solo lectura, con el árbol de artefactos ODD a la izquierda y una vista formateada del archivo seleccionado a la derecha.

## Qué resuelve

ODD conserva especificaciones, tareas, decisiones y evidencia dentro del directorio `odd/` del proyecto. `odd-view` permite revisar esos archivos sin cambiar de aplicación ni abandonar el flujo de trabajo en la terminal.

- Descubre recursivamente los archivos de `odd/`.
- Renderiza Markdown con el tema activo de Gentle Shell.
- Permite navegar con teclado o mouse.
- Se adapta a terminales angostas mostrando un panel por vez.
- Mantiene una frontera estrictamente read-only.
- Rechaza escapes de ruta, symlinks y archivos especiales.
- Limita cada preview a 512 KiB y detecta contenido binario.

## Instalación

### Desde npm — recomendado

Instalá la versión pública en el home aislado de Gentle Shell:

```bash
gentle-shell install npm:odd-view
```

Reiniciá o recargá Gentle Shell después de instalar. Para actualizar o eliminar el paquete:

```bash
gentle-shell update npm:odd-view
gentle-shell remove npm:odd-view
```

### Desde un release de GitHub

También podés instalar una versión inmutable directamente desde su tag:

```bash
VERSION=0.1.0
gentle-shell install git:github.com/oniricosistemas/odd-view@v${VERSION}
```

### Probar este checkout

Durante el desarrollo no hace falta instalar el paquete:

```bash
gentle-shell --extension ./extensions/odd-review.ts
```

## Uso

Abrí Gentle Shell dentro de un proyecto que tenga un directorio `odd/` y ejecutá:

```text
/odd-review
```

La ventana muestra el árbol de artefactos a la izquierda y el preview del archivo activo a la derecha.

## Controles

| Acción | Teclado | Mouse en fullscreen |
| --- | --- | --- |
| Cambiar de panel | `Tab` o `Shift+Tab` | Click sobre el panel |
| Seleccionar archivo | `↑`, `↓`, `Page Up`, `Page Down`, `Home`, `End` | Click o rueda sobre el árbol |
| Abrir el preview | `Enter` o `→` | Click sobre el preview |
| Desplazar el preview | `↑`, `↓`, `Page Up`, `Page Down`, `Space`, `Home`, `End` | Rueda sobre el preview |
| Volver al árbol | `←` | Click sobre el árbol |
| Cerrar | `Esc` o `Ctrl+C` | — |

## Seguridad de lectura

El navegador nunca modifica los artefactos del proyecto. Antes de abrir un archivo:

1. valida cada componente de la ruta dentro de `odd/`;
2. rechaza symlinks, directorios y archivos especiales;
3. abre el descriptor en modo read-only y no-follow;
4. vuelve a comprobar la identidad del archivo después de abrirlo;
5. limita la cantidad de datos cargados en memoria.

Los nombres de archivos también se limpian antes de renderizarse para evitar secuencias de control en la terminal.

## Desarrollo

```bash
npm test
npm run check
npm run release:check
```

| Ruta | Responsabilidad |
| --- | --- |
| `extensions/odd-review.ts` | Entrada del paquete para Pi/Gentle Shell |
| `src/command.js` | Registro y ciclo de vida de `/odd-review` |
| `src/files.js` | Descubrimiento seguro y previews read-only |
| `src/browser.js` | Layout fullscreen, renderizado e interacción |
| `test/` | Cobertura funcional, visual, de seguridad y distribución |
| `odd/tasks/odd-review.md` | Especificación ODD y evidencia del proyecto |

La guía de publicación está en [`RELEASING.md`](https://github.com/oniricosistemas/odd-view/blob/main/RELEASING.md). La versión de npm y el tag `vX.Y.Z` deben representar exactamente el mismo commit.

## Licencia

MIT © 2026 Onírico Sistemas.

## creado con:

<p align="left">
  <img src="https://raw.githubusercontent.com/Gentleman-Programming/gentle-ai/main/docs/assets/brand/built-with-gentle-ai.png" alt="Creado con Gentle AI" width="280">
</p>
