"""Comprobación pública diagnóstica, separada de las pruebas deterministas."""
import json
import sys
import urllib.request
import re
from html.parser import HTMLParser
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import medicine_info as info

result={}
class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[];self.text=[];self.current=None;self.ignore=0
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if tag in ('script','style'):self.ignore+=1
        if tag=='a':self.current=[values.get('href',''),'']
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.ignore=max(0,self.ignore-1)
        if tag=='a' and self.current:self.links.append(self.current);self.current=None
    def handle_data(self,data):
        if not self.ignore:
            if self.current:self.current[1]+=data
            if data.strip():self.text.append(data.strip())
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
        for doc in medicine.get('docs',[]):
            if doc.get('tipo') in (1,2) and doc.get('secc'):
                sections=info.fetch_json('docSegmentado/contenido/'+str(doc['tipo'])+'?nregistro='+str(medicine['nregistro']))
                result['document_'+str(doc['tipo'])]=dict(sections=len(info.rows(sections)),first_keys=list(info.rows(sections)[0]) if info.rows(sections) else [])
except Exception as error:
    result['cima_error']=type(error).__name__+': '+str(error)
for label,url in [('vademecum','https://www.vademecum.es/espana/medicamento/27631/omacor-1000-mg-capsulas-blandas'),
                  ('equivalents','https://www.vademecum.es/espana/equivalencias/27631/omacor-1000-mg-capsulas-blandas')]:
    try:
        with urllib.request.build_opener(info.NoRedirect()).open(urllib.request.Request(url,headers={'User-Agent':'Pastillas/0.2 (+https://github.com/kadyto/pastillas)'}),timeout=8) as response:
            raw=response.read(2*1024*1024).decode('utf-8',errors='replace');p=Page();p.feed(raw)
            result[label]=dict(status=response.status,content_type=response.headers.get('Content-Type'),
                               selects=re.findall(r'<select\b[\s\S]*?</select>',raw,re.I),
                               country_scripts=[raw[max(0,m.start()-200):m.end()+700] for m in list(re.finditer(r'onchange|function[^\n]*[Pp]ais|\?pais|idpais',raw))[:8]],
                               medicine_links=sum('/medicamento/' in u for u,t in p.links))
            Path('test-results/'+label+'.html').write_text(raw)
    except Exception as error:
        result[label]=dict(error=type(error).__name__,detail=str(error))
print(json.dumps(result,ensure_ascii=False,indent=2))
Path('test-results').mkdir(exist_ok=True)
Path('test-results/provider-probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
