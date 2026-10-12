# Descuento automático y comprobación del stock

Desde Pastillas 0.3.0 las tomas con horario se asumen y descuentan del inventario
sin tener que marcarlas. La interfaz usa «Asumida» y «Descuento automático»:
es una estimación según la pauta, no una prueba de que hayas tomado el medicamento.

## Cuándo baja el stock

- Las pautas por intervalo y a horas fijas descuentan la cantidad configurada
  cuando llega cada hora de toma. El proceso funciona con la web cerrada y revisa
  las tomas cada 30 segundos. Las pantallas también recuperan los descuentos
  vencidos antes de mostrar el stock.
- Si el contenedor se apaga, al arrancar se recuperan las tomas desde el último
  cálculo guardado, sin descontarlas dos veces. Las compras y correcciones se
  aplican después de recuperar los descuentos vencidos.
- Las pautas **según necesidad** siguen siendo manuales, porque no hay horas ni
  frecuencia para estimar cuándo las tomas.
- Pausar el tratamiento y su fecha de fin detienen los descuentos. Al reanudar
  o cambiar la pauta, se conserva el historial y no se aplica la nueva pauta al
  período anterior.

Los recordatorios siguen funcionando aunque la toma se haya asumido. Se limitan
a los últimos diez minutos para no enviar avisos acumulados tras apagar el NAS.

En **Hoy**, la tarjeta **Tomas descontadas** muestra cuántas tomas ya han aplicado
su descuento, junto al total programado para el día seleccionado. Por ejemplo,
«1 toma descontada de 2 programadas» indica que la otra aún no se ha descontado.
Pulsa la tarjeta para ver el detalle. Los filtros **Próximas**, **Descontadas** y
**Omitidas** permiten consultar cada grupo; no necesitas confirmar las próximas.

## Si no tomaste una dosis

Pulsa **No la tomé** en la agenda. La toma queda omitida y devuelve al stock lo
que se descontó. No cambia la hora de las próximas tomas. Repetir la acción o
reiniciar no vuelve a descontarla ni devuelve la cantidad dos veces.

Si la marcaste omitida por error, pulsa **Sí la tomé** para restaurar el descuento.
El historial identifica las tomas asumidas, confirmadas y omitidas. Deshacer una
toma programada la deja omitida, para que no reaparezca su descuento; deshacer
una toma según necesidad elimina ese registro y devuelve su consumo.

## Comprobar lo que queda

En **Medicamentos** o **Existencias**, pulsa **Comprobar stock**. Cuenta las unidades
reales, incluidas las sueltas, e introduce el total en la unidad del medicamento.
La app compara el stock calculado con lo contado y muestra la diferencia.

Al guardar, ese total sustituye al calculado. Se conservan el historial, el
movimiento de corrección y la fecha de revisión. Si las cantidades coinciden,
también se guarda la comprobación. Puedes introducir cero.

Tener más unidades de lo esperado puede corresponder a tomas omitidas o compras
sin registrar. El recuento no permite saber por sí solo qué ocurrió. Puedes
corregir el inventario aunque no recuerdes la toma concreta; los descuentos
futuros continúan desde la cantidad contada.

Las compras y **Corregir el total disponible** siguen disponibles. Los cálculos
usan milésimas enteras para mantener cantidades como media pastilla o 2,5 ml.

## Si se agota el stock registrado

El stock calculado se detiene en cero. La agenda identifica las tomas previstas
que no quedaron cubiertas por las existencias registradas. Si quedaba solo una
parte de una dosis, únicamente se descuenta esa parte; omitirla devuelve esa misma
cantidad, no una dosis completa inexistente. Comprueba el stock y registra la
compra o la corrección que corresponda. Una compra posterior no se consume por
tomas que ya se asumieron con el stock agotado.

## Actualizar una instalación existente

La versión 0.3.0 migra al esquema 3 y guarda una copia consistente de la base
anterior en `DATABASE_PATH.pre-v3.sqlite` antes de modificarla. Conserva cuentas,
existencias, recetas, vínculos médicos, historial y sesiones.

El cálculo automático empieza en el momento de actualizar. No descuenta de golpe
las tomas antiguas que quedaron pendientes. En la agenda se identifican como
«Sin descuento previo». Al crear un medicamento, el stock inicial corresponde
a las existencias actuales; tampoco se descuentan los períodos anteriores al alta.
Revisa una vez el inventario con **Comprobar stock** si su cantidad ya estaba
desajustada. La exportación JSON incorpora la procedencia de las tomas, su
cantidad prevista y la fecha de comprobación del stock.
