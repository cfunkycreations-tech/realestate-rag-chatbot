"""OpenAI-compatible tool declaration and streamed-call parsing.

This module only parses data. It does not execute tools or authorize writes.
"""
import json
import re
from .tools import REGISTRY, ToolError
from pydantic import ValidationError

MAX_CALLS=6
MAX_ARGUMENT_BYTES=20_000


def declarations():
    return [{'type':'function','function':{'name':spec.name,'description':spec.description,'parameters':spec.args.model_json_schema()}} for spec in REGISTRY.values()]


class CallAccumulator:
    def __init__(self): self.calls={}

    def feed(self, delta):
        values=delta.get('tool_calls',[])
        if not isinstance(values,list): raise ToolError('Invalid streamed tool calls.')
        for item in values:
            if not isinstance(item,dict): raise ToolError('Invalid streamed tool call.')
            index=item.get('index')
            if type(index) is not int or not 0<=index<MAX_CALLS: raise ToolError('Too many or invalid tool calls.')
            call=self.calls.setdefault(index,{'id':'','name':'','arguments':''})
            identifier=item.get('id')
            if identifier is not None:
                if not isinstance(identifier,str) or len(identifier)>128 or (call['id'] and call['id']!=identifier): raise ToolError('Invalid tool call ID.')
                call['id']=identifier
            function=item.get('function',{})
            if not isinstance(function,dict): raise ToolError('Invalid tool function.')
            for key in ('name','arguments'):
                chunk=function.get(key)
                if chunk is not None:
                    if not isinstance(chunk,str): raise ToolError('Invalid tool function fragment.')
                    call[key]+=chunk
                    if len(call[key].encode('utf-8'))>(128 if key=='name' else MAX_ARGUMENT_BYTES): raise ToolError('Tool call is too large.')

    def finalize(self):
        result=[];seen=set()
        for index in sorted(self.calls):
            call=self.calls[index];identifier=call['id'];name=call['name']
            if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',identifier) or identifier in seen: raise ToolError('Invalid or duplicate tool call ID.')
            if name not in REGISTRY: raise ToolError('Unknown tool.')
            try:
                args=json.loads(call['arguments'])
                parsed=REGISTRY[name].args.model_validate(args).model_dump()
            except (json.JSONDecodeError,ValidationError,TypeError) as exc:
                raise ToolError('Invalid tool arguments.') from exc
            seen.add(identifier);result.append({'id':identifier,'name':name,'arguments':parsed})
        return result
