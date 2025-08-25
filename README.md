<h1 align="center">
CodeFind - AI Pair Programming with AWS Bedrock & Knowledge Graphs
</h1>


<p align="center">
CodeFind lets you pair program with AWS Bedrock LLMs enhanced by knowledge graph retrieval to start a new project or build on your existing codebase.
</p>

## Getting Started

### Authentication

```bash
# AWS SSO authentication
aws-sso exec
	eng-ai-sandbox

# Verify AWS credentials
env | grep -i aws
```

### Build and Install

```bash
# Set global Python to 3.12 (use pyenv if needed)
pyenv global 3.12

# Clean previous builds (in aider directory)
rm -rf dist/ build/ *.egg-info/

# Upgrade build tools (if needed)
pip install --upgrade pip build wheel

# Build the package
python -m build

# Install the built package
pip install dist/codefind-0.86.2.dev3+g6e20f7a57.d20250821-py3-none-any.whl

# Or install from specific path
cd <path to aider> && pip install dist/codefind-0.86.2.dev3+g6e20f7a57.d20250821-py3-none-any.whl
```

### Environment Configuration

In the repository where you want to use CodeFind, set up the following environment variables (via .env file or export):

```bash
# AWS Credentials (for development/testing only)
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-key
AWS_DEFAULT_REGION=us-west-2

# Optional: AWS Session Token (if using temporary credentials)
AWS_SESSION_TOKEN=your-token

# AWS Bedrock Knowledge Base
BEDROCK_KNOWLEDGE_BASE_ID=GOZGOG7JRZ
BEDROCK_REGION=us-west-2
BEDROCK_SEARCH_TYPE=SEMANTIC # SEMANTIC or HYBRID

# Bedrock Streaming Control
BEDROCK_DISABLE_STREAMING=false

# CodeFind Settings
CODEFIND_MODEL=bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0
CODEFIND_AUTO_COMMITS=false
CODEFIND_VERBOSE=false

# Disable version checking
CODEFIND_CHECK_UPDATE=false
```

### Usage

```bash
# Change directory into your codebase
cd /to/your/project

# Use Claude 3.5 Sonnet via AWS Bedrock
codefind --model sonnet

# Use Claude 3.5 Haiku via AWS Bedrock
codefind --model haiku

# Use specific Bedrock model
codefind --model bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0
```