# Dynamic .env File Mapping in CodeFind

CodeFind now supports dynamic .env file discovery and mapping, allowing for more flexible environment variable management based on your project context and environment settings.

## Overview

The dynamic .env file mapping feature automatically discovers and loads multiple .env files in a specific order, supporting:

- Environment-specific configurations (`.env.development`, `.env.production`, etc.)
- Local overrides (`.env.local`)
- Directory traversal (walking up from current directory)
- Standard search paths (home directory, git root, current directory)

## How It Works

### Discovery Order

When dynamic discovery is enabled (default), CodeFind searches for .env files in this order:

1. **OAuth keys file**: `~/.codefind/oauth-keys.env` (highest priority)
2. **Environment-specific files**: Based on `NODE_ENV`, `ENVIRONMENT`, or `ENV` variables
3. **Common environment variants**: `.env.local`, `.env.development`, `.env.production`, etc.
4. **Standard search paths**: Home directory, git root, current directory
5. **Directory traversal**: Walking up from current directory to find additional .env files

### Environment-Specific Discovery

If you set environment variables like `NODE_ENV=development`, CodeFind will automatically look for:
- `.env.development`
- `.env.development.local`

Common environment names supported:
- `local`
- `development` / `dev`
- `staging`
- `production` / `prod`
- `test`

## Usage

### Command Line Options

```bash
# Enable dynamic discovery (default)
codefind --dynamic-env

# Disable dynamic discovery (use legacy behavior)
codefind --no-dynamic-env

# Show verbose discovery information
codefind --env-discovery-verbose

# Combine with environment variables
NODE_ENV=development codefind --env-discovery-verbose
```

### Environment Variables

You can also control the behavior via environment variables:
```bash
export CODEFIND_DYNAMIC_ENV=true
export CODEFIND_ENV_DISCOVERY_VERBOSE=true
```

## Examples

### Basic Usage

Create different .env files for different environments:

```bash
# Base configuration
echo "API_URL=https://api.example.com" > .env

# Development overrides
echo "API_URL=https://dev-api.example.com" > .env.development
echo "DEBUG=true" >> .env.development

# Local overrides (not committed to git)
echo "API_URL=http://localhost:3000" > .env.local
```

Run with environment-specific loading:
```bash
NODE_ENV=development codefind --env-discovery-verbose
```

### Directory Structure Example

```
project/
├── .env                    # Base configuration
├── .env.local             # Local overrides
├── .env.development       # Development settings
├── .env.production        # Production settings
└── subproject/
    ├── .env               # Subproject-specific settings
    └── src/
        └── main.py
```

When running CodeFind from `project/subproject/src/`, it will discover:
1. Environment-specific files in current and parent directories
2. Standard .env files walking up the directory tree
3. Files in git root and home directory

### Verbose Output Example

```bash
$ NODE_ENV=development codefind --env-discovery-verbose --exit

Dynamic .env file discovery enabled
Discovered .env files in order:
  1. /home/user/project/.env.development (exists)
  2. /home/user/project/.env.local (exists)
  3. /home/user/.env (not found)
  4. /home/user/project/.env (exists)
✓ Loaded: /home/user/project/.env.development
✓ Loaded: /home/user/project/.env.local
✓ Loaded: /home/user/project/.env
Successfully loaded 3 .env file(s)
```

## Configuration

### Legacy Mode

To use the old behavior (only standard search paths), disable dynamic discovery:

```bash
codefind --no-dynamic-env
```

Or set the environment variable:
```bash
export CODEFIND_DYNAMIC_ENV=false
```

### Custom .env File

You can still specify a custom .env file, which will be included in the discovery:

```bash
codefind --env-file custom.env
```

## Best Practices

1. **Use `.env.local` for local overrides** - This file should be in your `.gitignore`
2. **Environment-specific files** - Use `.env.development`, `.env.production`, etc.
3. **Base configuration in `.env`** - Common settings that apply to all environments
4. **Sensitive data** - Store in `~/.codefind/oauth-keys.env` or use AWS profiles

## File Loading Order and Precedence

Files loaded later override variables from files loaded earlier. The loading order is:

1. OAuth keys file (loaded first, can be overridden)
2. Environment-specific files (e.g., `.env.development`)
3. Standard .env files
4. Directory traversal files
5. Command-line specified file (loaded last, highest precedence)

## Migration from Legacy Behavior

The dynamic discovery is enabled by default and is backward compatible. If you prefer the old behavior:

1. Use `--no-dynamic-env` flag
2. Or set `CODEFIND_DYNAMIC_ENV=false`
3. The legacy behavior only loads files from the standard search paths

## Troubleshooting

### Debug Discovery Process

Use `--env-discovery-verbose` to see exactly which files are being discovered and loaded:

```bash
codefind --env-discovery-verbose --exit
```

### Check Environment Variables

After loading, you can verify which variables were set:

```bash
# In your .env files
echo "TEST_VAR=test_value" > .env.development

# Run and check
NODE_ENV=development codefind --env-discovery-verbose -m "What is the value of TEST_VAR?"
```

### Common Issues

1. **Files not found**: Check file paths in verbose output
2. **Variables not loading**: Ensure file format is correct (`KEY=value`)
3. **Precedence issues**: Later files override earlier ones - check loading order

## Integration with AWS and Bedrock

The dynamic .env discovery works seamlessly with AWS credentials and Bedrock configuration:

```bash
# .env.development
AWS_PROFILE=development
BEDROCK_REGION=us-west-2

# .env.production  
AWS_PROFILE=production
BEDROCK_REGION=us-east-1
```

This allows you to easily switch between different AWS environments and regions based on your current development context.
