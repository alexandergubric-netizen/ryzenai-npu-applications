"""Phase 3 tool contracts shared by the model, approval broker and file worker."""
import re
S={'type':'string'}
I={'type':'integer','minimum':1}
A={'type':'array','items':S}
ROWS={'type':'array','items':{'type':'array','items':{}}}
CAT={
 'pdf_read':('read','Read text from selected PDF pages.',{'path':S,'pages':S}),
 'pdf_search':('read','Find matching passages in a PDF.',{'path':S,'query':S}),
 'pdf_extract_pages':('write','Save selected PDF pages as a new PDF.',{'path':S,'pages':S,'out':S}),
 'pdf_merge':('write','Merge PDFs in order into a new PDF.',{'paths':A,'out':S}),
 'pdf_render_page':('read','Render one PDF page for preview.',{'path':S,'page':I}),
 'doc_create':('write','Create an editable Markdown document.',{'title':S,'markdown':S}),
 'doc_edit':('write','Replace a named Markdown section or the entire document.',{'id':S,'section':S,'markdown':S}),
 'doc_export':('write','Export an editable document to DOCX or PDF.',{'id':S,'format':S,'out':S}),
 'table_create':('write','Create an editable table with typed cells.',{'id':S,'columns':A,'rows':ROWS}),
 'table_update':('write','Apply edits to table cells by row and column.',{'id':S,'ops':{'type':'array','items':{'type':'object'}}}),
 'table_export':('write','Export an editable table to CSV or XLSX.',{'id':S,'format':S,'out':S}),
 'list_targets':('read','List supported conversion targets for a file.',{'path':S}),
 'convert_file':('write','Convert a supported file to a new output.',{'path':S,'target':S,'out':S}),
}
EXTS={'.pdf','.txt','.md','.docx','.csv','.tsv','.xlsx'}
def filename(value):
    if not isinstance(value,str) or not re.fullmatch(r'[\w][\w .()-]{0,92}',value) or value.endswith((' ','.')) or '..' in value:
        raise ValueError('Use a simple filename inside this workspace.')
    if value.split('.')[0].rstrip().upper() in {'CON','PRN','AUX','NUL',*(f'{p}{i}' for p in ('COM','LPT') for i in '123456789¹²³')}:
        raise ValueError('Reserved filename.')
    return value
def validate(name,args):
    if name not in CAT or not isinstance(args,dict):raise ValueError('Unknown file operation.')
    props=CAT[name][2]
    if set(args)!=set(props):raise ValueError('Missing or unexpected file arguments.')
    for key,definition in props.items():
        v=args[key];kind=definition['type']
        if kind=='string' and (not isinstance(v,str) or len(v)>(14000 if key=='markdown' else 200)):raise ValueError('Invalid '+key)
        if kind=='integer' and (type(v) is not int or v<1):raise ValueError('Invalid page.')
        if kind=='array' and (not isinstance(v,list) or len(v)>500):raise ValueError('Invalid '+key)
    for key in ('path','out','id','title'):
        if key in args:filename(args[key])
    if 'paths' in args:
        if not 2<=len(args['paths'])<=12:raise ValueError('Choose 2–12 PDFs.')
        for p in args['paths']:filename(p)
def target(name,a):
    if name=='doc_create':return filename(a['title']+'.tsdoc.json')
    if name=='table_create':return filename(a['id']+'.tstable.json')
    if name in ('doc_edit','table_update'):return a['id']
    return a.get('out')
def shortlist(prompt):
    text=prompt.lower()
    groups={'pdf':r'pdf|pages?', 'doc':r'document|docx|markdown|section','table':r'table|csv|spreadsheet|xlsx|cells?', 'convert':r'convert|targets?|conversion'}
    verbs={'read':'read|summari|text','search':'search|find','extract_pages':'extract|split','merge':'merge|combine','render_page':'render|preview|image','create':'create|make|new','edit':'edit|replace','export':'export|save as','update':'update|change|edit'}
    scored=[]
    for name,(risk,description,props) in CAT.items():
        group,_,verb=name.partition('_')
        family='convert' if name=='list_targets' else group
        score=100 if name in text else 0
        if re.search(groups[family],text):score+=4
        if score and re.search(verbs.get(verb,verb),text):score+=6
        if name=='convert_file' and 'convert' in text:score+=8
        if name=='list_targets' and 'target' in text:score+=8
        if score:scored.append((-score,name))
    return [{'name':n,'risk':CAT[n][0],'description':CAT[n][1],'parameters':{'type':'object','properties':CAT[n][2],'required':list(CAT[n][2]),'additionalProperties':False}} for _,n in sorted(scored)[:6]]

