# lambda/agent_router/detailed_investment_router.py

import json
import os
import boto3
import uuid

bedrock_agent = boto3.client("bedrock-agent-runtime")
AGENT_ID = os.environ["AGENT_ID"]
AGENT_ALIAS_ID = os.environ["AGENT_ALIAS_ID"]

def handler(event, context):
    """
    Lambda function to route queries to the detailed investment agent
    """
    try:
        print(f"Received event: {json.dumps(event, default=str)}")
        
        # Handle case where event might be a list or have different structure
        if isinstance(event, list):
            event = event[0] if event else {}
        
        # Parse the input from the orchestrator agent
        function_name = event.get("function", "")
        parameters_list = event.get("parameters", [])
        action_group = event.get("actionGroup", "")
        
        # Convert parameters list to dictionary
        parameters = {}
        if isinstance(parameters_list, list):
            for param in parameters_list:
                if isinstance(param, dict) and "name" in param and "value" in param:
                    parameters[param["name"]] = param["value"]
        
        # Alternative parsing for different event structures
        if not function_name and "inputText" in event:
            # Direct invocation format
            function_name = "invoke_detailed_investment_agent"
            parameters = {"query": event.get("inputText", "")}
        
        if function_name != "invoke_detailed_investment_agent":
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
        
        query = parameters.get("query", "")
        if not query:
            return {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": action_group,
                    "function": function_name,
                    "functionResponse": {
                        "responseBody": {
                            "TEXT": {
                                "body": "Error: Missing 'query' parameter"
                            }
                        }
                    }
                }
            }
        
        # Generate a unique session ID for this conversation
        session_id = str(uuid.uuid4())
        
        # Invoke the detailed investment agent
        response = bedrock_agent.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=session_id,
            inputText=query,
        )
        
        completion = ""
        # The response from the agent is a stream of data chunks
        for chunk in response['completion']:
            completion += chunk['chunk']['bytes'].decode()
        
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": action_group,
                "function": function_name,
                "functionResponse": {
                    "responseBody": {
                        "TEXT": {
                            "body": completion
                        }
                    }
                }
            }
        }
        
    except Exception as e:
        print(f"Error invoking detailed investment agent: {e}")
        print(f"Event structure: {json.dumps(event, default=str)}")
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "") if isinstance(event, dict) else "",
                "function": function_name if 'function_name' in locals() else "",
                "functionResponse": {
                    "responseBody": {
                        "TEXT": {
                            "body": f"Error invoking detailed investment agent: {str(e)}"
                        }
                    }
                }
            }
        }