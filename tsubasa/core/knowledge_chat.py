"""One native KB operation per opted-in message. Citations come from indexed rows."""
import json
import time
from core.tool_loop import assemble
from core.knowledge import area_name

SCHEMAS={
    "kb_search":("Retrieve supporting source passages in the selected knowledge area.",{"area":{"type":"string"},"query":{"type":"string"},"k":{"type":"integer","minimum":1,"maximum":8}}),
    "kb_add":("Propose indexing workspace files. The user must confirm after chat finishes.",{"area":{"type":"string"},"paths":{"type":"array","items":{"type":"string"}}})
}

def stream(app,model,messages,workspace,area,emit,cancelled,options):
    area=area_name(area)
    schemas=[{"type":"function","function":{"name":name,"description":desc,"parameters":{
        "type":"object","properties":props,"required":list(props),"additionalProperties":False}}}
        for name,(desc,props) in SCHEMAS.items()]
    history=[dict(m) for m in messages]
    history[0]["content"]+=" Use one knowledge tool for this message. The selected area is "+area+"."
    parts={}
    for kind,value in app.client.stream(model,history,tools=schemas,cancelled=cancelled,max_tokens=512,**options):
        if cancelled.is_set():return
        if kind=="tool_delta":assemble(parts,value)
        elif kind=="usage":yield kind,value
    if cancelled.is_set():return
    if not parts:
        name,args="kb_search",{"area":area,"query":messages[-1]["content"],"k":4}
    else:
        if set(parts)!={0}:raise ValueError("Use one knowledge operation per message.")
        name=parts[0]["name"];args=json.loads(parts[0]["arguments"])
        if name not in SCHEMAS or not isinstance(args,dict) or set(args)!=set(SCHEMAS[name][1]) or area_name(args["area"])!=area:
            raise ValueError("Invalid knowledge request or area.")
    start=time.monotonic()
    if name=="kb_add":
        proposal=app.knowledge.prepare(workspace,name,area,args["paths"])
        emit("knowledge_proposal",{**proposal,"workspace":workspace})
        result="Indexing proposed. Review the listed files after this response finishes."
        decision="proposed"
    else:
        hits=app.knowledge.index.search(workspace,area,args["query"],args["k"])
        result=format_hits(hits)
        decision="read"
    app.tools.audit(name,args,decision,start,result)
    yield "text",result

def format_hits(hits):
    if not hits:return "No supporting passage found in this area."
    return "\n\n".join("["+str(h["citation"])+"] "+h["source"]+
        (" (page "+str(h["page"])+")" if h["page"] else "")+"\n"+h["excerpt"] for h in hits)

