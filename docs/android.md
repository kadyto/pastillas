# Pastillas para Android

La aplicación Android incluye la interfaz, el motor de pautas y la base SQLite
dentro de su paquete. No levanta un servidor HTTP, no abre un puerto local y no
necesita Docker, cuentas remotas ni un backend. Los datos se guardan en el
almacenamiento privado del dispositivo.

Requiere **Android 8 o posterior** y un dispositivo **ARM64 o x86-64**. El proyecto
usa API 36 como destino y empaqueta bibliotecas compatibles con páginas de 16 KB.

## Funciones sin conexión

- Medicamentos con nombre y presentación libres, dosis fraccionarias y caducidad.
- Pautas por intervalos, horas fijas o según necesidad, con zona horaria por pauta.
- Descuento automático, compras, recuentos y corrección de tomas omitidas.
- Recetas, agenda, previsión de reposición e historial.
- Recordatorios locales de Android, también con la actividad cerrada.
- Exportación e importación de copias JSON, sin enviar el archivo a un servidor.

El stock se recupera de forma idempotente al ejecutar el trabajo de mantenimiento
o abrir la aplicación, incluyendo las tomas previstas mientras el teléfono estaba
apagado. Los medicamentos según necesidad se descuentan al registrar su uso.

## Recordatorios

En **Ajustes**, activa los recordatorios y concede el permiso de notificaciones.
Para respetar la hora programada, concede también **Alarmas precisas**. Si ese
permiso no está disponible, se utilizan alarmas de Android que pueden retrasarse.
El mantenimiento periódico de stock y recetas utiliza WorkManager y funciona sin
red. Android decide cuándo ejecutar este trabajo de fondo.

Las alarmas se reprograman después de reiniciar el dispositivo, actualizar la app
o cambiar el reloj. Si se fuerza la detención de la aplicación en Ajustes de
Android, es necesario abrirla de nuevo. Algunos fabricantes restringen las apps
en ahorro de batería; sus ajustes pueden afectar a los recordatorios.

Los avisos ocultan su contenido en la pantalla bloqueada de forma predeterminada,
sujeto a los ajustes de notificaciones del dispositivo.

## AEMPS y Vademécum

**Consultar AEMPS y Vademécum** está desactivado en una instalación nueva.
Activarlo permite la búsqueda y vinculación de medicamentos, los documentos,
las equivalencias internacionales y las comprobaciones de avisos. La aplicación
explica qué consultas se envían antes de activarlo.

Las comprobaciones automáticas de medicamentos vinculados tienen una caché de
12 horas. **Información → Reintentar comprobación** solicita una consulta manual
adicional, con un minuto de separación entre intentos. La disponibilidad de las
fuentes externas no condiciona el uso del botiquín local. Las consultas se
ejecutan fuera de la cola de operaciones locales.

No se utiliza ntfy ni se comprueba GitHub automáticamente desde Android.
Las actualizaciones se distribuyen mediante Google Play o una APK firmada.

## Trasladar el botiquín de la web

1. En la versión web, abre **Ajustes → Exportar mis datos**.
2. Guarda el archivo JSON en una ubicación accesible desde el teléfono.
3. En Android, abre **Ajustes → Importar copia** y selecciona el archivo.
4. Revisa el número de medicamentos y confirma la importación.

La importación añade recetas, medicamentos, caducidades, pautas, stock,
historial y vinculaciones. Reasigna los identificadores para conservar las
relaciones con los datos existentes y se revierte completa si hay un error.
No se importan cuentas, contraseñas, sesiones ni credenciales de ntfy o Dockhand.
No se consulta internet para importar. Repetir exactamente la misma copia no
duplica sus datos. Se admiten exportaciones de formato Pastillas 3 o 4, hasta 10 MB.

**Exportar copia** utiliza el selector de archivos de Android. La copia JSON
contiene datos de salud y debe guardarse en un lugar privado. La aplicación no
activa copias automáticas de Android en la nube. Desinstalarla o borrar sus datos
elimina el botiquín local; las copias exportadas se conservan en su ubicación.

La aplicación no sincroniza cambios entre la web y el teléfono.

## Descargar una compilación de pruebas

El workflow [Android](https://github.com/kadyto/pastillas/actions/workflows/android.yaml)
genera el artefacto **pastillas-android** con:

- `pastillas-android-pruebas.apk`: APK instalable para probar la aplicación.
- `pastillas-google-play-sin-firmar.aab`: bundle de producción cuando no hay firma
  configurada. Necesita firmarse antes de enviarlo a Google Play.
- `SHA256SUMS.txt`: sumas de comprobación.

Las descargas de artefactos de Actions requieren iniciar sesión en GitHub y se
conservan 30 días. La APK de pruebas tiene un identificador distinto
(`io.github.kadyto.pastillas.debug`) y aparece como **Pastillas (pruebas)**. Sus
datos están separados de la aplicación de producción. Exporta una copia para
trasladarlos. Las claves de pruebas de diferentes compilaciones pueden cambiar;
no sirven como firma de publicación.

## Compilar localmente

Se necesitan JDK 21, Python 3.12 y Android SDK con `platforms;android-36` y
`build-tools;36.0.0`. Android Studio puede instalar el SDK. Configura su ruta en
`android/local.properties` (`sdk.dir=/ruta/al/sdk`) o mediante `ANDROID_HOME`.

Desde la carpeta `android`:

```bash
./gradlew :app:assembleDebug :app:bundleRelease :app:lintDebug
```

Resultados:

- APK de pruebas: `app/build/outputs/apk/debug/app-debug.apk`.
- AAB: `app/build/outputs/bundle/release/app-release.aab`.

Chaquopy incluye Python y `tzdata` en el paquete durante la compilación; no
descarga código ni dependencias al ejecutar la aplicación. Los assets de la web y
los módulos compartidos se copian a directorios generados durante el build. No
es necesario mantener dos copias de la lógica ni de la interfaz.

## Firma y distribución de producción

El identificador de producción es `io.github.kadyto.pastillas`. Antes de la
primera publicación, el editor debe decidir el identificador definitivo y guardar
su clave de firma o de subida. Las actualizaciones requieren el mismo
identificador, una firma compatible y un `versionCode` creciente.

1. Genera y conserva tu keystore en Android Studio, o con `keytool`.
2. Copia `android/key.properties.example` como `android/key.properties` y configura
   la ruta del keystore, el alias y las contraseñas.
3. Ejecuta `./gradlew :app:assembleRelease :app:bundleRelease`.

La APK firmada se genera en `app/build/outputs/apk/release/app-release.apk` y el
AAB firmado en `app/build/outputs/bundle/release/app-release.aab`. Los keystores y
`key.properties` están excluidos de Git.

Para firmar en GitHub Actions, configura los secretos `ANDROID_KEYSTORE_BASE64`,
`ANDROID_STORE_PASSWORD`, `ANDROID_KEY_ALIAS` y `ANDROID_KEY_PASSWORD`. El workflow
genera entonces `pastillas-android.apk` y `pastillas-google-play.aab`, además de la
APK de pruebas, y elimina los archivos temporales de firma al terminar.

La descarga directa de una APK de producción y la versión de Google Play solo
se pueden actualizar entre sí si utilizan una firma compatible. Si Google Play
genera una clave de firma distinta de la clave de subida, la APK firmada con la
clave de subida no sustituye a la instalada desde Play. Decide la estrategia de
Play App Signing antes de distribuir la primera versión pública.

## Preparación de Google Play

Se distribuye un **AAB firmado**, que debe subirse a la cuenta de Play Console del
editor. La compilación no publica automáticamente la aplicación. Deben completarse
la ficha de la tienda, icono y capturas, política de privacidad, clasificación de
contenido, declaraciones de datos y de funciones de salud, y las pruebas que Play
Console solicite a esa cuenta.

La [política de privacidad Android](privacidad-android.md) describe el
almacenamiento local y las consultas opcionales. Debe publicarse en una URL HTTPS
accesible y revisarse junto con los datos de contacto del editor antes del envío.
Las consultas opcionales a terceros también deben tenerse en cuenta al completar
la declaración de seguridad de los datos.

## Verificación

El workflow compila APK y AAB, ejecuta Android Lint, comprueba las bibliotecas
de 16 KB y la firma de la APK de pruebas. Después instala la APK en un emulador
Android con la red desactivada y prueba altas desde la interfaz, persistencia,
descuento de tomas, una notificación con la actividad cerrada y el arranque normal
después de cerrar completamente el proceso.

Las pruebas Python de operaciones locales bloquean la creación de sockets. La
versión web conserva su workflow de Docker, navegador y proxy HTTP/HTTPS.
