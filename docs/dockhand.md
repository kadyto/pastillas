# Instalar Pastillas con Dockhand

## Opción sencilla: volumen gestionado por Docker

Pega [compose.dockhand.volume.yaml](../compose.dockhand.volume.yaml) en el editor del stack. Define `INITIAL_ADMIN_USER`, `INITIAL_ADMIN_PASSWORD` y, si lo necesitas, `APP_PORT`; las variables de HTTPS y ntfy funcionan igual que en la tabla inferior. No necesitas crear una carpeta en el NAS ni configurar `DATA_DIR`, `APP_UID` o `APP_GID`: el contenedor usa UID/GID 10001 y Docker inicializa el volumen con ese propietario.

Despliega con build habilitado. Se crea un volumen persistente del proyecto llamado `<nombre-del-stack>_pastillas_data` (Dockhand puede aplicar su propio prefijo). Mantén el nombre del stack y el volumen al actualizar. Puedes verlo en la sección Volumes de Dockhand. No elimines ese volumen al recrear el contenedor.

Esta variante inicia una base nueva. Si ya tienes datos en una carpeta del NAS, conserva el Compose original y corrige sus permisos, o realiza una migración con el contenedor detenido. Cambiar el Compose no copia los datos automáticamente.

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
| `COOKIE_SECURE` | `auto` por defecto: HTTPS a través del proxy usa una cookie segura; HTTP directo también funciona. `true` obliga a HTTPS; `false` conserva el comportamiento anterior |
| `NTFY_BASE_URL` | Por defecto `https://ntfy.sh`; cambia a tu servidor ntfy si lo tienes |
| `NTFY_TOKEN` | Opcional, token de publicación de un servidor ntfy con autenticación |

Despliega con **build/construcción habilitado**. Docker descarga el archivo público `.tar.gz` de GitHub y construye la imagen automáticamente. No requiere Git en Dockhand ni una imagen previa de GHCR. La primera instalación necesita acceso a GitHub y al registro Docker para descargar Python; no descarga paquetes de pip o npm.

Los Compose de Dockhand incluyen el Dockerfile en `dockerfile_inline` para funcionar también con versiones de Compose que interpretan mal la ruta del Dockerfile dentro de un contexto remoto. Requieren Docker Compose 2.17 o posterior.

Cuando `pastillas` esté **healthy**, abre `http://IP_DEL_NAS:8092` e inicia sesión. Los campos vacíos son normales: añade tu primer medicamento.

También puedes indicar un origen Git en Dockhand: repositorio `https://github.com/kadyto/pastillas`, referencia `main` y archivo `compose.dockhand.yaml`, conservando las mismas variables.

## HTTPS

Configura tu proxy inverso para apuntar a `8000` dentro del contenedor o al `APP_PORT` del host. La aplicación se sirve en la raíz del dominio, sin prefijo de ruta. Puedes usar cualquier dominio, IP o puerto, y el proxy puede reescribir `Host`: no necesitas configurar una URL pública. Con `COOKIE_SECURE=auto`, el encabezado `X-Forwarded-Proto` del proxy determina si la cookie lleva `Secure`. Con `true` y acceso HTTP no podrás mantener la sesión.

`PUBLIC_URL` ya no se utiliza. Si la conservas en las variables de un stack anterior, no impone restricciones. La interfaz utiliza peticiones relativas a la dirección desde la que la abres; no se necesita CORS para usarla desde dominios distintos. Cada dirección mantiene su propia sesión de navegador.

### Nginx Proxy Manager

En el Proxy Host, elige el esquema **http** hacia el contenedor, con su IP/nombre y el puerto del servicio. Activa el certificado y HTTPS en la pestaña SSL para el acceso exterior. Nginx Proxy Manager envía `X-Forwarded-Proto` automáticamente; `COOKIE_SECURE=auto` funciona tanto por ese HTTPS como al entrar directamente por HTTP.

No necesitas reglas en Advanced para las cookies. Conserva los encabezados `Cookie` y `Set-Cookie` y deja las rutas `/api/` fuera de cualquier caché personalizada. Las cookies son del host desde el que accedes, con `HttpOnly`, `SameSite=Lax` y sin un dominio fijado por la aplicación.

Desde la versión 0.1.1, las cookies de otras aplicaciones no invalidan la lectura de la sesión de Pastillas. También se tolera una cookie de sesión antigua con otra ruta si existe una sesión válida. Si el login acepta la contraseña pero no se conserva la cookie, la interfaz muestra un mensaje específico.

Para actualizar un stack existente, conserva sus datos y volumen y reconstruye la imagen. Puedes cambiar `COOKIE_SECURE` a `auto`; la aplicación sigue respetando los valores explícitos `true` y `false`. Comprueba que el pie de la app muestre 0.1.1 después de reconstruir.

## Actualizar

Haz una [copia consistente](mantenimiento.md). Conserva `DATA_DIR`, UID/GID y tus variables. En Dockhand solicita **reconstruir la imagen y recrear el stack** para descargar el `main` actual. Reiniciar sin reconstruir no cambia el código. Si Dockhand conserva la caché del contexto remoto, usa la opción de reconstruir sin caché.

Para fijar un commit, sustituye conjuntamente:

- Contexto: `https://github.com/kadyto/pastillas/archive/SHA_COMPLETO.tar.gz`
- Argumento `SOURCE_DIR`: `pastillas-SHA_COMPLETO`

Conserva el bloque `dockerfile_inline` del Compose.

El Dockerfile también admite construcción local mediante `compose.yaml`.

## Resolver problemas

### SQLite: unable to open database file

En el Compose con carpeta del NAS, `/data` es exactamente la ruta indicada en `DATA_DIR`. El contenedor debe poder crear y modificar `pastillas.sqlite` y los archivos `-wal`/`-shm`. El propietario de `/data` dentro de la imagen no cambia el propietario de una carpeta montada desde el NAS.

Si es una primera instalación sin datos, sustituye el Compose del stack por la variante de volumen gestionado de arriba y vuelve a desplegar con build habilitado. Puedes conservar las variables del usuario, la contraseña y el puerto; la variante no usa las de carpeta/UID/GID. Deja la carpeta anterior intacta.

Para seguir usando tu carpeta, revisa en el administrador de archivos del NAS:

1. `DATA_DIR` apunta a la carpeta local correcta y el montaje permite escritura.
2. `APP_UID` y `APP_GID` corresponden al usuario/grupo con acceso a esa carpeta. El valor 10001 es un valor por defecto; puede no coincidir con ninguna cuenta de tu NAS.
3. Los permisos y las ACL permiten a esa cuenta recorrer la ruta, crear archivos y modificar la base si ya existe. También debe haber espacio libre.
4. Después de corregir variables o permisos, recrea el contenedor en Dockhand.

La aplicación comprueba el acceso al iniciar y muestra la ruta, el UID/GID real y el error de almacenamiento. No cambia propietarios ni busca otra carpeta automáticamente.

- **Git no está instalado:** conserva el contexto `.tar.gz`; no uses `.git#main`.
- **No encuentra el Dockerfile o aparece una ruta `https:/.../Dockerfile`:** pega el Compose actual completo, con `dockerfile_inline`, y conserva `SOURCE_DIR: pastillas-main`.
- **No se construye:** activa build/rebuild al desplegar.
- **Sin permisos en `/data`:** revisa el propietario y las ACL de la carpeta y `APP_UID`/`APP_GID`.
- **Puerto ocupado:** cambia `APP_PORT`.
- **Usuario inicial no cambia:** las variables solo crean la primera cuenta cuando no hay ninguna. Cambia la contraseña desde Ajustes o con la herramienta de recuperación.
- **Avisos ausentes:** revisa [avisos](avisos.md); la agenda sigue disponible aunque ntfy no responda.
