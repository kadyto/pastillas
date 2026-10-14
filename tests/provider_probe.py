"""Comprobación pública diagnóstica, separada de las pruebas deterministas."""
import json
import sys
import urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import medicine_info as info

result={}
try:
    search=info.fetch_json('medicamentos?nombre=omacor')
    matches=info.rows(search)
    result['cima_search']=[dict(nregistro=m['nregistro'],name=m['nombre']) for m in matches]
    if matches:
        medicine=info.fetch_json('medicamento?nregistro='+str(matches[0]['nregistro']))
        result['cima_catalog']=dict(nregistro=medicine.get('nregistro'),presentations=medicine.get('presentaciones'),
                                    docs=medicine.get('docs'),notes=medicine.get('notas'))
        if medicine.get('notas'):
            notes=info.fetch_json('notas/'+str(medicine['nregistro']))
            result['notes_shape']=[list(n) for n in info.rows(notes)]
        if medicine.get('presentaciones'):
            supply=info.fetch_json('psuministro/'+medicine['presentaciones'][0]['cn'])
            result['supply_shape']=str(type(supply).__name__)
            loaded=info.load_information(dict(nregistro=medicine['nregistro'],cn=medicine['presentaciones'][0]['cn'],
                                            cima_name=medicine['nombre'],presentation_name=medicine['presentaciones'][0]['nombre']))
            result['cima_notice_loader']=dict(notices=len(loaded['notices']),documents=len(loaded['documents']))
        for doc in medicine.get('docs',[]):
            if doc.get('tipo') in (1,2) and doc.get('secc'):
                sections=info.fetch_json('docSegmentado/contenido/'+str(doc['tipo'])+'?nregistro='+str(medicine['nregistro']))
                result['document_'+str(doc['tipo'])]=dict(sections=len(info.rows(sections)),first_keys=list(info.rows(sections)[0]) if info.rows(sections) else [])
except Exception as error:
    result['cima_error']=type(error).__name__+': '+str(error)
    cause=error.__cause__
    result['cima_failure_type']=type(cause).__name__ if cause else None
    result['cima_http_status']=getattr(cause,'code',None)

# Comprueba registros de autorización nacional y centralizada por separado.
for query in ('pravafenix',):
    diagnostic={}
    try:
        matches=info.rows(info.fetch_json('medicamentos?nombre='+query))
        diagnostic['matches']=len(matches)
        for match in matches[:1]:
            number=str(match['nregistro'])
            medicine=info.fetch_json('medicamento?nregistro='+__import__('urllib.parse',fromlist=['quote']).quote(number,safe=''))
            diagnostic['registry_format']='centralised' if '/' in number else 'national'
            diagnostic['notes_flag']=medicine.get('notas')
            for presentation in medicine.get('presentaciones',[])[:1]:
                item=dict(nregistro=number,cn=str(presentation['cn']),cima_name=medicine['nombre'],presentation_name=presentation['nombre'])
                diagnostic['supply_flag']=presentation.get('psum')
                loaded=info.load_information(item)
                diagnostic['information_loaded']=True
                diagnostic['documents']=len(loaded['documents'])
                diagnostic['notices']=len(loaded['notices'])
    except Exception as error:
        diagnostic['error']=type(error).__name__+': '+str(error)
        cause=error.__cause__
        diagnostic['failure_type']=type(cause).__name__ if cause else None
        diagnostic['http_status']=getattr(cause,'code',None)
    result['centralised_registration']=diagnostic
for label,url in [('equivalents_de','https://www.vademecum.es/espana/equivalencias/27631/omacor-1000-mg-capsulas-blandas'),
                  ('equivalents_fr','https://www.vademecum.es/espana/equivalencias/27631/omacor-1000-mg-capsulas-blandas?code=fr')]:
    try:
        data=info.parse_equivalents(info.fetch_vademecum(url))
        result[label]=dict(country=data['country'],countries=len(data['countries']),results=len(data['results']),
                           sample=data['results'][:1])
    except Exception as error:
        result[label]=dict(error=type(error).__name__,detail=str(error))
print(json.dumps(result,ensure_ascii=False,indent=2))
Path('test-results').mkdir(exist_ok=True)
Path('test-results/provider-probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
