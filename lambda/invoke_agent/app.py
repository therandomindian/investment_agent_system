# lambda/invoke_agent/app.py

import json
import os
import boto3
import uuid

bedrock_agent = boto3.client("bedrock-agent-runtime")
ORCHESTRATOR_AGENT_ID = os.environ["ORCHESTRATOR_AGENT_ID"]
ORCHESTRATOR_AGENT_ALIAS_ID = os.environ["ORCHESTRATOR_AGENT_ALIAS_ID"]

def handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        prompt = body.get("query")
        # Use a provided session_id or create a new one for each conversation
        session_id = body.get("session_id", str(uuid.uuid4()))

        if not prompt:
            return {
                "statusCode": 400, 
                "body": json.dumps({"error": "Missing 'query' in request body"})
            }

        # Check if the placeholder is still there
        if "PLACEHOLDER" in ORCHESTRATOR_AGENT_ALIAS_ID:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "Server is not configured. Agent Alias ID is a placeholder."})
            }

        response = bedrock_agent.invoke_agent(
            agentId=ORCHESTRATOR_AGENT_ID,
            agentAliasId=ORCHESTRATOR_AGENT_ALIAS_ID,
            sessionId=session_id,
            inputText=prompt,
        )

        completion = ""
        # The response from the agent is a stream of data chunks
        for chunk in response['completion']:
            completion += chunk['chunk']['bytes'].decode()

        return {
            "statusCode": 200,
            "body": json.dumps({"response": completion, "session_id": session_id})
        }

    except json.JSONDecodeError:
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON in request body"})}
    except Exception as e:
        # Catch other potential errors
        print(f"Error invoking agent: {e}")
        return {
            "statusCode": 500, 
            "body": json.dumps({"error": f"An internal error occurred: {str(e)}"})
        }