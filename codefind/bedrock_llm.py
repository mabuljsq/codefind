#!/usr/bin/env python3
"""
Direct AWS Bedrock integration for CodeFind.
Replaces litellm with native Bedrock API calls.
"""

import json
import os
import time
from typing import Dict, List, Optional, Any, Iterator

import boto3
from botocore.exceptions import ClientError, NoCredentialsError


class BedrockLLMError(Exception):
    """Base exception for Bedrock LLM errors."""
    pass


class BedrockAuthError(BedrockLLMError):
    """Authentication/credentials error."""
    pass


class BedrockRateLimitError(BedrockLLMError):
    """Rate limit exceeded error."""
    pass


class BedrockModelError(BedrockLLMError):
    """Model-specific error."""
    pass


class BedrockResponse:
    """Response object that mimics litellm response structure."""
    
    def __init__(self, response_data: Dict[str, Any], model: str):
        self.model = model
        self.choices = []
        self.usage = None
        
        # Parse Bedrock response based on model type
        if "anthropic" in model.lower():
            self._parse_anthropic_response(response_data)
        elif "amazon.titan" in model.lower():
            self._parse_titan_response(response_data)
        elif "meta.llama" in model.lower():
            self._parse_llama_response(response_data)
        else:
            raise BedrockModelError(f"Unsupported model type: {model}")
    
    def _parse_anthropic_response(self, data: Dict[str, Any]):
        """Parse Anthropic Claude response."""
        content = data.get('content', [])
        if content and isinstance(content, list):
            text = content[0].get('text', '')
        else:
            text = str(content)
        
        choice = type('Choice', (), {
            'message': type('Message', (), {
                'content': text,
                'role': 'assistant'
            })(),
            'finish_reason': data.get('stop_reason', 'stop')
        })()
        
        self.choices = [choice]
        
        # Parse usage
        usage_data = data.get('usage', {})
        self.usage = type('Usage', (), {
            'prompt_tokens': usage_data.get('input_tokens', 0),
            'completion_tokens': usage_data.get('output_tokens', 0),
            'total_tokens': usage_data.get('input_tokens', 0) + usage_data.get('output_tokens', 0)
        })()
    
    def _parse_titan_response(self, data: Dict[str, Any]):
        """Parse Amazon Titan response."""
        results = data.get('results', [])
        if results:
            text = results[0].get('outputText', '')
        else:
            text = ''
        
        choice = type('Choice', (), {
            'message': type('Message', (), {
                'content': text,
                'role': 'assistant'
            })(),
            'finish_reason': 'stop'
        })()
        
        self.choices = [choice]
        
        # Titan doesn't provide detailed usage info
        self.usage = type('Usage', (), {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0
        })()
    
    def _parse_llama_response(self, data: Dict[str, Any]):
        """Parse Meta Llama response."""
        text = data.get('generation', '')
        
        choice = type('Choice', (), {
            'message': type('Message', (), {
                'content': text,
                'role': 'assistant'
            })(),
            'finish_reason': data.get('stop_reason', 'stop')
        })()
        
        self.choices = [choice]
        
        # Llama usage info
        self.usage = type('Usage', (), {
            'prompt_tokens': data.get('prompt_token_count', 0),
            'completion_tokens': data.get('generation_token_count', 0),
            'total_tokens': data.get('prompt_token_count', 0) + data.get('generation_token_count', 0)
        })()


class BedrockLLM:
    """Direct Bedrock LLM client."""
    
    def __init__(self, region_name: str = None):
        self.region_name = region_name or os.environ.get('AWS_DEFAULT_REGION', 'us-west-2')
        self._client = None
    
    @property
    def client(self):
        """Lazy-load Bedrock client."""
        if self._client is None:
            try:
                self._client = boto3.client('bedrock-runtime', region_name=self.region_name)
            except NoCredentialsError:
                raise BedrockAuthError("AWS credentials not found. Please configure AWS credentials.")
        return self._client
    
    def completion(self, model: str, messages: List[Dict[str, str]], 
                  stream: bool = False, temperature: float = 0.0, 
                  max_tokens: int = 4096, **kwargs) -> BedrockResponse:
        """
        Send completion request to Bedrock.
        
        Args:
            model: Bedrock model ID (e.g., 'bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0')
            messages: List of message dicts with 'role' and 'content'
            stream: Whether to stream response (not implemented yet)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional model parameters
            
        Returns:
            BedrockResponse object
        """
        # Get the best available model ID (inference profile if available)
        model_id = get_best_model_id(model)
        
        # Convert messages to model-specific format
        if 'anthropic' in model_id.lower():
            body = self._format_anthropic_request(messages, temperature, max_tokens, **kwargs)
        elif 'amazon.titan' in model_id.lower():
            body = self._format_titan_request(messages, temperature, max_tokens, **kwargs)
        elif 'meta.llama' in model_id.lower():
            body = self._format_llama_request(messages, temperature, max_tokens, **kwargs)
        else:
            raise BedrockModelError(f"Unsupported model: {model_id}")
        
        try:
            # Check if streaming is disabled via environment variable
            disable_streaming = os.environ.get('BEDROCK_DISABLE_STREAMING', 'false').lower() == 'true'

            if stream and not disable_streaming:
                # Use streaming for real-time responses
                if self._is_inference_profile(model_id):
                    response = self.client.invoke_model_with_response_stream(
                        modelId=model_id,
                        body=json.dumps(body),
                        contentType='application/json',
                        accept='application/json'
                    )
                else:
                    response = self.client.invoke_model_with_response_stream(
                        modelId=model_id,
                        body=json.dumps(body),
                        contentType='application/json',
                        accept='application/json'
                    )

                # Return streaming response generator
                return self._handle_streaming_response(response, model_id)
            else:
                # Use regular non-streaming response
                if self._is_inference_profile(model_id):
                    response = self.client.invoke_model(
                        modelId=model_id,
                        body=json.dumps(body),
                        contentType='application/json',
                        accept='application/json'
                    )
                else:
                    response = self.client.invoke_model(
                        modelId=model_id,
                        body=json.dumps(body),
                        contentType='application/json',
                        accept='application/json'
                    )
            
            response_body = json.loads(response['body'].read())
            return BedrockResponse(response_body, model)
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ThrottlingException':
                raise BedrockRateLimitError(f"Rate limit exceeded: {e}")
            elif error_code == 'ValidationException':
                raise BedrockModelError(f"Invalid request: {e}")
            else:
                raise BedrockLLMError(f"Bedrock API error: {e}")
    
    def _format_anthropic_request(self, messages: List[Dict], temperature: float, 
                                max_tokens: int, **kwargs) -> Dict:
        """Format request for Anthropic Claude models."""
        # Convert messages to Anthropic format
        system_message = ""
        formatted_messages = []
        
        for msg in messages:
            if msg['role'] == 'system':
                system_message = msg['content']
            else:
                formatted_messages.append({
                    'role': msg['role'],
                    'content': msg['content']
                })
        
        body = {
            'messages': formatted_messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'anthropic_version': 'bedrock-2023-05-31'
        }
        
        if system_message:
            body['system'] = system_message
            
        return body
    
    def _format_titan_request(self, messages: List[Dict], temperature: float, 
                            max_tokens: int, **kwargs) -> Dict:
        """Format request for Amazon Titan models."""
        # Combine all messages into a single prompt
        prompt = ""
        for msg in messages:
            if msg['role'] == 'system':
                prompt += f"System: {msg['content']}\n\n"
            elif msg['role'] == 'user':
                prompt += f"Human: {msg['content']}\n\n"
            elif msg['role'] == 'assistant':
                prompt += f"Assistant: {msg['content']}\n\n"
        
        prompt += "Assistant: "
        
        return {
            'inputText': prompt,
            'textGenerationConfig': {
                'maxTokenCount': max_tokens,
                'temperature': temperature,
                'topP': kwargs.get('top_p', 0.9),
                'stopSequences': kwargs.get('stop', [])
            }
        }
    
    def _format_llama_request(self, messages: List[Dict], temperature: float, 
                            max_tokens: int, **kwargs) -> Dict:
        """Format request for Meta Llama models."""
        # Format as chat template
        prompt = ""
        for msg in messages:
            if msg['role'] == 'system':
                prompt += f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n{msg['content']}<|eot_id|>"
            elif msg['role'] == 'user':
                prompt += f"<|start_header_id|>user<|end_header_id|>\n{msg['content']}<|eot_id|>"
            elif msg['role'] == 'assistant':
                prompt += f"<|start_header_id|>assistant<|end_header_id|>\n{msg['content']}<|eot_id|>"
        
        prompt += "<|start_header_id|>assistant<|end_header_id|>\n"
        
        return {
            'prompt': prompt,
            'max_gen_len': max_tokens,
            'temperature': temperature,
            'top_p': kwargs.get('top_p', 0.9)
        }

    def _is_inference_profile(self, model_id):
        """
        Check if the model ID is an inference profile.
        Inference profiles typically start with region prefixes like 'us.', 'eu.', etc.
        """
        # Inference profiles follow the pattern: {region}.{provider}.{model-name}
        # Examples: us.anthropic.claude-3-5-sonnet-20240620-v1:0, eu.anthropic.claude-3-haiku-20240307-v1:0
        return bool(model_id and '.' in model_id and
                   any(model_id.startswith(f"{region}.") for region in
                       ['us', 'eu', 'ap', 'ca', 'sa', 'af', 'me']))  # Common AWS region prefixes

    def _handle_streaming_response(self, response, model_id):
        """
        Handle streaming response from Bedrock and yield chunks compatible with the coder.
        """
        try:
            # Get the event stream
            event_stream = response['body']

            for event in event_stream:
                if 'chunk' in event:
                    chunk_data = json.loads(event['chunk']['bytes'].decode())

                    # Parse based on model type
                    if 'anthropic' in model_id.lower():
                        chunk_text = self._parse_anthropic_streaming_chunk(chunk_data)
                    elif 'amazon.titan' in model_id.lower():
                        chunk_text = self._parse_titan_streaming_chunk(chunk_data)
                    elif 'meta.llama' in model_id.lower():
                        chunk_text = self._parse_llama_streaming_chunk(chunk_data)
                    else:
                        chunk_text = ""

                    # Only yield chunks with actual content
                    if chunk_text:
                        # Create a streaming chunk compatible with the coder
                        chunk = type('StreamingChunk', (), {
                            'choices': [type('Choice', (), {
                                'delta': type('Delta', (), {
                                    'content': chunk_text,
                                    'role': 'assistant'
                                })(),
                                'finish_reason': None
                            })()]
                        })()

                        yield chunk

        except Exception as e:
            # If streaming fails, fall back to a single chunk with error
            error_chunk = type('StreamingChunk', (), {
                'choices': [type('Choice', (), {
                    'delta': type('Delta', (), {
                        'content': f"Streaming error: {str(e)}",
                        'role': 'assistant'
                    })(),
                    'finish_reason': 'error'
                })()]
            })()
            yield error_chunk
            return

        # Send final chunk to indicate completion
        final_chunk = type('StreamingChunk', (), {
            'choices': [type('Choice', (), {
                'delta': type('Delta', (), {
                    'content': "",
                    'role': 'assistant'
                })(),
                'finish_reason': 'stop'
            })()]
        })()
        yield final_chunk

    def _parse_anthropic_streaming_chunk(self, chunk_data):
        """Parse streaming chunk from Anthropic Claude models."""
        try:
            # Debug: print chunk structure to understand format
            # print(f"DEBUG: Chunk data: {chunk_data}")

            # Anthropic streaming format - check different possible structures
            if chunk_data.get('type') == 'content_block_delta':
                delta = chunk_data.get('delta', {})
                return delta.get('text', '')
            elif chunk_data.get('type') == 'content_block_start':
                # Start of content block - no text yet
                return ""
            elif chunk_data.get('type') == 'message_delta':
                # Message metadata - no text content
                return ""
            elif 'completion' in chunk_data:
                # Alternative format: direct completion text
                return chunk_data.get('completion', '')
            elif 'delta' in chunk_data:
                # Alternative format: delta with text
                delta = chunk_data.get('delta', {})
                return delta.get('text', '')
            elif 'text' in chunk_data:
                # Direct text field
                return chunk_data.get('text', '')

            return ""
        except Exception as e:
            # print(f"DEBUG: Error parsing chunk: {e}")
            return ""

    def _parse_titan_streaming_chunk(self, chunk_data):
        """Parse streaming chunk from Amazon Titan models."""
        try:
            # Titan streaming format
            return chunk_data.get('outputText', '')
        except Exception:
            return ""

    def _parse_llama_streaming_chunk(self, chunk_data):
        """Parse streaming chunk from Meta Llama models."""
        try:
            # Llama streaming format
            return chunk_data.get('generation', '')
        except Exception:
            return ""


# Global instance
bedrock_llm = BedrockLLM()

# Compatibility functions to replace litellm calls
def completion(**kwargs):
    """Drop-in replacement for litellm.completion()."""
    return bedrock_llm.completion(**kwargs)


def validate_environment(model: str) -> Dict[str, Any]:
    """Validate AWS Bedrock environment for the given model."""
    def is_bedrock_model(model_name):
        """Check if model is a Bedrock model or inference profile."""
        return (model_name.startswith("bedrock/") or
                any(model_name.startswith(f"{region}.") for region in
                    ['us', 'eu', 'ap', 'ca', 'sa', 'af', 'me']))

    if not is_bedrock_model(model):
        return {
            'keys_in_environment': False,
            'missing_keys': ['BEDROCK_MODEL_REQUIRED']
        }
    
    # Check AWS credentials
    missing_keys = []
    keys_in_environment = []
    
    # Check for AWS credentials
    if not (os.environ.get('AWS_ACCESS_KEY_ID') and os.environ.get('AWS_SECRET_ACCESS_KEY')):
        if not os.environ.get('AWS_PROFILE'):
            # Check if we're running on AWS infrastructure with IAM roles
            try:
                import boto3
                session = boto3.Session()
                credentials = session.get_credentials()
                if not credentials:
                    missing_keys.extend(['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'])
                else:
                    keys_in_environment.append('AWS_IAM_ROLE')
            except:
                missing_keys.extend(['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'])
        else:
            keys_in_environment.append('AWS_PROFILE')
    else:
        keys_in_environment.extend(['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'])
    
    return {
        'keys_in_environment': bool(keys_in_environment),
        'missing_keys': missing_keys
    }


def get_available_inference_profiles() -> Dict[str, str]:
    """
    Get available inference profiles from AWS Bedrock.
    Returns a mapping of model names to inference profile IDs.
    """
    try:
        bedrock = boto3.client('bedrock')
        profiles = bedrock.list_inference_profiles()

        profile_map = {}
        for profile in profiles.get('inferenceProfileSummaries', []):
            profile_id = profile['inferenceProfileId']
            # Extract the base model name from the profile ID
            # e.g., us.anthropic.claude-3-5-sonnet-20240620-v1:0 -> anthropic.claude-3-5-sonnet-20240620-v1:0
            if '.' in profile_id:
                parts = profile_id.split('.', 1)
                if len(parts) > 1:
                    base_model = parts[1]  # Remove region prefix
                    profile_map[base_model] = profile_id

        return profile_map
    except Exception as e:
        print(f"Warning: Could not fetch inference profiles: {e}")
        return {}


def get_best_model_id(requested_model: str) -> str:
    """
    Get the best available model ID, preferring inference profiles when available.

    Args:
        requested_model: The requested model (e.g., "anthropic.claude-3-5-sonnet-20241022-v2:0")

    Returns:
        The best available model ID (inference profile ID if available, otherwise the original)
    """
    # Remove bedrock/ prefix if present
    clean_model = requested_model.replace('bedrock/', '')

    # If it's already an inference profile, return as-is
    if any(clean_model.startswith(f"{region}.") for region in ['us', 'eu', 'ap', 'ca', 'sa', 'af', 'me']):
        return clean_model

    # Check if there's an available inference profile for this model
    profiles = get_available_inference_profiles()
    if clean_model in profiles:
        return profiles[clean_model]

    # Return the original model ID
    return clean_model


def get_model_info(model: str) -> Dict[str, Any]:
    """Get model information (placeholder for compatibility)."""
    # This would normally fetch from Bedrock API, but for now return basic info
    return {
        'max_tokens': 4096,
        'max_input_tokens': 200000,
        'litellm_provider': 'bedrock',
        'mode': 'chat'
    }


def encode(model: str, text: str) -> List[int]:
    """Tokenize text (placeholder implementation)."""
    # Simple approximation: ~4 chars per token
    return list(range(len(text) // 4))


def token_counter(model: str, messages: List[Dict]) -> int:
    """Count tokens in messages (placeholder implementation)."""
    total_chars = sum(len(str(msg.get('content', ''))) for msg in messages)
    return total_chars // 4  # Rough approximation
