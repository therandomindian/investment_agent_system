# lambda/agent_preparer/prepare_agents.py

import json
import boto3
import time
from typing import Dict, Any

bedrock_agent = boto3.client("bedrock-agent")

def handler(event, context):
    """
    Custom resource Lambda to prepare Bedrock agents and aliases
    """
    try:
        print(f"Received event: {json.dumps(event, default=str)}")
        
        request_type = event.get('RequestType')
        properties = event.get('ResourceProperties', {})
        
        if request_type == 'Create' or request_type == 'Update':
            return prepare_agents_and_aliases(event, context, properties)
        elif request_type == 'Delete':
            # Nothing to do on delete
            return send_response(event, context, 'SUCCESS', {})
        else:
            return send_response(event, context, 'FAILED', {}, f"Unknown request type: {request_type}")
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return send_response(event, context, 'FAILED', {}, str(e))


def prepare_agents_and_aliases(event, context, properties):
    """
    Prepare all agents and their aliases
    """
    try:
        agents = properties.get('Agents', [])
        aliases = properties.get('Aliases', [])
        
        results = {}
        
        # Prepare agents first
        for agent_info in agents:
            agent_id = agent_info['AgentId']
            agent_name = agent_info['AgentName']
            
            print(f"Preparing agent {agent_name} ({agent_id})")
            
            try:
                response = bedrock_agent.prepare_agent(agentId=agent_id)
                print(f"Agent {agent_name} preparation initiated: {response}")
                
                # Wait for agent to be prepared
                wait_for_agent_preparation(agent_id, agent_name)
                results[f"Agent_{agent_name}"] = "Prepared"
                
            except Exception as e:
                print(f"Error preparing agent {agent_name}: {str(e)}")
                results[f"Agent_{agent_name}"] = f"Error: {str(e)}"
        
        # Prepare aliases after agents are prepared
        for alias_info in aliases:
            agent_id = alias_info['AgentId']
            alias_id = alias_info['AliasId']
            alias_name = alias_info['AliasName']
            
            print(f"Preparing alias {alias_name} ({alias_id}) for agent {agent_id}")
            
            try:
                response = bedrock_agent.prepare_agent_alias(
                    agentId=agent_id,
                    agentAliasId=alias_id
                )
                print(f"Alias {alias_name} preparation initiated: {response}")
                
                # Wait for alias to be prepared
                wait_for_alias_preparation(agent_id, alias_id, alias_name)
                results[f"Alias_{alias_name}"] = "Prepared"
                
            except Exception as e:
                print(f"Error preparing alias {alias_name}: {str(e)}")
                results[f"Alias_{alias_name}"] = f"Error: {str(e)}"
        
        return send_response(event, context, 'SUCCESS', results)
        
    except Exception as e:
        print(f"Error in prepare_agents_and_aliases: {str(e)}")
        return send_response(event, context, 'FAILED', {}, str(e))


def wait_for_agent_preparation(agent_id: str, agent_name: str, max_wait_time: int = 300):
    """
    Wait for agent to be prepared (max 5 minutes)
    """
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            response = bedrock_agent.get_agent(agentId=agent_id)
            agent_status = response.get('agent', {}).get('agentStatus')
            
            print(f"Agent {agent_name} status: {agent_status}")
            
            if agent_status == 'PREPARED':
                print(f"Agent {agent_name} is now prepared")
                return True
            elif agent_status == 'FAILED':
                raise Exception(f"Agent {agent_name} preparation failed")
            
            time.sleep(10)  # Wait 10 seconds before checking again
            
        except Exception as e:
            print(f"Error checking agent status: {str(e)}")
            time.sleep(10)
    
    raise Exception(f"Timeout waiting for agent {agent_name} to be prepared")


def wait_for_alias_preparation(agent_id: str, alias_id: str, alias_name: str, max_wait_time: int = 300):
    """
    Wait for alias to be prepared (max 5 minutes)
    """
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            response = bedrock_agent.get_agent_alias(
                agentId=agent_id,
                agentAliasId=alias_id
            )
            alias_status = response.get('agentAlias', {}).get('agentAliasStatus')
            
            print(f"Alias {alias_name} status: {alias_status}")
            
            if alias_status == 'PREPARED':
                print(f"Alias {alias_name} is now prepared")
                return True
            elif alias_status == 'FAILED':
                raise Exception(f"Alias {alias_name} preparation failed")
            
            time.sleep(10)  # Wait 10 seconds before checking again
            
        except Exception as e:
            print(f"Error checking alias status: {str(e)}")
            time.sleep(10)
    
    raise Exception(f"Timeout waiting for alias {alias_name} to be prepared")


def send_response(event, context, response_status, response_data, reason=None):
    """
    Send response back to CloudFormation
    """
    import urllib3
    
    response_url = event['ResponseURL']
    
    response_body = {
        'Status': response_status,
        'Reason': reason or f'See CloudWatch Log Stream: {context.log_stream_name}',
        'PhysicalResourceId': context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'Data': response_data
    }
    
    json_response_body = json.dumps(response_body)
    
    print(f"Response body: {json_response_body}")
    
    headers = {
        'content-type': '',
        'content-length': str(len(json_response_body))
    }
    
    try:
        http = urllib3.PoolManager()
        response = http.request('PUT', response_url, body=json_response_body, headers=headers)
        print(f"Status code: {response.status}")
        return {'statusCode': 200}
    except Exception as e:
        print(f"send_response failed: {e}")
        return {'statusCode': 500}