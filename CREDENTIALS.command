#!/bin/zsh
set -euo pipefail
print 'Store a secret in your login Keychain. Do not paste it into configuration files.'
print '1: OpenAI API key   2: Claude API key   3: SMTP password/app password   4: IMAP password/app password   5: Adzuna app ID   6: Adzuna app key'
read 'choice?Choose 1–6: '
case "$choice" in
  1) credential=OPENAI_API_KEY ;;
  2) credential=ANTHROPIC_API_KEY ;;
  3) credential=SMTP_PASSWORD ;;
  4) credential=IMAP_PASSWORD ;;
  5) credential=ADZUNA_APP_ID ;;
  6) credential=ADZUNA_APP_KEY ;;
  *) print 'No changes made.'; exit 1 ;;
esac
# Omitting the password argument makes security prompt for it; the secret is not in process arguments.
/usr/bin/security add-generic-password -U -a "$USER" -s "local.job-search-desk.$credential" -w
print 'Saved. The app will read this secret from Keychain when needed.'
read '?Press Return to close.'
