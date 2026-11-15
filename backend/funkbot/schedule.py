"""Bounded five-field cron evaluation in local wall time.

A repeated fall-back minute fires once (its first occurrence); missing spring
minutes are skipped. Weekday uses cron's Sunday=0 (7 is also accepted).
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _field(raw, low, high):
    result=set()
    for part in raw.split(','):
        bits=part.split('/')
        if len(bits)>2 or not bits[0] or (len(bits)==2 and (not bits[1].isdigit() or not 1<=int(bits[1])<=high-low+1)):
            raise ValueError('Invalid cron field.')
        step=int(bits[1]) if len(bits)==2 else 1
        base=bits[0]
        if base=='*': start,end=low,high
        elif '-' in base:
            bounds=base.split('-')
            if len(bounds)!=2 or not all(x.isdigit() for x in bounds): raise ValueError('Invalid cron range.')
            start,end=map(int,bounds)
        elif base.isdigit() and len(bits)==1: start=end=int(base)
        else: raise ValueError('Invalid cron field.')
        if not low<=start<=end<=high: raise ValueError('Cron value out of range.')
        result.update(range(start,end+1,step))
    return result


def parse(expression, zone):
    fields=expression.split()
    if len(fields)!=5 or len(expression)>120: raise ValueError('Cron needs five fields: minute hour day month weekday.')
    try: tz=ZoneInfo(zone)
    except (ZoneInfoNotFoundError,ValueError): raise ValueError('Enter a valid IANA timezone.') from None
    minute=_field(fields[0],0,59);hour=_field(fields[1],0,23);day=_field(fields[2],1,31);month=_field(fields[3],1,12);weekday=_field(fields[4],0,7)
    if 7 in weekday: weekday.add(0);weekday.discard(7)
    return tz,sorted(minute),sorted(hour),day,month,weekday,fields[2]=='*',fields[4]=='*'


def next_occurrence(expression, zone, after):
    tz,minutes,hours,days,months,weekdays,anyday,anyweekday=parse(expression,zone)
    start=datetime.fromtimestamp(after,timezone.utc).astimezone(tz).date()
    for i in range(366*8):
        day=start+timedelta(days=i)
        dom=day.day in days;dow=(day.weekday()+1)%7 in weekdays
        if day.month not in months or not (dow if anyday else dom if anyweekday else dom or dow): continue
        for hour in hours:
            for minute in minutes:
                local=datetime(day.year,day.month,day.day,hour,minute,tzinfo=tz,fold=0)
                stamp=local.timestamp()
                back=datetime.fromtimestamp(stamp,tz)
                if (back.year,back.month,back.day,back.hour,back.minute)!=(day.year,day.month,day.day,hour,minute): continue
                if stamp>after: return stamp
    raise ValueError('Cron has no occurrence in the next eight years.')
