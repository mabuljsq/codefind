"""
AWS Bedrock Knowledge Graph integration for CodeFind.

This module provides functionality to connect to AWS Bedrock Knowledge Bases
with GraphRAG capabilities, allowing CodeFind to retrieve information from
knowledge graphs stored in Amazon Neptune Analytics.
"""

import json
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


@dataclass
class KnowledgeGraphResult:
    """Represents a result from knowledge graph retrieval."""
    content: str
    score: float
    metadata: Dict[str, Any]
    location: Optional[Dict[str, Any]] = None
    source_type: Optional[str] = None


@dataclass
class KnowledgeGraphConfig:
    """Configuration for Bedrock Knowledge Graph client."""
    knowledge_base_id: str
    region_name: str = "us-west-2"
    max_results: int = 10
    search_type: str = "HYBRID"  # HYBRID or SEMANTIC
    enable_reranking: bool = False
    reranking_model_arn: Optional[str] = None
    guardrail_id: Optional[str] = None
    guardrail_version: Optional[str] = None


class BedrockKnowledgeGraphClient:
    """
    Client for interacting with AWS Bedrock Knowledge Bases with GraphRAG support.
    
    This client provides methods to query knowledge bases that are backed by
    Amazon Neptune Analytics graphs, enabling GraphRAG (Graph Retrieval-Augmented Generation)
    capabilities.
    """
    
    def __init__(self, config: KnowledgeGraphConfig):
        """
        Initialize the Bedrock Knowledge Graph client.
        
        Args:
            config: Configuration object containing knowledge base settings
            
        Raises:
            ImportError: If boto3 is not installed
            ValueError: If required configuration is missing
        """
        if not BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 is required for Bedrock Knowledge Graph integration. "
                "Install it with: pip install boto3"
            )
        
        self.config = config
        self._validate_config()
        
        # Initialize the Bedrock Agent Runtime client
        try:
            self.client = boto3.client(
                'bedrock-agent-runtime',
                region_name=config.region_name
            )
        except NoCredentialsError:
            raise ValueError(
                "AWS credentials not found. Please configure your AWS credentials using "
                "AWS CLI, environment variables, or IAM roles."
            )
    
    def _validate_config(self) -> None:
        """Validate the configuration parameters."""
        if not self.config.knowledge_base_id:
            raise ValueError("knowledge_base_id is required")
        
        if self.config.search_type not in ["HYBRID", "SEMANTIC"]:
            raise ValueError("search_type must be either 'HYBRID' or 'SEMANTIC'")
        
        if self.config.max_results < 1 or self.config.max_results > 100:
            raise ValueError("max_results must be between 1 and 100")
    
    def retrieve(self, query: str, **kwargs) -> List[KnowledgeGraphResult]:
        """
        Retrieve information from the knowledge graph based on a query.
        
        Args:
            query: The search query text
            **kwargs: Additional parameters to override config defaults
            
        Returns:
            List of KnowledgeGraphResult objects containing retrieved information
            
        Raises:
            ClientError: If the AWS API call fails
            ValueError: If the query is empty
        """
        if not query.strip():
            raise ValueError("Query cannot be empty")
        
        # Build the retrieval configuration
        retrieval_config = self._build_retrieval_config(**kwargs)
        
        # Build the request parameters
        request_params = {
            'knowledgeBaseId': self.config.knowledge_base_id,
            'retrievalQuery': {
                'text': query
            },
            'retrievalConfiguration': retrieval_config
        }
        
        # Add guardrail configuration if specified
        if self.config.guardrail_id and self.config.guardrail_version:
            request_params['guardrailConfiguration'] = {
                'guardrailId': self.config.guardrail_id,
                'guardrailVersion': self.config.guardrail_version
            }
        
        try:
            response = self.client.retrieve(**request_params)
            return self._parse_response(response)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            raise ClientError(
                error_response={
                    'Error': {
                        'Code': error_code,
                        'Message': f"Bedrock Knowledge Graph retrieval failed: {error_message}"
                    }
                },
                operation_name='retrieve'
            )

    def _build_retrieval_config(self, **kwargs) -> Dict[str, Any]:
        """Build the retrieval configuration for the API call."""
        max_results = kwargs.get('max_results', self.config.max_results)
        search_type = kwargs.get('search_type', self.config.search_type)

        vector_config = {
            'numberOfResults': max_results,
            'overrideSearchType': search_type
        }

        # Add reranking configuration if enabled
        if self.config.enable_reranking and self.config.reranking_model_arn:
            vector_config['rerankingConfiguration'] = {
                'type': 'BEDROCK_RERANKING_MODEL',
                'bedrockRerankingConfiguration': {
                    'modelConfiguration': {
                        'modelArn': self.config.reranking_model_arn
                    },
                    'numberOfRerankedResults': min(max_results, 25)  # Max 25 for reranking
                }
            }

        return {
            'vectorSearchConfiguration': vector_config
        }

    def _parse_response(self, response: Dict[str, Any]) -> List[KnowledgeGraphResult]:
        """Parse the API response into KnowledgeGraphResult objects."""
        results = []

        for item in response.get('retrievalResults', []):
            content = self._extract_content(item.get('content', {}))
            score = item.get('score', 0.0)
            metadata = item.get('metadata', {})
            location = item.get('location')
            source_type = location.get('type') if location else None

            result = KnowledgeGraphResult(
                content=content,
                score=score,
                metadata=metadata,
                location=location,
                source_type=source_type
            )
            results.append(result)

        return results

    def _extract_content(self, content_data: Dict[str, Any]) -> str:
        """Extract text content from the content data structure."""
        if 'text' in content_data:
            return content_data['text']
        elif 'byteContent' in content_data:
            # Handle base64 encoded content if needed
            return f"[Binary content: {content_data.get('type', 'unknown')}]"
        elif 'row' in content_data:
            # Handle structured row data
            rows = content_data['row']
            if rows:
                return '\n'.join([
                    f"{row.get('columnName', '')}: {row.get('columnValue', '')}"
                    for row in rows
                ])
        return ""

    def retrieve_and_format(self, query: str, format_template: Optional[str] = None) -> str:
        """
        Retrieve information and format it for use in CodeFind context.

        Args:
            query: The search query
            format_template: Optional template for formatting results

        Returns:
            Formatted string containing the retrieved information
        """
        results = self.retrieve(query)

        if not results:
            return f"No results found for query: {query}"

        if format_template:
            return self._format_with_template(results, format_template)

        # Default formatting
        formatted_results = [f"# Knowledge Graph Results for: {query}\n"]

        for i, result in enumerate(results, 1):
            formatted_results.append(f"## Result {i} (Score: {result.score:.3f})")
            formatted_results.append(f"**Source:** {result.source_type or 'Unknown'}")
            formatted_results.append(f"**Content:**\n{result.content}")

            if result.metadata:
                formatted_results.append(f"**Metadata:** {json.dumps(result.metadata, indent=2)}")

            formatted_results.append("---")

        return "\n\n".join(formatted_results)

    def _format_with_template(self, results: List[KnowledgeGraphResult], template: str) -> str:
        """Format results using a custom template."""
        formatted_parts = []

        for result in results:
            formatted_part = template.format(
                content=result.content,
                score=result.score,
                metadata=json.dumps(result.metadata),
                source_type=result.source_type or 'Unknown'
            )
            formatted_parts.append(formatted_part)

        return "\n".join(formatted_parts)

    def test_connection(self) -> bool:
        """
        Test the connection to the knowledge base.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            # Try a simple query to test the connection
            self.retrieve("test", max_results=1)
            return True
        except Exception:
            return False


def create_client_from_env() -> Optional[BedrockKnowledgeGraphClient]:
    """
    Create a BedrockKnowledgeGraphClient from environment variables.

    Expected environment variables:
    - BEDROCK_KNOWLEDGE_BASE_ID: The knowledge base ID (required)
    - BEDROCK_REGION: AWS region (default: us-west-2)
    - BEDROCK_MAX_RESULTS: Maximum results to return (default: 10)
    - BEDROCK_SEARCH_TYPE: Search type HYBRID or SEMANTIC (default: HYBRID)
    - BEDROCK_ENABLE_RERANKING: Enable reranking (default: false)
    - BEDROCK_RERANKING_MODEL_ARN: ARN for reranking model
    - BEDROCK_GUARDRAIL_ID: Guardrail ID
    - BEDROCK_GUARDRAIL_VERSION: Guardrail version

    Returns:
        BedrockKnowledgeGraphClient instance or None if required config is missing
    """
    knowledge_base_id = os.environ.get('BEDROCK_KNOWLEDGE_BASE_ID')
    if not knowledge_base_id:
        return None

    config = KnowledgeGraphConfig(
        knowledge_base_id=knowledge_base_id,
        region_name=os.environ.get('BEDROCK_REGION', 'us-west-2'),
        max_results=int(os.environ.get('BEDROCK_MAX_RESULTS', '10')),
        search_type=os.environ.get('BEDROCK_SEARCH_TYPE', 'HYBRID'),
        enable_reranking=os.environ.get('BEDROCK_ENABLE_RERANKING', '').lower() == 'true',
        reranking_model_arn=os.environ.get('BEDROCK_RERANKING_MODEL_ARN'),
        guardrail_id=os.environ.get('BEDROCK_GUARDRAIL_ID'),
        guardrail_version=os.environ.get('BEDROCK_GUARDRAIL_VERSION')
    )

    try:
        return BedrockKnowledgeGraphClient(config)
    except (ImportError, ValueError) as e:
        print(f"Failed to create Bedrock Knowledge Graph client: {e}")
        return None


def create_client_from_args(args) -> Optional[BedrockKnowledgeGraphClient]:
    """
    Create a BedrockKnowledgeGraphClient from command line arguments.

    Args:
        args: Parsed command line arguments

    Returns:
        BedrockKnowledgeGraphClient instance or None if not configured
    """
    if not hasattr(args, 'bedrock_knowledge_base_id') or not args.bedrock_knowledge_base_id:
        return None

    config = KnowledgeGraphConfig(
        knowledge_base_id=args.bedrock_knowledge_base_id,
        region_name=getattr(args, 'bedrock_region', 'us-west-2'),
        max_results=getattr(args, 'bedrock_max_results', 10),
        search_type=getattr(args, 'bedrock_search_type', 'HYBRID'),
        enable_reranking=getattr(args, 'bedrock_enable_reranking', False),
        reranking_model_arn=getattr(args, 'bedrock_reranking_model_arn', None),
        guardrail_id=getattr(args, 'bedrock_guardrail_id', None),
        guardrail_version=getattr(args, 'bedrock_guardrail_version', None)
    )

    try:
        return BedrockKnowledgeGraphClient(config)
    except (ImportError, ValueError) as e:
        print(f"Failed to create Bedrock Knowledge Graph client: {e}")
        return None


class KnowledgeGraphRetriever:
    """
    A retriever class that integrates with CodeFind's existing retrieval systems.
    """

    def __init__(self, client: BedrockKnowledgeGraphClient):
        """Initialize with a Bedrock Knowledge Graph client."""
        self.client = client

    def retrieve(self, query: str, max_results: Optional[int] = None) -> str:
        """
        Retrieve information formatted for CodeFind context.

        Args:
            query: The search query
            max_results: Maximum number of results to return

        Returns:
            Formatted string containing retrieved information
        """
        kwargs = {}
        if max_results is not None:
            kwargs['max_results'] = max_results

        return self.client.retrieve_and_format(query, **kwargs)

    def ask(self, question: str) -> str:
        """
        Ask a question and get formatted results (compatible with Help class interface).

        Args:
            question: The question to ask

        Returns:
            Formatted context string
        """
        results = self.client.retrieve(question)

        if not results:
            return f"# Question: {question}\n\nNo relevant information found in the knowledge graph."

        context = f"# Question: {question}\n\n# Relevant knowledge graph data:\n\n"

        for i, result in enumerate(results, 1):
            context += f"## Knowledge Graph Result {i} (Relevance: {result.score:.3f})\n\n"
            context += f"{result.content}\n\n"

            if result.metadata:
                context += f"**Metadata:** {json.dumps(result.metadata, indent=2)}\n\n"

            context += "---\n\n"

        return context
