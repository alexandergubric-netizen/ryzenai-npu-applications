"""Single-call stdio worker in Tsubasa's private file runtime."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.file_catalog import CAT, validate
from tools.file_conversion import targets,convert
from tools.office_files import document_operation,table_operation
from tools.pdf_files import perform

def call(request):
    name,args=request["name"],request["args"]
    validate(name,args)
    inputs=[Path(p) for p in request["inputs"]]
    source=inputs[0] if inputs else None
    out=Path(request["output"]) if request["output"] else None
    if name.startswith("pdf_"):
        return perform(name,args,inputs,out)
    if name.startswith("doc_"):
        document_operation(name,args,source,out)
    elif name.startswith("table_"):
        table_operation(name,args,source,out)
    elif name=="list_targets":
        return targets(source)
    elif name=="convert_file":
        convert(source,args["target"],out)
    return {"saved":True}

if __name__=="__main__":
    req=json.load(sys.stdin.buffer)
    try:
        if req.get("jsonrpc")!="2.0":
            raise ValueError("Invalid RPC version.")
        if req.get("method")=="tools/list":
            response={"result":[{"name":name,"description":description,"inputSchema":{
                "type":"object","properties":props,"required":list(props),"additionalProperties":False}}
                for name,(_,description,props) in CAT.items()]}
        elif req.get("method")=="kb/pages":
            from contextlib import ExitStack
            from tools.pdf_files import open_pdf
            with ExitStack() as stack:
                doc=open_pdf(stack,Path(req["params"]["path"]))
                pages=[]
                total=0
                for number,page in enumerate(doc,1):
                    text=page.get_text()
                    total+=len(text)
                    if total>215000:
                        raise ValueError("PDF exceeds index limits.")
                    pages.append({"page":number,"text":text})
                response={"result":pages}
        elif req.get("method")=="tools/call":
            response={"result":call(req["params"])}
        else:
            raise ValueError("Unknown RPC method.")
    except Exception:
        response={"error":"Could not process this file. Check the format, ranges and field values."}
    print(json.dumps({"jsonrpc":"2.0","id":req["id"],**response}))

