# Pastillas

Tu botiquín, al día. Aplicación web en español para gestionar **medicamentos, recetas, tomas y existencias**, alojada en tu propio servidor con Docker. Interfaz adaptable a móvil y escritorio, fondo blanco y verde de farmacia, tema oscuro opcional y acceso por usuario.

## Instalar con Dockhand

**Opción sin configurar permisos de carpetas:** pega [compose.dockhand.volume.yaml](compose.dockhand.volume.yaml). Docker crea un volumen persistente con los permisos correctos. Solo necesitas tu usuario, contraseña y un puerto libre; no utiliza `DATA_DIR`, `APP_UID` ni `APP_GID`. Conserva el mismo nombre del stack y su volumen al actualizar. Esta opción crea un botiquín nuevo: no importa datos de una carpeta anterior.

**Opción con carpeta propia del NAS:** sigue los pasos siguientes.

El mismo método que en [Listasdelacompra](https://github.com/kadyto/Listasdelacompra) y [no-lo-vuelvas-a-ver](https://github.com/kadyto/no-lo-vuelvas-a-ver): pega [compose.dockhand.yaml](compose.dockhand.yaml), configura las variables y despliega con **build habilitado**. Docker descarga el archivo público de GitHub y construye automáticamente. **No tienes que crear una imagen previamente, instalar Git ni usar una terminal.**

1. Crea una carpeta de datos en tu NAS y dale permiso de escritura al UID/GID del contenedor.
2. En Dockhand, abre **Stacks → New Stack** y pega el Compose completo.
3. Define `DATA_DIR` (ruta absoluta), `INITIAL_ADMIN_USER` y `INITIAL_ADMIN_PASSWORD` (12–256 caracteres). Configura `APP_UID`/`APP_GID` con el propietario de la carpeta; ambos son `10001` por defecto.
4. Despliega construyendo la imagen y espera al estado **healthy**.
5. Abre `http://IP_DEL_SERVIDOR:8092` e inicia sesión.

Instrucciones, proxy HTTPS y actualizaciones: **[guía de Dockhand](docs/dockhand.md)**.

Puedes acceder desde cualquier dominio, IP o puerto; no hay una URL pública fija ni una variable `PUBLIC_URL` que configurar. `COOKIE_SECURE=auto` detecta HTTPS a través de Nginx Proxy Manager y también permite el acceso HTTP directo. [Configuración del proxy](docs/dockhand.md#nginx-proxy-manager).

## Qué puedes hacer

- **Medicamentos libres:** nombre, marca, presentación (pastillas, gotas, jarabes, cápsulas, cremas…), concentración del envase e indicaciones.
- **Caducidad opcional:** guarda la fecha del envase al crear o editar un medicamento, también si lo tomas según necesidad. Se muestra en Medicamentos y Existencias, resaltando si caduca hoy o ya ha caducado. Si tienes varios envases, indica la fecha más próxima.
- **Versión y actualizaciones:** pie con GitHub, versión instalada, comprobación diaria y **Comprobar ahora**. La cuenta administradora puede **Actualizar con Dockhand** si se configura el webhook de su stack Git. [Configuración de actualizaciones](docs/actualizaciones.md).
- **Cantidades fraccionarias:** media pastilla, 5 ml o 2 gotas, con hasta tres decimales. Se usan milésimas enteras internamente para evitar errores de redondeo.
- **Pautas:** cada 6, 8, 12, 24 horas o intervalo personalizado de 1–720 horas; horas fijas del día; según necesidad. Fecha de inicio, fin opcional, zona horaria y pausa.
- **Agenda automática:** las tomas programadas se asumen y descuentan del stock a su hora, sin tener que marcarlas. Puedes indicar «No la tomé» para devolver el descuento. Las tomas según necesidad se registran manualmente.
- **Existencias:** compras, precio opcional, correcciones y **Comprobar stock** para comparar la previsión con la cantidad contada y guardar la revisión; historial de movimientos. Previsión de la primera toma futura que no se podrá cubrir y antelación de reposición configurable por medicamento.
- **Recetas:** referencia, profesional, indicaciones y fecha de renovación; vinculación con medicamentos y aviso desde siete días antes.
- **Información de medicamentos:** búsqueda por nombre o URL de Vademécum, selección de envase CIMA/AEMPS, prospecto y ficha técnica dentro de la app, notas de seguridad y problemas de suministro. Comprobaciones al entrar, con caché persistente de 12 horas. Las equivalencias internacionales públicas de Vademécum se consultan por país dentro de la app. [Uso y alcance de la integración](docs/informacion-medicamentos.md).
- **Avisos:** en la app, en el navegador con la web abierta y, opcionalmente, en el móvil con **ntfy aunque cierres la web**.
- **Usuarios:** la cuenta administradora puede crear cuentas desde Ajustes. Cada persona tiene sus propios datos, pautas y avisos.
- **Datos:** SQLite persistente, exportación personal JSON y herramienta de copia consistente del servidor.

La aplicación empieza vacía. Los medicamentos y sus pautas los introduce el usuario siguiendo su prescripción; no hay recomendaciones ni cálculos de dosis clínicas.

## Primer medicamento

1. Pulsa **Añadir medicamento**.
2. Introduce el nombre, la presentación y la concentración del envase.
3. Elige una unidad común para las existencias, las compras y las tomas. Por ejemplo, `ml` para un jarabe y `pastillas` para comprimidos.
4. Indica la cantidad por toma y el total disponible. Dos cajas de 30 pastillas son **60 pastillas**, no 2 cajas.
5. Configura la pauta y la primera toma. Las fechas del formulario usan la zona horaria indicada allí.
6. Las tomas programadas se descontarán automáticamente a su hora. Si no tomas una, pulsa **No la tomé**. En **Existencias**, registra compras y utiliza **Comprobar stock** para contar lo que queda.

No se convierten unidades: si cuentas gotas, registra existencias en gotas; si cuentas mililitros, también la cantidad por toma debe estar en mililitros. La concentración del envase es un campo informativo libre.

## Horarios y previsiones

Los intervalos son horas reales desde la primera toma, incluidas las noches. Las horas fijas siguen el reloj local de la zona elegida. En el cambio a horario de verano, una hora fija inexistente se desplaza hacia delante por el salto de hora; dos horas que coincidan se cuentan como una toma. En el cambio de otoño, una hora repetida se programa una sola vez, en su primera aparición. No se admite una fecha de inicio local inexistente. Se conservan las tomas registradas al editar o pausar una pauta.

La previsión parte de las existencias actuales y cuenta las **tomas futuras**. Las tomas programadas vencidas se registran como **asumidas** y se descuentan automáticamente; esto es una estimación de inventario, no una confirmación de que hayas ingerido el medicamento. Las tomas anteriores al alta o a la actualización del cálculo no se descuentan retroactivamente. La primera toma futura sin cantidad suficiente es la fecha de reposición mostrada. Si las existencias cubren todo un tratamiento con fecha de fin, se indica expresamente. Los medicamentos según necesidad muestran tomas disponibles, sin inventar una fecha de agotamiento. Las previsiones diarias se limitan al año 2100.

Los descuentos y avisos de toma se procesan cada 30 segundos. Si el contenedor se apaga, los descuentos pendientes se recuperan al arrancar, sin repetirlos. Los avisos tienen una ventana de recuperación de 10 minutos; no se envía una acumulación de avisos antiguos tras apagar el NAS. Las existencias y recetas generan como máximo un aviso diario por registro. Se guardan 90 días de avisos y el historial completo de tomas y movimientos. [Descuento automático y comprobaciones de stock](docs/stock-automatico.md). El servidor debe estar encendido y con su reloj correcto.

## Avisos en el móvil

En **Ajustes**, utiliza el tema aleatorio generado para tu cuenta, suscríbete a él en ntfy y activa el envío. [Configuración y privacidad de avisos](docs/avisos.md).

Las notificaciones de navegador necesitan HTTPS o localhost y que la app siga abierta. Instalarla en la pantalla de inicio no convierte esos avisos en notificaciones con la web cerrada. Para eso utiliza ntfy.

## Desarrollo local

Python **3.12 o posterior**, con zona horaria IANA disponible. No necesita npm, pip, base de datos externa ni dependencias Python.

```bash
python -m app.server
```

Abre `http://localhost:8000`. Sin variables de administrador, la primera visita permite crear la cuenta inicial. En Docker, el Compose exige usuario y contraseña propios y los crea al iniciar una base vacía. Cambiar las variables después no cambia una contraseña ya guardada.

```bash
python -m unittest discover -s tests -v
node --check app/static/app.js
```

## Copias y mantenimiento

Consulta **[mantenimiento](docs/mantenimiento.md)** para realizar una copia SQLite consistente, restaurar el servidor, recuperar una contraseña y exportar datos. La exportación JSON es un archivo de consulta y portabilidad; no existe un botón de importación/restauración JSON.

Arquitectura: Python estándar + servidor HTTP con hilos + SQLite WAL + JavaScript sin compilación. El contenedor funciona sin privilegios, con sistema de archivos de solo lectura salvo `/data` y `/tmp`. No incorpora CDN, fuentes remotas ni analítica. La información opcional de medicamentos consulta la API pública de CIMA/AEMPS; el envío opcional a ntfy también necesita una conexión externa.
