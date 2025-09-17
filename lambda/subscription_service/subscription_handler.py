import json
import urllib3
import os
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize HTTP client
http = urllib3.PoolManager()

def handler(event, context):
    """
    Lambda function to handle subscription checking and subscription creation
    for the Vanguard Investment Advice service.
    """
    try:
        print(f"Received event: {json.dumps(event, default=str)}")
        
        # Handle case where event might be a list or have different structure
        if isinstance(event, list):
            event = event[0] if event else {}
        
        # Parse the input from the bedrock agent
        function_name = event.get("function", "")
        parameters_list = event.get("parameters", [])
        action_group = event.get("actionGroup", "")
        
        # Convert parameters list to dictionary
        parameters = {}
        if isinstance(parameters_list, list):
            for param in parameters_list:
                if isinstance(param, dict) and "name" in param and "value" in param:
                    parameters[param["name"]] = param["value"]
        elif isinstance(parameters_list, dict):
            parameters = parameters_list
        
        logger.info(f"Function called: {function_name}")
        logger.info(f"Parameters: {parameters}")
        
        if function_name == 'check_subscription':
            result = check_subscription(parameters)
        elif function_name == 'subscribe_to_service':
            result = subscribe_to_service(parameters)
        else:
            return {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": action_group,
                    "function": function_name,
                    "functionResponse": {
                        "responseBody": {
                            "TEXT": {
                                "body": f"Error: Unknown function: {function_name}"
                            }
                        }
                    }
                }
            }
        
        # Extract the response body from the result
        if result.get('statusCode') == 200:
            body_data = json.loads(result['body'])
            
            # Format response based on function type
            if function_name == 'check_subscription':
                response_text = json.dumps(body_data)
            elif function_name == 'subscribe_to_service':
                # Create a user-friendly message for subscription success
                if body_data.get('success'):
                    response_text = f"Great! You have successfully subscribed to the Vanguard Investment Advice service. You now have access to detailed investment advice and personalized recommendations."
                else:
                    response_text = f"There was an issue with your subscription: {body_data.get('message', 'Unknown error')}"
            else:
                response_text = json.dumps(body_data)
        else:
            error_data = json.loads(result['body'])
            response_text = f"Error: {error_data.get('error', 'Unknown error')}"
        
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": action_group,
                "function": function_name,
                "functionResponse": {
                    "responseBody": {
                        "TEXT": {
                            "body": response_text
                        }
                    }
                }
            }
        }
            
    except Exception as e:
        logger.error(f"Error in subscription handler: {str(e)}")
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "") if isinstance(event, dict) else "",
                "function": function_name if 'function_name' in locals() else "",
                "functionResponse": {
                    "responseBody": {
                        "TEXT": {
                            "body": f"Error in subscription handler: {str(e)}"
                        }
                    }
                }
            }
        }

def check_subscription(parameters):
    """
    Check if the user has subscribed to the Vanguard Investment Advice service.
    """
    try:
        user_id = parameters.get('user_id', 'quang')  # Default to 'quang' for now
        
        # Call the subscription check API
        check_url = f"https://kpfnbcvnfb.execute-api.us-east-1.amazonaws.com/dev/permissions/{user_id}"
        
        logger.info(f"Checking subscription for user: {user_id}")
        logger.info(f"API URL: {check_url}")
        
        response = http.request('GET', check_url, timeout=10)
        
        if response.status != 200:
            logger.error(f"API request failed with status: {response.status}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': f'API request failed with status: {response.status}',
                    'details': response.data.decode('utf-8') if response.data else 'No response data'
                })
            }
        
        subscription_data = json.loads(response.data.decode('utf-8'))
        logger.info(f"Subscription check response: {subscription_data}")
        
        # Handle both list and dict responses from the API
        permitted_agents = []
        if isinstance(subscription_data, dict):
            # If it's a dict, extract from 'data' field
            permitted_agents = subscription_data.get('data', {}).get('permitted_agents', [])
        elif isinstance(subscription_data, list):
            # If it's a list, it might be the permitted_agents directly
            permitted_agents = subscription_data
        
        # Check if the user has access to the detailed investment agent
        has_subscription = len(permitted_agents) > 0
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'has_subscription': has_subscription,
                'permitted_agents': permitted_agents,
                'user_id': user_id,
                'raw_response': subscription_data
            })
        }
        
    except urllib3.exceptions.HTTPError as e:
        logger.error(f"HTTP request failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Failed to check subscription status',
                'details': str(e)
            })
        }
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Invalid JSON response from API',
                'details': str(e)
            })
        }
    except Exception as e:
        logger.error(f"Error checking subscription: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal error while checking subscription',
                'details': str(e)
            })
        }

def subscribe_to_service(parameters):
    """
    Subscribe the user to the Vanguard Investment Advice service.
    """
    try:
        user_id = parameters.get('user_id', 'quang')  # Default to 'quang' for now
        agent_name = parameters.get('agent_name', 'detailed-investment-agent')
        
        # Call the subscription API
        subscribe_url = f"https://kpfnbcvnfb.execute-api.us-east-1.amazonaws.com/dev/permissions/{user_id}/agents"
        
        payload = {
            'agent_name': agent_name
        }
        
        encoded_data = json.dumps(payload).encode('utf-8')
        
        logger.info(f"Subscribing user {user_id} to agent {agent_name}")
        logger.info(f"API URL: {subscribe_url}")
        logger.info(f"Payload: {payload}")
        
        response = http.request(
            'POST',
            subscribe_url,
            body=encoded_data,
            headers={
                'Content-Type': 'application/json'
            },
            timeout=10
        )
        
        if response.status != 200:
            logger.error(f"API request failed with status: {response.status}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': f'API request failed with status: {response.status}',
                    'details': response.data.decode('utf-8') if response.data else 'No response data'
                })
            }
        
        subscription_result = json.loads(response.data.decode('utf-8'))
        logger.info(f"Subscription response: {subscription_result}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'message': f'Successfully subscribed {user_id} to {agent_name}',
                'subscription_result': subscription_result
            })
        }
        
    except urllib3.exceptions.HTTPError as e:
        logger.error(f"HTTP request failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Failed to subscribe to service',
                'details': str(e)
            })
        }
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Invalid JSON response from API',
                'details': str(e)
            })
        }
    except Exception as e:
        logger.error(f"Error subscribing to service: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal error while subscribing',
                'details': str(e)
            })
        }