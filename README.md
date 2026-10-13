# Pastillas

Pastillas es una aplicación web autohospedada para organizar medicamentos, recetas, horarios de toma y existencias. Permite registrar un tratamiento, calcular el consumo previsto y anticipar la reposición de medicamentos.

Se instala con Docker y guarda los datos en el servidor. La interfaz está en español, se adapta a móviles y ordenadores y ofrece tema claro y oscuro. Cada cuenta dispone de su propio botiquín.

## Funcionalidades

- **Medicamentos:** nombre, marca, presentación, concentración, cantidad por toma y fecha de caducidad opcional. Admite comprimidos, cápsulas, jarabes, gotas y otras presentaciones, con cantidades fraccionarias.
- **Pautas y agenda:** intervalos personalizados, horas fijas del día o tomas según necesidad. Los tratamientos pueden tener fecha de fin o ponerse en pausa.
- **Control de existencias:** descuento automático de las tomas programadas, registro de compras, recuentos manuales e historial de movimientos. La previsión de consumo permite estimar cuándo será necesaria una reposición.
- **Recetas:** referencia, profesional, indicaciones, medicamentos vinculados y recordatorio de renovación.
- **Información de medicamentos:** búsqueda por nombre o URL de Vademécum, prospectos y fichas técnicas de CIMA/AEMPS, avisos de seguridad y problemas de suministro. Las equivalencias internacionales de Vademécum se consultan por país.
- **Notificaciones:** avisos dentro de la aplicación, notificaciones del navegador y envío opcional a ntfy para recibir recordatorios con la web cerrada.
- **Cuentas independientes:** la cuenta administradora crea usuarios; cada usuario accede a sus medicamentos, recetas y avisos.
- **Versiones:** comprobación diaria de GitHub, consulta manual y actualización mediante un webhook de Dockhand.

## Instalación con Docker

Se necesita un servidor con Docker y Docker Compose. Los archivos de instalación para Dockhand requieren Docker Compose 2.17 o posterior. Durante la construcción debe haber acceso a GitHub y al registro de imágenes de Docker.

### Desde Dockhand

Los archivos Compose descargan el código de este repositorio y construyen la imagen durante el despliegue. Hay dos opciones de almacenamiento:

| Almacenamiento | Archivo Compose | Configuración |
| --- | --- | --- |
| Volumen persistente gestionado por Docker | [compose.dockhand.volume.yaml](compose.dockhand.volume.yaml) | Docker crea el volumen y establece sus permisos. |
| Carpeta del servidor o NAS | [compose.dockhand.yaml](compose.dockhand.yaml) | Requiere una carpeta existente y permisos de escritura para el usuario del contenedor. |

1. Crea un stack en Dockhand y copia el contenido del Compose elegido.
2. Define `INITIAL_ADMIN_USER` y `INITIAL_ADMIN_PASSWORD`. La contraseña debe tener entre 12 y 256 caracteres.
3. Configura `APP_PORT` si necesitas cambiar el puerto de acceso; el valor predeterminado es `8092`.
4. Si utilizas una carpeta del servidor, define `DATA_DIR` con su ruta absoluta. Ajusta `APP_UID` y `APP_GID` al propietario de la carpeta; ambos son `10001` de forma predeterminada.
5. Despliega con la construcción de la imagen habilitada y espera a que el contenedor indique el estado `healthy`.
6. Abre `http://IP_DEL_SERVIDOR:8092`, o el puerto configurado, e inicia sesión con la cuenta administradora.

Las variables de administrador crean la cuenta en una base de datos nueva. Las contraseñas de cuentas existentes se gestionan desde la aplicación.

Consulta la [guía de Dockhand](docs/dockhand.md) para conocer las variables disponibles, los permisos de almacenamiento y la configuración del proxy.

### Desde Docker Compose

Clona el repositorio y prepara el archivo de configuración:

```bash
git clone https://github.com/kadyto/pastillas.git
cd pastillas
cp .env.example .env
```

Edita `.env` para establecer el usuario, la contraseña y la ruta `DATA_DIR`. Crea esa carpeta y configura sus permisos de escritura para el UID/GID indicado. A continuación, construye y arranca el servicio:

```bash
docker compose up --build -d
```

El archivo [compose.yaml](compose.yaml) utiliza el código local del repositorio. El puerto predeterminado de acceso es `8092`.

### Acceso mediante HTTPS

La aplicación puede publicarse con un proxy inverso, incluido Nginx Proxy Manager. El proxy debe apuntar al puerto publicado del servicio o al puerto `8000` dentro del contenedor.

`COOKIE_SECURE=auto` configura la cookie de sesión según el acceso HTTP o HTTPS; detrás del proxy utiliza el encabezado `X-Forwarded-Proto`. Consulta la [configuración de Nginx Proxy Manager](docs/dockhand.md#nginx-proxy-manager).

## Primeros pasos

1. Pulsa **Añadir medicamento** e introduce el nombre, la presentación y la concentración del envase.
2. Elige la unidad de existencias y la cantidad por toma. Las compras y las tomas deben utilizar la misma unidad: por ejemplo, `ml` para un jarabe o `pastillas` para comprimidos.
3. Registra la cantidad disponible. Dos cajas de 30 comprimidos corresponden a 60 unidades de existencias.
4. Configura el horario o selecciona **Según necesidad**. Puedes añadir indicaciones, una receta vinculada y la fecha de caducidad.
5. En **Existencias**, registra las compras y utiliza **Comprobar stock** para ajustar el inventario a un recuento físico.

Las pautas y cantidades deben corresponder al tratamiento indicado por el profesional sanitario. La concentración del envase es un dato informativo; la aplicación utiliza la cantidad y la unidad introducidas para calcular el consumo.

### Cómo se calcula el stock

Las tomas con horario se consideran realizadas cuando llega su hora y se descuentan automáticamente del inventario. Si se omite una toma, **No la tomé** devuelve su descuento al stock. Las tomas según necesidad se registran manualmente, porque su frecuencia depende del uso.

El stock calculado es una estimación basada en la pauta registrada. Puede verificarse y corregirse mediante un recuento físico. La previsión de reposición indica la primera toma futura que las existencias no cubrirían; los tratamientos según necesidad muestran la cantidad de tomas disponibles.

La caducidad se registra por medicamento. Si se conservan varios envases con fechas distintas, debe indicarse la fecha más próxima. La fecha aparece en **Medicamentos** y **Existencias**, con un indicador cuando caduca ese día o ya ha caducado.

Consulta el [funcionamiento del descuento automático y los recuentos](docs/stock-automatico.md) para conocer el tratamiento de pausas, cambios de pauta y reinicios del servidor.

### Avisos e información externa

Los avisos del navegador requieren HTTPS o localhost y que la web permanezca abierta. Para recibir recordatorios con la web cerrada, puede configurarse ntfy desde **Ajustes**.

La consulta de información de medicamentos es opcional. Los documentos y avisos proceden de CIMA/AEMPS; las equivalencias internacionales proceden de las páginas públicas de Vademécum. Las comprobaciones de seguridad y suministro al iniciar sesión se conservan durante 12 horas. Cada apartado identifica su fuente y su estado de actualización.

## Datos, copias y actualizaciones

Los datos se almacenan en SQLite dentro de la carpeta o el volumen montado en `/data`. Al actualizar, deben conservarse ese almacenamiento y el nombre del proyecto Docker.

Desde **Ajustes** puede descargarse una exportación JSON de los datos de una cuenta. Para realizar copias completas y restaurar el servidor se incluye una herramienta de copia SQLite consistente. Los procedimientos están descritos en la [guía de mantenimiento](docs/mantenimiento.md).

El pie de la aplicación muestra la versión instalada y comprueba GitHub cada 24 horas. **Comprobar ahora** permite solicitar una consulta adicional. La cuenta administradora puede actualizar desde la aplicación si se configura el webhook de su stack Git en Dockhand; el procedimiento y las variables necesarias están en la [guía de actualizaciones](docs/actualizaciones.md).

Para una actualización manual, descarga el código actualizado, reconstruye la imagen y recrea el stack conservando sus datos. En los Compose de Dockhand, la construcción obtiene el contenido de la rama `main`.

## Documentación

| Guía | Contenido |
| --- | --- |
| [Instalación con Dockhand](docs/dockhand.md) | Almacenamiento, variables, proxy HTTPS y resolución de problemas. |
| [Stock automático](docs/stock-automatico.md) | Tomas asumidas, omisiones, recuentos y previsiones de consumo. |
| [Información de medicamentos](docs/informacion-medicamentos.md) | Vinculación con CIMA/AEMPS y Vademécum, documentos y alcance de los avisos. |
| [Notificaciones](docs/avisos.md) | Configuración de ntfy y avisos del navegador. |
| [Actualizaciones](docs/actualizaciones.md) | Comprobación de versiones y webhook de Dockhand. |
| [Mantenimiento](docs/mantenimiento.md) | Copias, restauración, exportación y recuperación de cuentas. |

## Desarrollo local

La aplicación utiliza Python estándar, SQLite y JavaScript sin compilación. Para ejecutarla fuera de Docker se necesita Python 3.12 o posterior con zonas horarias IANA disponibles.

Desde la raíz del repositorio:

```bash
python -m app.server
```

Abre `http://localhost:8000`. En una instalación local nueva, la primera visita permite crear la cuenta administradora.

Las comprobaciones del proyecto pueden ejecutarse con:

```bash
python -m unittest discover -s tests -v
node --check app/static/app.js
```
