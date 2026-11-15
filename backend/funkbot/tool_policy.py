"""Web fetch host policy, defaulting to no allowed external sites."""
import ipaddress
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .tools import canonical_host, public_address


class WebPolicy(BaseModel):
    model_config=ConfigDict(extra='forbid')
    allow: list[str] = Field(default_factory=list,max_length=100)
    deny: list[str] = Field(default_factory=list,max_length=100)

    @field_validator('allow','deny')
    @classmethod
    def validate_hosts(cls, values):
        cleaned=[]
        for value in values:
            if len(value)>254 or not value or value != value.strip() or '*' in value:
                raise ValueError('Enter exact hostnames or .example.com suffixes; no wildcards, paths or ports.')
            suffix=value.startswith('.')
            host=canonical_host(value[1:] if suffix else value)
            try:
                ip=ipaddress.ip_address(host)
            except ValueError:
                labels=host.split('.')
                if len(labels)<2 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in labels):
                    raise ValueError('Enter valid hostnames without paths or ports.')
            else:
                if suffix or not public_address(ip):
                    raise ValueError('Private and non-public IP addresses cannot be listed.')
                host=str(ip)
            entry=('.' if suffix else '')+host
            if entry not in cleaned: cleaned.append(entry)
        return cleaned
