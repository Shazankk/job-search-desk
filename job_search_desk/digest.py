from datetime import datetime
from email.message import EmailMessage
import smtplib
import ssl
from .core import secret, now, event


def send_digest(con, cfg, root):
    e = cfg['email']
    if not e.get('enabled'):
        return 'disabled'
    day = datetime.now().date().isoformat()
    previous = con.execute('SELECT state FROM digests WHERE day=?',(day,)).fetchone()
    if previous:
        return previous['state']  # no blind retries after an ambiguous SMTP result
    jobs = con.execute('''SELECT * FROM jobs WHERE score>=? AND needs_review=0 AND duplicate_of IS NULL
      AND artifact IS NOT NULL AND status NOT IN ('dismissed','applied','closed')
      AND id NOT IN (SELECT job_id FROM digest_jobs) ORDER BY score DESC LIMIT 20''',
      (cfg['min_score'],)).fetchall()
    leads=con.execute('''SELECT * FROM jobs WHERE needs_review=1 AND duplicate_of IS NULL
      AND status NOT IN ('dismissed','applied','closed') AND id NOT IN (SELECT job_id FROM digest_leads)
      ORDER BY first_seen DESC LIMIT 30''').fetchall()
    if not e.get('host') or not e.get('to') or not e.get('from') or not e.get('username'):
        event(con,'email','not configured')
        return 'not configured'
    password = secret('SMTP_PASSWORD')
    if not password:
        event(con,'email','SMTP_PASSWORD missing')
        return 'missing credential'
    if e.get('include_job_details'):
        body = '\n\n'.join(f"{j['title']} — {j['company']} | {j['score']}/10\n{j['apply_url'] or j['url']}\nSource: {j['source_url'] or j['url']}\nPacket: {j['artifact']}" for j in jobs)
    else:
        body = 'Open the local dashboard to review the prepared jobs. Job details are omitted by your privacy settings.'
    if e.get('include_job_details') and leads:
        body+='\n\nNew alert leads — full job descriptions needed (no full fit score):\n'+'\n\n'.join(f"{j['title']} — {j['source']}\n{j['apply_url'] or j['url']}" for j in leads)
    errors = con.execute("SELECT COUNT(*) FROM events WHERE kind='source_error' AND substr(at,1,10)=?",(day,)).fetchone()[0]
    body = (f'{len(jobs)} new prepared jobs; {len(leads)} new alert/search leads needing a full description. Source failures recorded today (UTC): {errors}.\n\n'+body+
            f'\n\nLocal folder on this Mac: {root / "artifacts"}\nNo applications or outreach were sent.')
    msg = EmailMessage()
    msg['Subject'] = 'Daily job-search digest — '+day
    msg['From'], msg['To'] = e['from'], e['to']
    msg.set_content(body)
    # Reserve before sending: SMTP may accept a message even if the final acknowledgement is lost.
    con.execute('INSERT INTO digests VALUES(?,?,?)',(day,'sending',now()))
    con.commit()
    try:
        context = ssl.create_default_context()
        if e['security'] == 'ssl':
            client = smtplib.SMTP_SSL(e['host'],int(e['port']),timeout=30,context=context)
        else:
            client = smtplib.SMTP(e['host'],int(e['port']),timeout=30)
            client.starttls(context=context)
        with client as connection:
            connection.login(e['username'],password)
            refused = connection.send_message(msg)
            if refused:
                raise RuntimeError('Recipient refused')
        con.execute('UPDATE digests SET state=? WHERE day=?',('sent',day))
        con.executemany('INSERT OR IGNORE INTO digest_jobs VALUES(?,?)',[(j['id'],now()) for j in jobs])
        con.executemany('INSERT OR IGNORE INTO digest_leads VALUES(?,?)',[(j['id'],now()) for j in leads])
        con.commit()
        event(con,'email','digest sent')
        return 'sent'
    except Exception:
        con.execute('UPDATE digests SET state=? WHERE day=?',('uncertain_or_failed',day))
        con.commit()
        event(con,'email','delivery failed or uncertain; review mailbox and logs, no automatic retry')
        return 'uncertain_or_failed'
