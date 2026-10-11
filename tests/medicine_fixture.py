"""Respuestas sintéticas de CIMA: no representan medicamentos ni avisos reales."""
from copy import deepcopy

MEDICINE = dict(nregistro='99999', nombre='MEDICAMENTO DE PRUEBA 1000 MG CAPSULAS',
                labtitular='Laboratorio de pruebas', dosis='1000 mg',
                formaFarmaceuticaSimplificada=dict(nombre='Cápsulas'), notas=True, psum=True,
                presentaciones=[dict(cn='999001', nombre='Envase de prueba, 28 cápsulas', comerc=True, psum=True),
                                dict(cn='999002', nombre='Envase de prueba, 100 cápsulas', comerc=True, psum=False)],
                docs=[dict(tipo=1,secc=True,url='https://cima.aemps.es/cima/pdfs/ft/99999/FT_99999.pdf'),
                      dict(tipo=2,secc=True,url='https://cima.aemps.es/cima/pdfs/p/99999/P_99999.pdf')])
NOTE = dict(tipo=1, num='PRUEBA/2026/1', ref='Nota sintética para pruebas', asunto='AVISO SINTÉTICO: comprobar la presentación',
            fecha=1791712800000, url='https://www.aemps.gob.es/nota-de-prueba')
SUPPLY = dict(cn='999001', nombre='Envase de prueba, 28 cápsulas', fini=1791712800000, ffin=1794315600000,
              observ='DESABASTECIMIENTO SINTÉTICO para pruebas', activo=True)
DOCUMENT = [dict(seccion='1',titulo='Documento sintético para pruebas',orden=1,
                 contenido='<p>Contenido de prueba del documento oficial.</p><table><tr><th>Campo</th><td>Valor</td></tr></table><script>window.injected=true</script>'),
            dict(seccion='2',titulo='Otra sección',orden=2,contenido='<p>Más contenido de prueba.</p>')]

def fetch(endpoint):
    if endpoint.startswith('medicamentos?'):
        return dict(pagina=1,tamanioPagina=25,totalFilas=1,resultados=[deepcopy(MEDICINE)])
    if endpoint.startswith('medicamento?'):
        return deepcopy(MEDICINE)
    if endpoint.startswith('notas/'):
        return [deepcopy(NOTE)]
    if endpoint.startswith('psuministro/'):
        return [deepcopy(SUPPLY)] if endpoint.endswith('999001') else []
    if endpoint.startswith('docSegmentado/'):
        return deepcopy(DOCUMENT)
    raise AssertionError('Endpoint no previsto: '+endpoint)
