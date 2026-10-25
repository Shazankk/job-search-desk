"""Connection diagnostics; no secrets are returned or stored in settings."""
from .core import secret
from .resume import ai_order


def connection_status(cfg):
    provider = cfg.get('provider','none')
    if provider == 'none':
        return False,'AI is off. Matching and document preparation use local rules.'
    if not cfg.get('model','').strip():
        return False,'Enter a model ID from your provider.'
    if not cfg.get('share_resume_facts'):
        return False,'Allow sharing factual paragraphs to enable AI-assisted ordering.'
    if int(cfg.get('max_calls_per_run',3))==0:
        return False,'AI is configured but its call limit is zero. Increase it to use AI during preparation.'
    name = 'OPENAI_API_KEY' if provider == 'openai' else 'ANTHROPIC_API_KEY'
    if not secret(name):
        return False,'API key missing. Use CREDENTIALS.command to store it in the login Keychain.'
    return True,f'{provider.title()} is configured. Use Test AI connection to check API access; preparation uses it when a resume has reorderable paragraphs.'


def test_connection(cfg):
    ready,message = connection_status(cfg)
    if not ready:
        return False,message
    probe = dict(cfg)
    # Explicit user-triggered small API call, using synthetic data rather than their resume.
    result = ai_order([0,1],['Synthetic fact: experience with Python.','Synthetic fact: experience with payroll.'],
                      {'title':'Python developer','description':'Synthetic connection test: Python experience.'},probe)
    if result is None:
        return False,probe.get('_last_error','No usable response; local preparation remains available.')
    return True,'Connection succeeded. AI returned a valid fact order. This test used synthetic text, not your resume.'
