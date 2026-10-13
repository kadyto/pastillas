# Versión instalada y actualización con Dockhand

El pie de todas las pantallas incluye GitHub, la versión instalada y el resultado
de su comprobación. **Comprobar ahora** consulta GitHub aunque no hayan pasado
24 horas. Si hay una versión nueva, se indica su número; si GitHub no responde,
se muestra el error y la fecha de la última comprobación correcta.

El servidor comprueba `main` al arrancar si corresponde y después una vez cada
24 horas, aunque nadie abra la web. El resultado y los intentos se conservan en
SQLite: recargar, entrar desde varios móviles o reiniciar el contenedor no causa
nuevas consultas durante ese intervalo. Los fallos también respetan las 24 horas,
salvo que fuerces una comprobación. Solo se envían peticiones del software a GitHub;
no se envían medicamentos ni datos del botiquín.

## Actualizar desde la app

La cuenta administradora puede usar **Actualizar con Dockhand** cuando hay una
versión nueva y está configurado el webhook. Dockhand descarga el repositorio,
reconstruye la imagen y recrea el stack. El contenedor de Pastillas conserva su
configuración de solo lectura; la app no necesita acceso al socket Docker.

Configura una vez la integración en Dockhand:

1. Vincula **el stack existente** con el origen Git
   `https://github.com/kadyto/pastillas`, rama `main` y el Compose que ya utilizas:
   `compose.dockhand.yaml` o `compose.dockhand.volume.yaml`. Si tu versión de Dockhand
   requiere registrar un stack Git, conserva exactamente el nombre del proyecto,
   las variables y la carpeta o el volumen de datos del stack actual; no crees un
   segundo botiquín ni elimines sus volúmenes. Revisa estos valores antes de desplegar.
2. Activa **Build images on deploy** y **Disable build cache** en las opciones
   del stack Git, para reconstruir desde el contenido actualizado de GitHub.
3. Activa su webhook y configura un secreto privado. Copia la URL del webhook,
   que tiene la forma `https://DOCKHAND/api/git/stacks/ID/webhook`.
4. En las variables del stack de Pastillas, indica:

   ```dotenv
   DOCKHAND_WEBHOOK_URL=https://DOCKHAND/api/git/stacks/ID/webhook
   DOCKHAND_WEBHOOK_SECRET=el_secreto_configurado_en_Dockhand
   ```

5. Recrea el contenedor para aplicar las variables. En la app, pulsa
   **Comprobar ahora** y, cuando haya una versión nueva, **Actualizar con Dockhand**.

La URL debe ser accesible desde el contenedor de Pastillas, también por la red
interna del NAS. HTTP interno y HTTPS son compatibles; en HTTPS se valida el
certificado. No pongas el secreto en la URL. La app firma el cuerpo con
HMAC-SHA256 y lo envía en `X-Hub-Signature-256`; el secreto y la URL privada no
se entregan al navegador. También se admite la URL de webhook de un repositorio
Dockhand, `/api/git/webhook/ID`, si ese repositorio ya despliega este mismo stack.

La comprobación diaria **no instala automáticamente** una versión: actualizar
requiere pulsar el botón. Durante el despliegue, la web puede desconectarse y
vuelve a cargar al detectar la nueva versión. Si el resultado queda sin confirmar,
consulta el registro del stack en Dockhand antes de repetir la solicitud. La app
distingue errores, ausencia de cambios y solicitudes recibidas; no afirma que se
haya instalado la actualización hasta detectar el nuevo software.

Referencia: [integración Git y webhooks de Dockhand](https://dockhand.pro/manual/#webhooks).

## Sin webhook

**Cómo actualizar** permite abrir estas instrucciones y **Descargar código de
GitHub**. La descarga por sí sola no cambia la versión del contenedor. En Dockhand
debes reconstruir la imagen y recrear el stack, conservando sus datos; no basta
con reiniciarlo. [Guía de instalación y actualización](dockhand.md#actualizar).

La versión 0.4.0 migra al esquema SQLite 5 y guarda una copia consistente previa
en `DATABASE_PATH.pre-v5.sqlite`. Conserva las cuentas, las sesiones, los
medicamentos, sus caducidades, las existencias y el historial.

## Icono

El icono se utiliza en la cabecera, el favicon, las notificaciones y el manifiesto
de instalación. Los accesos directos antiguos pueden conservar su imagen hasta
que el navegador actualice el manifiesto; en iOS puede ser necesario añadir de
nuevo el acceso a la pantalla de inicio para renovar su icono.
