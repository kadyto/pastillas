# Copias, restauración y cuentas

## Exportación personal

En Ajustes, **Exportar mis datos** descarga JSON con los medicamentos, recetas, tomas y movimientos completos de tu cuenta, sin contraseñas ni sesiones. Las cantidades se expresan como enteros con `quantity_scale: 1000`: divide entre 1000 para obtener las unidades del usuario. Las fechas de tomas son segundos UTC. Es un archivo de consulta y portabilidad; no se importa desde la interfaz.

## Copia completa consistente

SQLite usa WAL. No copies solo `pastillas.sqlite` mientras el contenedor está escribiendo: pueden faltar cambios del archivo `-wal`.

Desde la consola del contenedor en Dockhand:

```bash
python -m app.cli backup /data/copia-2026-10-11.sqlite
```

La herramienta usa la API de copias SQLite y crea un archivo consistente; rechaza un destino ya existente. Descarga la copia desde el administrador de archivos del NAS y guárdala en otro almacenamiento privado. Contiene todos los datos y hashes de contraseñas del servidor. Con una copia de seguridad del NAS, para obtener una copia en frío basta detener el contenedor antes de copiar la carpeta de datos completa.

## Restaurar el servidor

1. Detén el stack en Dockhand.
2. Conserva una copia del estado actual.
3. Sustituye `pastillas.sqlite` por la copia consistente. Retira los archivos `pastillas.sqlite-wal` y `pastillas.sqlite-shm` del estado anterior; nunca reutilices un WAL de otra copia.
4. Asegura que el propietario es el mismo UID/GID del contenedor.
5. Inicia el stack y comprueba el acceso y las existencias.

## Recuperar contraseña

La cuenta puede cambiar su contraseña desde Ajustes, indicando la actual. Se revocan las sesiones previas y se mantiene abierta una nueva sesión en el navegador que la cambia.

Si la has olvidado, en una consola interactiva del contenedor:

```bash
python -m app.cli reset-password miusuario
```

La nueva contraseña se solicita sin mostrarla y no se pasa como argumento. Todas las sesiones de esa cuenta quedan revocadas. Las variables `INITIAL_ADMIN_*` solo se utilizan en una base sin usuarios; no restablecen contraseñas.

La cuenta administradora crea otras cuentas desde Ajustes, pero las cuentas mantienen sus datos separados. No hay registro público, recuperación por correo ni acceso de un usuario al botiquín de otro.

## Persistencia

Mantén la misma carpeta `DATA_DIR` al recrear o actualizar el stack. Medicamentos, stock, usuarios, recetas, registros de toma y avisos se guardan en esa carpeta. El historial no se borra al reiniciar. Eliminar un medicamento desde la interfaz sí elimina sus tomas y movimientos tras la confirmación; pausarlo los conserva.

Si utilizas `compose.dockhand.volume.yaml`, los mismos archivos se guardan en el volumen `pastillas_data` del stack, montado en `/data`. Conserva el nombre del stack y ese volumen al actualizar, y no marques la opción de eliminar volúmenes al recrear el contenedor. La herramienta de copia SQLite se utiliza con el mismo comando; después descarga el archivo mediante el explorador del volumen en Dockhand o tu herramienta de copias Docker.
