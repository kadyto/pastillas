# Instalar Pastillas con Dockhand

## Preparar el NAS

Crea una carpeta local de datos, por ejemplo `/volume1/docker/pastillas/data` en Synology. Usa la ruta real que indique tu NAS; no una ruta SMB/NFS. Dale permiso de lectura y escritura a una cuenta sin privilegios. Introduce su UID y GID en `APP_UID` y `APP_GID`. La carpeta debe existir antes del despliegue; el Compose no la crea automáticamente.

## Configurar el stack

En Dockhand: **Stacks → New Stack → pastillas**. Pega el contenido íntegro de [compose.dockhand.yaml](../compose.dockhand.yaml).

| Variable | Valor |
| --- | --- |
| `DATA_DIR` | Ruta absoluta de la carpeta de datos ya creada |
| `INITIAL_ADMIN_USER` | Usuario inicial, 3–60 caracteres |
| `INITIAL_ADMIN_PASSWORD` | Contraseña propia de 12–256 caracteres |
| `APP_UID` / `APP_GID` | Propietario de la carpeta; por defecto 10001 / 10001 |
| `APP_PORT` | Puerto disponible, por defecto 8092 |
| `BIND_ADDRESS` | Por defecto 0.0.0.0, accesible por la red local; 127.0.0.1 para proxy local |
| `COOKIE_SECURE` | `false` para HTTP privado; `true` cuando accedas únicamente por HTTPS |
| `PUBLIC_URL` | URL externa exacta con proxy inverso, por ejemplo `https://pastillas.ejemplo.es`, sin barra final |
| `NTFY_BASE_URL` | Por defecto `https://ntfy.sh`; cambia a tu servidor ntfy si lo tienes |
| `NTFY_TOKEN` | Opcional, token de publicación de un servidor ntfy con autenticación |

Despliega con **build/construcción habilitado**. Docker descarga el archivo público `.tar.gz` de GitHub y construye la imagen automáticamente. No requiere Git en Dockhand ni una imagen previa de GHCR. La primera instalación necesita acceso a GitHub y al registro Docker para descargar Python; no descarga paquetes de pip o npm.

Cuando `pastillas` esté **healthy**, abre `http://IP_DEL_NAS:8092` e inicia sesión. Los campos vacíos son normales: añade tu primer medicamento.

También puedes indicar un origen Git en Dockhand: repositorio `https://github.com/kadyto/pastillas`, referencia `main` y archivo `compose.dockhand.yaml`, conservando las mismas variables.

## HTTPS

Configura tu proxy inverso para apuntar a `8000` dentro del contenedor o al `APP_PORT` del host. La aplicación se sirve en la raíz del dominio, sin prefijo de ruta. Conserva el encabezado `Host` o configura `PUBLIC_URL` con la URL externa exacta. Con HTTPS, utiliza `COOKIE_SECURE=true`. Con HTTP y cookies seguras activadas no podrás mantener la sesión.

El servidor valida el origen de las peticiones. Si aparece un error de origen al guardar, revisa `PUBLIC_URL` y la URL con la que accedes. La dirección debe incluir el puerto si no es el puerto estándar. No se necesita CORS.

## Actualizar

Haz una [copia consistente](mantenimiento.md). Conserva `DATA_DIR`, UID/GID y tus variables. En Dockhand solicita **reconstruir la imagen y recrear el stack** para descargar el `main` actual. Reiniciar sin reconstruir no cambia el código. Si Dockhand conserva la caché del contexto remoto, usa la opción de reconstruir sin caché.

Para fijar un commit, sustituye conjuntamente:

- Contexto: `https://github.com/kadyto/pastillas/archive/SHA_COMPLETO.tar.gz`
- Dockerfile: `pastillas-SHA_COMPLETO/Dockerfile`
- Argumento `SOURCE_DIR`: `pastillas-SHA_COMPLETO`

El Dockerfile también admite construcción local mediante `compose.yaml`.

## Resolver problemas

- **Git no está instalado:** conserva el contexto `.tar.gz`; no uses `.git#main`.
- **No encuentra el Dockerfile:** usa `pastillas-main/Dockerfile` y `SOURCE_DIR: pastillas-main`.
- **No se construye:** activa build/rebuild al desplegar.
- **Sin permisos en `/data`:** revisa el propietario y las ACL de la carpeta y `APP_UID`/`APP_GID`.
- **Puerto ocupado:** cambia `APP_PORT`.
- **Usuario inicial no cambia:** las variables solo crean la primera cuenta cuando no hay ninguna. Cambia la contraseña desde Ajustes o con la herramienta de recuperación.
- **Avisos ausentes:** revisa [avisos](avisos.md); la agenda sigue disponible aunque ntfy no responda.
