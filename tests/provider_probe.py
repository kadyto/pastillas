"""Comprobación pública diagnóstica, separada de las pruebas deterministas."""
import json
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote
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
    reason=getattr(cause,'reason',None)
    result['cima_reason_type']=type(reason).__name__ if reason is not None else None
    result['cima_ssl_verify_message']=getattr(reason,'verify_message',None)
    result['cima_reason_errno']=getattr(reason,'errno',None)
    if isinstance(reason, TimeoutError) or isinstance(cause, TimeoutError):
        # Distingue una fuente lenta del límite habitual de ocho segundos.
        started=time.monotonic()
        try:
            request=urllib.request.Request(info.BASE+'medicamentos?nombre=omacor',headers={
                'Accept':'application/json','User-Agent':'Pastillas (+https://github.com/kadyto/pastillas)'})
            with urllib.request.build_opener(info.NoRedirect()).open(request,timeout=25) as response:
                data=json.loads(response.read(info.MAX_RESPONSE+1))
                result['cima_extended_wait']=dict(status=response.status,matches=len(info.rows(data)))
        except (OSError,ValueError) as extended:
            underlying=extended.reason if isinstance(extended,urllib.error.URLError) else extended
            result['cima_extended_wait']=dict(error=info.connection_error(extended),reason_type=type(underlying).__name__)
        result['cima_extended_wait']['elapsed_seconds']=round(time.monotonic()-started,1)

# Comprueba registros de autorización nacional y centralizada por separado.
for query in ('pravafenix',):
    diagnostic={}
    try:
        matches=info.rows(info.fetch_json('medicamentos?nombre='+query))
        diagnostic['matches']=len(matches)
        for match in matches[:1]:
            number=str(match['nregistro'])
            medicine=info.fetch_json('medicamento?nregistro='+quote(number,safe=''))
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
        reason=getattr(cause,'reason',None)
        diagnostic['reason_type']=type(reason).__name__ if reason is not None else None
        diagnostic['ssl_verify_message']=getattr(reason,'verify_message',None)
        diagnostic['reason_errno']=getattr(reason,'errno',None)
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
