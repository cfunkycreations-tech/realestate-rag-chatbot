"""Local skill document parsing and explicit slash-invocation parsing."""
import re

INVOCATION = re.compile(r'^/([a-z][a-z0-9-]{0,31})(?:\s+([\s\S]*))?$',re.ASCII)
HEADINGS = {'when to use':'when_to_use','inputs':'inputs','steps':'steps','checks':'checks'}


def parse_invocation(content):
    return INVOCATION.fullmatch(content.strip())


def parse_markdown(text):
    """Parse a deliberately small, readable subset, not arbitrary frontmatter.

    Imported text is data: no links are fetched, no commands are executed and
    no tool permissions are changed. An owner must review and save the draft.
    """
    lines=text.replace('\r\n','\n').replace('\r','\n').split('\n')
    if lines and lines[0].strip()=='---':
        try: end=lines.index('---',1)
        except ValueError as exc: raise ValueError('The frontmatter is not closed.') from exc
        metadata={}
        for line in lines[1:end]:
            match=re.fullmatch(r'(name|description):\s*(.*?)\s*',line)
            if match:
                value=match.group(2)
                if len(value)>1 and value[0]==value[-1] and value[0] in ('\"',"'"): value=value[1:-1]
                metadata[match.group(1)]=value.strip()
        name=metadata.get('name','');description=metadata.get('description','');body='\n'.join(lines[end+1:]).strip()
        if not name or not description or not body: raise ValueError('Frontmatter requires single-line name and description, plus a body.')
        if len(name)>120 or len(description)>4000 or len(body)>6000: raise ValueError('Name, description or body exceed the skill editor limits.')
        # Leave missing fields blank; the owner must supply them before saving.
        return {'name':name,'when_to_use':description,'inputs':'','steps':body,'checks':''}
    name='';section=None;seen=set();parts={key:[] for key in HEADINGS.values()}
    for line in lines:
        if line.startswith('# ') and not name and not section:
            name=line[2:].strip();continue
        if line.startswith('## '):
            key=line[3:].strip().lower()
            if key not in HEADINGS: raise ValueError('Use only When to use, Inputs, Steps, and Checks headings.')
            section=HEADINGS[key]
            if section in seen: raise ValueError('Do not repeat a heading.')
            seen.add(section)
            continue
        if section: parts[section].append(line)
        elif line.strip(): raise ValueError('Start with a title followed by the required headings.')
    fields={key:'\n'.join(value).strip() for key,value in parts.items()}
    if not name or any(not value for value in fields.values()):
        raise ValueError('A title and all four non-empty sections are required.')
    return {'name':name,**fields}
