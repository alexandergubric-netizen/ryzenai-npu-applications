"""Small native tool registry for the Phase 2 practice connector."""
import re

TOOLS = {
    'read_sample': ('Read and return the text of sample.txt.', 'read', {}),
    'count_words': ('Count the words in sample.txt and return the total.', 'read', {}),
    'create_draft': ('Create draft.txt with the supplied text. Never overwrite an existing file.', 'write',
                     {'text': {'type':'string','maxLength':1000}}),
}

def metadata(name):
    description, risk, properties = TOOLS[name]
    return {'name':name, 'description':description, 'risk':risk,
            'parameters':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}

def shortlist(prompt):
    # All three are related and fit the schema budget. Plain chat sends no tools.
    if not re.search(r'\b(sample|draft|file|words?|note|read_sample|count_words|create_draft)\b', prompt, re.I):
        return []
    return [metadata(name) for name in TOOLS][:6]

def native(items):
    return [{'type':'function','function':{k:v for k,v in item.items() if k!='risk'}} for item in items]

def validate(name, args):
    if name not in TOOLS or not isinstance(args,dict) or set(args)!=set(TOOLS[name][2]):
        raise ValueError('Unknown tool or invalid arguments.')
    if name=='create_draft' and (not isinstance(args['text'],str) or not args['text'].strip() or len(args['text'])>1000):
        raise ValueError('Draft text must be 1–1,000 characters.')

