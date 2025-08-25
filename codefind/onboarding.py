#!/usr/bin/env python

import os
import subprocess
import sys

# URLs module removed - CodeFind uses AWS documentation
from codefind.io import InputOutput


def check_aws_credentials():
    """
    Check if AWS credentials are available through various methods.
    
    Returns:
        dict: Information about available AWS credentials
    """
    cred_info = {
        'has_credentials': False,
        'method': None,
        'profile': None,
        'region': None
    }
    
    # Check environment variables
    if os.environ.get('AWS_ACCESS_KEY_ID') and os.environ.get('AWS_SECRET_ACCESS_KEY'):
        cred_info['has_credentials'] = True
        cred_info['method'] = 'environment_variables'
        cred_info['region'] = os.environ.get('AWS_DEFAULT_REGION', 'us-west-2')
        return cred_info
    
    # Check AWS profile
    if os.environ.get('AWS_PROFILE'):
        cred_info['has_credentials'] = True
        cred_info['method'] = 'aws_profile'
        cred_info['profile'] = os.environ.get('AWS_PROFILE')
        cred_info['region'] = os.environ.get('AWS_DEFAULT_REGION', 'us-west-2')
        return cred_info
    
    # Check if AWS CLI is configured
    try:
        result = subprocess.run(['aws', 'sts', 'get-caller-identity'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            cred_info['has_credentials'] = True
            cred_info['method'] = 'aws_cli'
            # Try to get the region
            try:
                region_result = subprocess.run(['aws', 'configure', 'get', 'region'], 
                                             capture_output=True, text=True, timeout=5)
                if region_result.returncode == 0:
                    cred_info['region'] = region_result.stdout.strip() or 'us-west-2'
                else:
                    cred_info['region'] = 'us-west-2'
            except:
                cred_info['region'] = 'us-west-2'
            return cred_info
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # Check for IAM role (if running on EC2/ECS/Lambda)
    try:
        import boto3
        session = boto3.Session()
        credentials = session.get_credentials()
        if credentials:
            cred_info['has_credentials'] = True
            cred_info['method'] = 'iam_role'
            cred_info['region'] = session.region_name or 'us-west-2'
            return cred_info
    except:
        pass
    
    return cred_info


def try_to_select_default_model():
    """
    Attempts to select a default Bedrock model based on available AWS credentials.
    
    Returns:
        The name of the selected model, or None if no AWS credentials are found.
    """
    cred_info = check_aws_credentials()
    
    if cred_info['has_credentials']:
        # Default to Claude 3.7 Sonnet if AWS credentials are available
        return "bedrock/us.anthropic.claude-3-7-sonnet-20250109-v1:0"
    
    return None


def offer_aws_setup(io):
    """
    Offers AWS credential setup guidance to the user.

    Args:
        io: The InputOutput object for user interaction.

    Returns:
        True if user wants to proceed with setup, False otherwise.
    """
    io.tool_output("CodeFind requires AWS credentials to access Bedrock models.")
    io.tool_output()
    io.tool_output("You can set up AWS credentials in several ways:")
    io.tool_output("1. AWS CLI: Run 'aws configure' to set up credentials")
    io.tool_output("2. Environment variables: Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
    io.tool_output("3. AWS Profile: Set AWS_PROFILE environment variable")
    io.tool_output("4. IAM Roles: If running on AWS infrastructure")
    io.tool_output()

    if io.confirm_ask("Would you like to open the AWS credentials setup guide?", default="y"):
        io.offer_url("https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html",
                     "Open AWS credentials guide?")
        return True

    return False


def select_default_model(args, io):
    """
    Selects a default Bedrock model based on available AWS credentials.
    Offers AWS setup guidance if no credentials are found.

    Args:
        args: The command line arguments object.
        io: The InputOutput object for user interaction.

    Returns:
        The selected model name, or None if no model could be selected.
    """
    # If a model is already specified, return it
    if hasattr(args, 'model') and args.model:
        return args.model

    # Try to select a default model based on AWS credentials
    model = try_to_select_default_model()
    if model:
        io.tool_output(f"Using default model: {model}")
        return model

    # No AWS credentials found
    no_creds_msg = "No AWS credentials found for Bedrock access."
    io.tool_warning(no_creds_msg)

    # Offer AWS setup guidance
    if offer_aws_setup(io):
        # Check again after potential setup
        model = try_to_select_default_model()
        if model:
            io.tool_output(f"Using model: {model}")
            return model

    io.tool_error("CodeFind requires AWS credentials to access Bedrock models.")
    io.tool_output("Please configure AWS credentials and try again.")
    io.tool_output("Visit AWS Bedrock documentation for more info: https://docs.aws.amazon.com/bedrock/")

    return None


def check_bedrock_access(io, region='us-west-2'):
    """
    Check if the user has access to AWS Bedrock in the specified region.
    
    Args:
        io: The InputOutput object for user interaction.
        region: AWS region to check (default: us-west-2)
        
    Returns:
        bool: True if Bedrock access is available, False otherwise.
    """
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError
        
        client = boto3.client('bedrock', region_name=region)
        # Try to list foundation models to test access
        response = client.list_foundation_models()
        
        if response.get('modelSummaries'):
            io.tool_output(f"✅ Bedrock access confirmed in region {region}")
            return True
        else:
            io.tool_warning(f"⚠️  Bedrock access limited in region {region}")
            return False
            
    except NoCredentialsError:
        io.tool_error("❌ No AWS credentials found")
        return False
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'UnauthorizedOperation':
            io.tool_error(f"❌ No permission to access Bedrock in region {region}")
        elif error_code == 'OptInRequired':
            io.tool_error(f"❌ Bedrock not enabled in region {region}. Please enable it in the AWS console.")
        else:
            io.tool_error(f"❌ Bedrock access error: {error_code}")
        return False
    except ImportError:
        io.tool_error("❌ boto3 not installed. Run: pip install boto3")
        return False
    except Exception as e:
        io.tool_error(f"❌ Unexpected error checking Bedrock access: {e}")
        return False


def validate_bedrock_setup(io):
    """
    Validate that AWS Bedrock is properly set up and accessible.

    Args:
        io: The InputOutput object for user interaction.

    Returns:
        bool: True if setup is valid, False otherwise.
    """
    io.tool_output("Validating AWS Bedrock setup...")
    
    # Check AWS credentials
    cred_info = check_aws_credentials()
    if not cred_info['has_credentials']:
        io.tool_error("❌ No AWS credentials found")
        offer_aws_setup(io)
        return False
    
    io.tool_output(f"✅ AWS credentials found via {cred_info['method']}")
    if cred_info['profile']:
        io.tool_output(f"   Profile: {cred_info['profile']}")
    io.tool_output(f"   Region: {cred_info['region']}")
    
    # Check Bedrock access
    if not check_bedrock_access(io, cred_info['region']):
        return False
    
    return True


def main():
    """Main function to test the AWS Bedrock setup validation."""
    print("Testing AWS Bedrock setup validation...")

    # Use a real IO object for interaction
    io = InputOutput(
        pretty=True,
        yes=False,
        tool_output_color="BLUE",
        tool_warning_color="YELLOW",
        tool_error_color="RED",
    )
    
    # Test credential detection
    cred_info = check_aws_credentials()
    print(f"Credentials found: {cred_info}")
    
    # Test model selection
    class MockArgs:
        model = None
    
    args = MockArgs()
    model = select_default_model(args, io)
    print(f"Selected model: {model}")

    # Test Bedrock validation
    if model:
        is_valid = validate_bedrock_setup(io)
        print(f"Bedrock setup valid: {is_valid}")
    
    print("AWS Bedrock setup test finished.")


if __name__ == "__main__":
    main()
