# Avisos

## En la app

La campana muestra avisos de toma, existencias y renovación de recetas. Las tomas se registran únicamente al confirmarlas; un aviso nunca consume existencias. Se pueden marcar todos los avisos como leídos.

Los avisos de cada toma se activan en el formulario del medicamento. Los avisos de existencias y recetas se activan en Ajustes. Los de recetas comienzan siete días antes de su renovación; los de existencias dependen de los días de antelación de cada medicamento.

## En el navegador

Desde Ajustes, pulsa **Activar avisos del navegador** y concede el permiso. La preferencia se guarda por cuenta y dispositivo. Necesita HTTPS o localhost, soporte de notificaciones y que la aplicación siga abierta y pueda actualizarse. Un navegador suspendido por el móvil puede no mostrar los avisos. No se almacena información médica en el service worker ni se permite registrar tomas sin conexión.

## En el móvil con la web cerrada

1. Instala ntfy en Android o iOS y permite sus notificaciones.
2. En Ajustes de Pastillas, consulta el servidor y el tema generado para tu usuario.
3. En ntfy, suscríbete a ese servidor y a ese tema exacto.
4. Activa **Enviar avisos a ntfy aunque cierre la web** y guarda.

El contenedor publica los avisos en ntfy. Necesita conexión saliente al servidor ntfy. Pastillas no comprueba que tu móvil esté suscrito ni que el sistema operativo haya mostrado la notificación: el estado **Enviado a ntfy** significa que el servidor ntfy ha aceptado la publicación.

El tema generado contiene un valor aleatorio largo. En el servicio público ntfy, quien conozca el tema podría leer sus mensajes; no lo compartas. Los avisos contienen el nombre del medicamento, la cantidad y las indicaciones, o la receta y su fecha. El envío está desactivado por defecto y solo se activa cuando lo eliges.

Para alojar también los avisos en tu infraestructura, define `NTFY_BASE_URL` en Dockhand con la dirección de tu servidor ntfy. Si requiere autenticación, define `NTFY_TOKEN` con un token autorizado para publicar en los temas usados. El token se guarda como variable del contenedor y nunca se entrega al navegador. La autenticación para suscribirse se configura en la aplicación ntfy del móvil. En iOS con servidor propio, revisa la configuración de entrega de ntfy para APNs/upstream; esa configuración pertenece a ntfy.

## Comportamiento

El proceso revisa las pautas cada 30 segundos. Los avisos de toma tienen una ventana de 10 minutos. Tras una parada prolongada del NAS, los anteriores quedan pendientes en la agenda, sin enviar una ráfaga de avisos antiguos. Los de existencias y recetas se emiten como máximo una vez al día por registro mientras siga la condición.

Los envíos fallidos se reintentan hasta cinco veces dentro de diez minutos. No se envían avisos antiguos cuando activas ntfy más tarde. Una interrupción entre la aceptación de ntfy y su registro local puede causar un aviso duplicado; nunca duplica una toma ni su consumo. Los fallos de entrega no afectan al registro de tratamientos.

Si no llegan avisos, revisa el estado de ntfy en la campana, la suscripción exacta, los permisos del móvil, la conectividad del NAS y los registros de Dockhand. El contenedor y el móvil deben estar disponibles; la web puede estar cerrada.
