# Política de privacidad de Pastillas para Android

Fecha: 19 de octubre de 2026.

Esta política corresponde a la aplicación Android de código abierto Pastillas,
cuyo proyecto se encuentra en <https://github.com/kadyto/pastillas>. La versión
web autohospedada tiene un almacenamiento y una configuración de servicios
distintos.

## Datos que guarda la aplicación

Pastillas guarda en una base SQLite privada del dispositivo los medicamentos,
marcas, presentaciones, pautas, tomas, existencias, caducidades, recetas,
indicaciones e historial que introduzcas, además de preferencias y avisos.

No crea una cuenta remota ni envía el botiquín a un servidor del proyecto.
No incluye publicidad, analítica de uso ni rastreadores. La gestión del botiquín,
los recordatorios y las copias locales funcionan sin internet.

La aplicación usa el almacenamiento privado protegido por Android. No incorpora
una contraseña o cifrado de base de datos adicional al del sistema. La protección
del dispositivo y sus ajustes de bloqueo siguen siendo relevantes para el acceso
a tus datos.

## Consultas externas opcionales

Las consultas a AEMPS y Vademécum están desactivadas en una instalación nueva.
Puedes activarlas o desactivarlas en Ajustes.

Al activarlas y buscar o vincular medicamentos:

- CIMA/AEMPS recibe los nombres o códigos utilizados en búsquedas y los
  identificadores necesarios para consultar fichas, documentos, avisos y
  problemas de suministro de los medicamentos vinculados.
- Vademécum recibe la consulta de la página del medicamento y el país elegido
  para las equivalencias internacionales.
- Los servicios reciben la conexión desde tu dispositivo, incluida su dirección
  IP y los datos habituales de una conexión HTTPS. Aplican sus propias políticas
  de privacidad y condiciones de uso.

Estas consultas no incluyen las existencias, el historial de tomas, las recetas
ni las notas personales del botiquín. Sus respuestas se guardan temporalmente en
la base local para reducir consultas y mostrar la última información disponible.
Las comprobaciones automáticas de medicamentos vinculados respetan una caché de
12 horas; las consultas y reintentos manuales pueden producir conexiones adicionales.

Desactivar las fuentes impide nuevas consultas de la aplicación. No elimina las
consultas que los servicios ya hayan recibido ni su información almacenada en la
caché local. El botiquín sigue funcionando sin esas fuentes.

Si abres un enlace externo —por ejemplo, el repositorio o una página original de
un medicamento— se abrirá el navegador del dispositivo y se aplicarán sus ajustes
y la política del sitio visitado.

## Permisos

- **Internet y estado de red:** consultas externas opcionales y comprobación de
  disponibilidad de conexión. La interfaz y la base local no necesitan un servidor.
- **Notificaciones:** mostrar recordatorios locales si concedes el permiso.
- **Alarmas precisas:** solicitar a Android que entregue recordatorios a la hora
  prevista. Su concesión depende de los ajustes del dispositivo.
- **Inicio del dispositivo:** reprogramar los recordatorios después de reiniciar.

La aplicación no solicita acceso general a tus archivos. Las copias se importan
o exportan mediante el selector de documentos de Android, para el archivo que
elijas.

## Copias, conservación y eliminación

Los datos permanecen en el dispositivo hasta que los elimines. La copia automática
de los datos de la app en la nube de Android está desactivada.

**Exportar copia** genera un archivo JSON con los datos del botiquín. El archivo
contiene datos de salud y no tiene cifrado adicional. Tú eliges dónde guardarlo;
si eliges un proveedor de almacenamiento en la nube, ese proveedor recibirá el
archivo según tus instrucciones. La aplicación no elige ni configura ese destino.

**Importar copia** lee el archivo elegido en el teléfono. No lo envía a un servidor.
No importa contraseñas ni credenciales de la instalación web.

Puedes eliminar los datos desde **Ajustes → Borrar botiquín local**, borrando los
datos de la aplicación en Android o desinstalándola. Las copias que hayas exportado
y los datos que puedan conservar los servicios externos no se borran al hacerlo.
Los avisos de la aplicación se conservan hasta 90 días.

## Contacto y cambios

El código, las incidencias y las vías públicas de contacto del proyecto están en
<https://github.com/kadyto/pastillas>. No incluyas datos de salud ni copias del
botiquín en incidencias públicas.

El editor de cada distribución debe mantener sus datos de contacto actualizados
en la ficha de la tienda y publicar esta política en una URL accesible. Los cambios
en el tratamiento de datos deben reflejarse en esta política y en la aplicación.
