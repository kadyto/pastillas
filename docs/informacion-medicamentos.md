# Información de medicamentos

Disponible desde Pastillas 0.2.0. La vinculación es opcional: se siguen pudiendo
registrar nombres, marcas, jarabes, gotas, dosis y pautas como texto libre.

## Vincular un medicamento

1. Añade o edita un medicamento. También puedes pulsar **Información** en su tarjeta.
2. En **Nombre o URL de Vademécum**, escribe el nombre comercial o pega una URL
   como `https://www.vademecum.es/espana/medicamento/27631/omacor-1000-mg-capsulas-blandas`.
3. Pulsa **Buscar medicamento**. La búsqueda utiliza el catálogo oficial CIMA/AEMPS;
   al pegar una URL, se obtiene el nombre del enlace y se propone una búsqueda.
   El número de la URL de Vademécum no se interpreta como registro CIMA.
4. Elige el medicamento con la concentración y forma correctas y después el
   **envase / código nacional** de tu caja. Confirma y guarda el formulario.

Elegir el envase es necesario: un problema de suministro puede afectar a una
presentación concreta sin afectar a otras del mismo medicamento. La selección
no modifica tu cantidad por toma, horarios, existencias ni historial.

## Qué se puede consultar

Desde **Información** se muestran el nombre oficial, el envase, la fuente y las
fechas de comprobación. Hay cuatro apartados:

- **Prospecto** y **Ficha técnica**: documentos de CIMA/AEMPS, leídos dentro de la
  app por secciones. Se conservan texto, títulos, listas y tablas; las imágenes
  se consultan en el original. También se enlazan los documentos originales y
  PDF. Si AEMPS no proporciona el documento por secciones, se usa el enlace al
  original, sin inventar ni resumir su contenido.
- **Avisos**: notas de seguridad asociadas al medicamento en CIMA y problemas
  de suministro activos del código nacional elegido. Las notas conservan su
  fecha de publicación y pueden ser históricas. Una fecha prevista de fin de
  suministro no implica que el problema se haya resuelto: se comprueba el estado
  activo de la fuente. No se comprueba el lote de tu caja ni se garantiza la
  cobertura de avisos que AEMPS no asocie a la ficha CIMA.
- **Equivalencias**: enlace directo a las equivalencias internacionales de ese
  medicamento en Vademécum. Se necesita su URL. Se abren en la web de Vademécum;
  no se extrae su contenido privado ni se sortean restricciones de acceso.

**Alcance de Vademécum:** durante la comprobación sus páginas devolvieron una
restricción de acceso al cliente web. Esta versión conserva su URL y enlaza sus
equivalencias, pero la búsqueda, los documentos y las comprobaciones automáticas
utilizan la API pública oficial de AEMPS. No necesita una cuenta de Vademécum.
Una integración adicional con contenido o alertas propios de Vademécum requeriría
acceso autorizado a sus servicios. Las equivalencias no son una indicación para
cambiar tu tratamiento ni una confirmación de sustitución.

## Comprobaciones cada 12 horas

Al iniciar sesión o recuperar una sesión existente al abrir la app, se encolan
los medicamentos vinculados cuyo tratamiento está activo y no ha terminado.
La consulta ocurre en segundo plano; entrar no espera a que respondan las fuentes.

Cada medicamento/envase se comprueba como máximo una vez en cualquier período
de **12 horas**. El resultado y el último intento se guardan en SQLite: recargar,
entrar desde otro dispositivo o reiniciar el contenedor no elimina este límite.
No se hacen nuevas consultas automáticas por los refrescos de la pantalla ni
por tener la app abierta. Cuando pasan 12 horas, se consulta al entrar de nuevo.
Al vincular un medicamento también se solicita su primera comprobación.

Las búsquedas y las lecturas de documentos son acciones explícitas del usuario
y también tienen caché de 12 horas por búsqueda/documento. Un intento fallido se
conserva durante 12 horas para evitar consultas repetidas si la fuente está caída.
En ese caso se mantiene el resultado anterior y se muestra que la información
**no está actualizada**, junto con las fechas del último intento y del último éxito.

Las notas y problemas encontrados generan avisos en la app. Si ya tienes ntfy
activado, se aplica la misma entrega de avisos existente. Una nota histórica se
identifica como «disponible», con su fecha; no se presenta como recién publicada.
Cada aviso de una vinculación se genera una sola vez, incluso después de que se
eliminen los avisos de más de 90 días. Quitar una vinculación no borra los avisos
históricos: la ficha **Información** refleja el estado de la vinculación actual.

## Instalación y datos

No se necesita una clave API ni nuevas variables del stack. Dockhand usa los
compose existentes. El contenedor necesita acceso HTTPS saliente a
`cima.aemps.es`; Vademécum se abre desde el navegador. No se envían a las fuentes
tu usuario, contraseña, pauta, tomas, recetas ni existencias. Se consulta el
nombre buscado, el registro del medicamento y el código nacional.

La actualización migra automáticamente la base al esquema 2 y, antes de migrar
una base del esquema 1, guarda una copia consistente en
`DATABASE_PATH.pre-v2.sqlite` (normalmente `/data/pastillas.sqlite.pre-v2.sqlite`).
Conserva las cuentas, sesiones, medicamentos, tomas, recetas y existencias.
La exportación JSON añade `medicine_links`; no exporta la caché pública ni claves.
Haz igualmente una copia de seguridad antes de actualizar tu instalación.

Fuentes: [documentación REST de CIMA](https://sede.aemps.gob.es/docs/CIMA-REST-API_1_19.pdf),
[problemas de suministro de AEMPS](https://www.aemps.gob.es/profesional-sanitario-2/problemas-de-suministro-de-medicamentos/)
y [Vademécum.es](https://www.vademecum.es/).
