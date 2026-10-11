# Pastillas

Tu botiquín, al día. Aplicación web en español para gestionar **medicamentos, recetas, tomas y existencias**, alojada en tu propio servidor con Docker. Interfaz adaptable a móvil y escritorio, tema claro/oscuro y acceso por usuario.

## Instalar con Dockhand

El mismo método que en [Listasdelacompra](https://github.com/kadyto/Listasdelacompra) y [no-lo-vuelvas-a-ver](https://github.com/kadyto/no-lo-vuelvas-a-ver): pega [compose.dockhand.yaml](compose.dockhand.yaml), configura las variables y despliega con **build habilitado**. Docker descarga el archivo público de GitHub y construye automáticamente. **No tienes que crear una imagen previamente, instalar Git ni usar una terminal.**

1. Crea una carpeta de datos en tu NAS y dale permiso de escritura al UID/GID del contenedor.
2. En Dockhand, abre **Stacks → New Stack** y pega el Compose completo.
3. Define `DATA_DIR` (ruta absoluta), `INITIAL_ADMIN_USER` y `INITIAL_ADMIN_PASSWORD` (12–256 caracteres). Configura `APP_UID`/`APP_GID` con el propietario de la carpeta; ambos son `10001` por defecto.
4. Despliega construyendo la imagen y espera al estado **healthy**.
5. Abre `http://IP_DEL_SERVIDOR:8092` e inicia sesión.

Instrucciones, proxy HTTPS y actualizaciones: **[guía de Dockhand](docs/dockhand.md)**.

## Qué puedes hacer

- **Medicamentos libres:** nombre, marca, presentación (pastillas, gotas, jarabes, cápsulas, cremas…), concentración del envase e indicaciones.
- **Cantidades fraccionarias:** media pastilla, 5 ml o 2 gotas, con hasta tres decimales. Se usan milésimas enteras internamente para evitar errores de redondeo.
- **Pautas:** cada 6, 8, 12, 24 horas o intervalo personalizado de 1–720 horas; horas fijas del día; según necesidad. Fecha de inicio, fin opcional, zona horaria y pausa.
- **Agenda:** consulta cualquier día; confirma, omite o deshaz una toma. Una toma confirmada descuenta sus existencias una sola vez. Las omitidas no consumen nada. No permite confirmar si falta cantidad.
- **Existencias:** compras, precio opcional y correcciones del total contado; historial de movimientos. Previsión de la primera toma futura que no se podrá cubrir y antelación de reposición configurable por medicamento.
- **Recetas:** referencia, profesional, indicaciones y fecha de renovación; vinculación con medicamentos y aviso desde siete días antes.
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
6. En **Hoy**, pulsa **Tomada** después de tomarla. En **Existencias**, registra las siguientes compras.

No se convierten unidades: si cuentas gotas, registra existencias en gotas; si cuentas mililitros, también la cantidad por toma debe estar en mililitros. La concentración del envase es un campo informativo libre.

## Horarios y previsiones

Los intervalos son horas reales desde la primera toma, incluidas las noches. Las horas fijas siguen el reloj local de la zona elegida. En el cambio a horario de verano, una hora fija inexistente se desplaza hacia delante por el salto de hora; dos horas que coincidan se cuentan como una toma. En el cambio de otoño, una hora repetida se programa una sola vez, en su primera aparición. No se admite una fecha de inicio local inexistente. Se conservan las tomas registradas al editar o pausar una pauta.

La previsión parte de las existencias actuales y cuenta las **tomas futuras**. Las tomas pasadas pendientes no se descuentan ni se dan por tomadas. La primera toma futura sin cantidad suficiente es la fecha de reposición mostrada. Si las existencias cubren todo un tratamiento con fecha de fin, se indica expresamente. Los medicamentos según necesidad muestran tomas disponibles, sin inventar una fecha de agotamiento. Las previsiones diarias se limitan al año 2100.

Los avisos de toma se generan cada 30 segundos, con una ventana de recuperación de 10 minutos; no se envía una acumulación de avisos antiguos tras apagar el NAS. Las existencias y recetas generan como máximo un aviso diario por registro. Se guardan 90 días de avisos y el historial completo de tomas y movimientos. El servidor debe estar encendido y con su reloj correcto.

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

Arquitectura: Python estándar + servidor HTTP con hilos + SQLite WAL + JavaScript sin compilación. El contenedor funciona sin privilegios, con sistema de archivos de solo lectura salvo `/data` y `/tmp`. No incorpora CDN, fuentes remotas, analítica ni servicios médicos externos. Solo el envío opcional a ntfy necesita una conexión externa durante el uso.
