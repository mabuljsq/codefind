<h1 align="center">
CodeFind - AI Pair Programming with AWS Bedrock & Knowledge Graphs
</h1>


<p align="center">
CodeFind lets you pair program with AWS Bedrock LLMs enhanced by knowledge graph retrieval to start a new project or build on your existing codebase.
</p>

## Getting Started

```bash
# Install CodeFind
pip install -e .

# Change directory into your codebase
cd /to/your/project

# Set up AWS credentials (via .env file or AWS CLI)
export AWS_ACCESS_KEY_ID=<your-key>
export AWS_SECRET_ACCESS_KEY=<your-secret>
export AWS_DEFAULT_REGION=us-west-2

# Use Claude 3.5 Sonnet via AWS Bedrock
codefind --model sonnet

# Use Claude 3.5 Haiku via AWS Bedrock
codefind --model haiku

# Use specific Bedrock model
codefind --model bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0
```