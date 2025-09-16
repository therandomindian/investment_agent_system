# investment_agent_system/investment_agent_system_stack.py

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    CfnParameter, 
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_apigateway as apigateway,
    aws_bedrock as bedrock,
    aws_s3 as s3,
    aws_logs as logs
)
from constructs import Construct
from aws_cdk.aws_lambda import Architecture
from aws_cdk.aws_lambda_python_alpha import PythonFunction

class InvestmentAgentSystemStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Parameter to accept the ID of the manually created Knowledge Base
        knowledge_base_id = CfnParameter(
            self, "KnowledgeBaseId",
            type="String",
            description="The ID of the manually created Bedrock Knowledge Base."
        ).value_as_string

        # S3 Bucket for PDS documents
        pds_bucket = s3.Bucket(
            self, "PdsDocumentsBucket",
            versioned=False, # Versioning is now turned off
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL
        )

        # IAM Role for Bedrock Agents to run
        agent_execution_role = iam.Role(
            self, "BedrockAgentExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
        )
        agent_execution_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[f"arn:aws:bedrock:{self.region}::foundation-model/amazon.nova-micro-v1:0"]
        ))

        # Grant the agent role permission to retrieve from the manually created KB
        agent_execution_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:Retrieve"],
            resources=[f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/{knowledge_base_id}"]
        ))

        # Bedrock Agents
        personalized_agent = bedrock.CfnAgent(
            self, "PersonalizedInfoAgent",
            agent_name="Personalized-Information-Agent",
            agent_resource_role_arn=agent_execution_role.role_arn,
            foundation_model="amazon.nova-micro-v1:0",
            instruction="You provide personalized financial information based on the user's query. State clearly this is not advice and you cannot access their account.",
        )

        general_agent = bedrock.CfnAgent(
            self, "GeneralAdviceAgent",
            agent_name="General-Advice-Agent",
            agent_resource_role_arn=agent_execution_role.role_arn,
            foundation_model="amazon.nova-micro-v1:0",
            knowledge_bases=[bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                knowledge_base_id=knowledge_base_id,
                description="Contains Product Disclosure Statements (PDS) for Vanguard Australia products."
            )],
            instruction=""" You are an expert AI assistant representing Vanguard Investments Australia. Your primary role is to provide factual, educational information and general financial advice to clients based strictly on official Vanguard documentation.

                            **Core Directives:**

                            1.  **Source of Truth:** You MUST base all answers about Vanguard's products, their features, performance, and fees exclusively on the content retrieved from the knowledge base (the provided S3 vector store). Do not invent information or use your general training data for product-specific queries. If the answer to a user's question cannot be found in the provided documents, you MUST state that the information is not available in the official documents you have access to.

                            2.  **General Advice Only:** You are operating under Australian Financial Services Law and are ONLY permitted to provide General Advice. This is a strict and critical constraint. General Advice does not take into account a person's individual objectives, financial situation, or needs.
                                - NEVER recommend that a user should buy, sell, or hold a specific product.
                                - NEVER suggest a product is suitable or a good fit for a user.
                                - Your role is to explain what products are and how they work in a factual, objective way, based on the documents. For example, instead of saying "You should consider this ETF for growth," say "This ETF aims to provide capital growth by investing in a portfolio of Australian shares."

                            3.  **Tone:** Your tone must be professional, objective, helpful, and aligned with Vanguard's brand of providing clear, straightforward investment information.

                            **Mandatory Output Format:**

                            CRITICAL: Every single response you generate MUST begin with the following "General Advice Warning," formatted exactly as shown below in a markdown block. There are no exceptions to this rule.

                            ---
                            > **General Advice Warning**
                            > The information provided is general in nature and does not take into account your personal objectives, financial situation, or needs. You should consider your own circumstances and whether the information is appropriate for you before making any investment decision. We recommend you seek independent financial advice.
                            ---

                            After providing this warning, proceed to answer the user's query according to the directives above.
                            """,
        )

        orchestrator_agent = bedrock.CfnAgent(
            self, "OrchestratorAgent",
            agent_name="Investment-Orchestrator-Agent",
            agent_resource_role_arn=agent_execution_role.role_arn,
            foundation_model="amazon.nova-micro-v1:0",
            instruction=f"""
                You are a master financial query orchestrator. Your job is to route queries to the correct specialist.
                - If a query is about general market concepts... you must invoke the '{general_agent.agent_name}' agent to get the answer.
                - If a query is personal... you must invoke the '{personalized_agent.agent_name}' agent to get the answer.
                - Respond only with the answer you receive from the specialist agent.
            """
        )
        
        agent_execution_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeAgent"],
            resources=[personalized_agent.attr_agent_arn, general_agent.attr_agent_arn]
        ))
        
        # --- THE FIX ---
        # Explicitly define the Log Group for the Lambda function to prevent conflicts
        invoke_agent_log_group = logs.LogGroup(
            self, "InvokeAgentLambdaLogGroup",
            # A unique but predictable name for the log group
            log_group_name=f"/aws/lambda/{self.stack_name}-InvokeAgentLambda",
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # API Entrypoint Lambda
        invoke_agent_lambda = PythonFunction(
            self, "InvokeAgentLambda",
            entry="lambda/invoke_agent",
            index="app.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_11,
            architecture=Architecture.ARM_64,
            timeout=Duration.seconds(90),
            environment={
                "ORCHESTRATOR_AGENT_ID": orchestrator_agent.attr_agent_id,
                "ORCHESTRATOR_AGENT_ALIAS_ID": "PLACEHOLDER"
            },
            # Associate the explicitly created log group
            log_group=invoke_agent_log_group
        )
        
        invoke_agent_lambda.role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeAgent"],
            resources=[
                f"arn:aws:bedrock:{self.region}:{self.account}:agent-alias/{orchestrator_agent.attr_agent_id}/*"
            ]
        ))

        # API Gateway with API Key security and logging
        api_log_group = logs.LogGroup(self, "ApiAccessLogs")
        api = apigateway.LambdaRestApi(
            self, "InvestmentAgentApi",
            handler=invoke_agent_lambda,
            default_method_options=apigateway.MethodOptions(
                api_key_required=True
            ),
            deploy_options=apigateway.StageOptions(
                access_log_destination=apigateway.LogGroupLogDestination(api_log_group),
                access_log_format=apigateway.AccessLogFormat.json_with_standard_fields(
                    caller=True, http_method=True, ip=True, protocol=True, request_time=True,
                    resource_path=True, response_length=True, status=True, user=True
                )
            )
        )
        
        api_key = apigateway.ApiKey(self, "MyApiKey", api_key_name="investment-agent-key")
        usage_plan = api.add_usage_plan("MyUsagePlan", name="StandardUsagePlan",
            throttle=apigateway.ThrottleSettings(rate_limit=10, burst_limit=5)
        )
        usage_plan.add_api_key(api_key)
        
        # Outputs
        CfnOutput(self, "ApiEndpointUrl", value=api.url)
        CfnOutput(self, "PdsBucketName", value=pds_bucket.bucket_name)
        CfnOutput(self, "ApiKeyId",
            value=api_key.key_id,
            description="The ID of the API Key to use for requests"
        )