"""Bounded PDF text extraction in a separate, resource-limited process."""
import io
import sys
try:
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(5,5))
    resource.setrlimit(resource.RLIMIT_FSIZE,(1024*1024,1024*1024))
except (ImportError,ValueError,OSError):
    # Fail closed on platforms where an untrusted PDF cannot be bounded.
    sys.exit(2)
try:
    from pypdf import PdfReader
    pdf=PdfReader(io.BytesIO(sys.stdin.buffer.read(2*1024*1024+1)),strict=True)
    if pdf.is_encrypted or len(pdf.pages)>20: sys.exit(2)
    parts=[];remaining=40000
    for page in pdf.pages:
        text=page.extract_text() or ''
        parts.append(text[:remaining]);remaining-=len(parts[-1])
        if remaining<=0: break
    result='\n'.join(parts).strip()
    if not result: sys.exit(2)
    sys.stdout.write(result[:40000])
except Exception:
    sys.exit(2)
