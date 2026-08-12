# Security Guidelines for API Keys

## Overview
This project requires EC3 and RSMeans API keys to function. It's critical to prevent accidental exposure of these credentials in version control or logs.

## API Key Management

### EC3 API Token
- **Source**: https://buildingtransparency.org
- **Handling**: 
  - Store in `config.ini` (local development only - file is .gitignored)
  - Use environment variable `EC3_API_TOKEN` for CI/CD and production
  - Never commit real tokens to version control

### RSMeans API Key
- **Handling**: 
  - Pass as measure argument (measure.py) - not stored in files
  - Use environment variable `RSMEANS_API_KEY` for CI/CD
  - Never hardcode in source files

## Setup Instructions

### Local Development
1. Copy the template: `cp config.ini.template config.ini`
2. Edit `config.ini` and add your real EC3 API token
3. Never commit `config.ini` to version control (it's in .gitignore)

### CI/CD and Production
Use environment variables instead of config files:

```bash
# Set before running measures
export EC3_API_TOKEN="your_token_here"
export RSMEANS_API_KEY="your_key_here"

# Or inline
EC3_API_TOKEN="token" python apply_measure.py
```

### Using with GitHub Actions
```yaml
env:
  EC3_API_TOKEN: ${{ secrets.EC3_API_TOKEN }}
  RSMEANS_API_KEY: ${{ secrets.RSMEANS_API_KEY }}
```

## .gitignore Configuration
The following sensitive files are already excluded:
- `config.ini` - Local configuration with API tokens
- `.env` - Environment variable files
- `.secrets` - Secret files
- Workflow files with API keys

Verify these entries in `.gitignore`:
```
config.ini
.env
.env.*
.secrets
lib/measures/workflow_with_reporting.osw
```

## Checking for Exposed Credentials

### Before committing:
```bash
# Check for any patterns matching API keys
git diff HEAD -- | grep -i "api_key\|token\|secret"
```

### If credentials are accidentally committed:
1. **Immediately rotate the credentials** - they are now exposed in Git history
2. Create a new commit that removes the sensitive data (use `git filter-branch` or `BFG Repo Cleaner`)
3. Force push to remove from history
4. Notify your team and update all consumers of the exposed credentials

## Code Review Checklist
- [ ] No hardcoded API keys in `.py`, `.rb`, or `.json` files
- [ ] No sensitive data in default values of measure arguments
- [ ] Config files with templates included but not actual tokens
- [ ] Environment variable fallbacks implemented where applicable
- [ ] .gitignore properly covers all config and secrets files

## Environment Variable Fallback Support

The following components support environment variables:

- **apply_measure.py**: Reads `EC3_API_TOKEN` if `config.ini` is not available
- **measure.py**: Accepts API token as measure argument (passed at runtime)
- **Resources**: EC3_lookup.py and call_rsmeans_api.py accept tokens as function parameters

This allows flexibility:
1. Local dev: Use `config.ini`
2. CI/CD: Use environment variables
3. Docker/containers: Use mounted secrets or env vars

## References
- [OWASP: Secrets Management](https://owasp.org/www-community/Secrets_Management)
- [GitHub: Removing sensitive data from history](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
- [EC3 BuildingTransparency API](https://buildingtransparency.org)
